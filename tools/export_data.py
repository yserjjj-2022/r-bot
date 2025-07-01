# tools/export_data.py

import os
import pandas as pd
import pytz
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from decouple import config

# Комментарий: Подключаемся к базе данных, используя ту же логику, что и в основном приложении.
# Скрипт автоматически подхватит DATABASE_URL из вашего .env файла.
DATABASE_URL = config("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def export_data_to_csv(filename: str = "results.csv"):
    """
    Собирает все данные из таблиц users, sessions, responses, ai_dialogues,
    объединяет их, преобразует время в московское и сохраняет в CSV-файл.
    """
    db = SessionLocal()
    print("Подключение к базе данных...")
    
    try:
        # Комментарий: Этот сложный SQL-запрос с помощью LEFT JOIN объединяет все наши таблицы
        # в одну большую "плоскую" таблицу, где каждая строка представляет собой одно событие (ответ или диалог).
        query = text("""
            SELECT
                s.id AS session_id,
                u.telegram_id,
                s.graph_id,
                s.start_time AS session_start_utc,
                s.end_time AS session_end_utc,
                r.node_id AS response_node_id,
                r.answer_text,
                r.timestamp AS response_timestamp_utc,
                d.node_id AS ai_node_id,
                d.user_message,
                d.ai_response,
                d.timestamp AS ai_timestamp_utc
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            LEFT JOIN responses r ON r.session_id = s.id
            LEFT JOIN ai_dialogues d ON d.session_id = s.id
            ORDER BY s.id, r.timestamp, d.timestamp
        """)

        print("Выполнение запроса к базе данных...")
        # Комментарий: Использование pandas.read_sql_query - это удобный способ сразу
        # выполнить запрос и загрузить результат в DataFrame.
        df = pd.read_sql_query(query, db.bind)

        print(f"Получено {len(df)} строк. Начинаем обработку времени...")
        
        # --- Преобразование времени в московское ---
        moscow_tz = pytz.timezone('Europe/Moscow')
        
        # Список колонок с временем, которые нужно преобразовать
        time_columns = [
            'session_start_utc', 'session_end_utc', 
            'response_timestamp_utc', 'ai_timestamp_utc'
        ]
        
        for col in time_columns:
            # Новое имя колонки, например, session_start_msk
            new_col_name = col.replace('_utc', '_msk')
            # Преобразуем время, игнорируя пустые значения (NaT)
            df[new_col_name] = pd.to_datetime(df[col]).dt.tz_convert(moscow_tz)

        print("Преобразование времени завершено. Сохранение в файл...")
        # Сохраняем в CSV. encoding='utf-8-sig' важен для корректного отображения кириллицы в Excel.
        df.to_csv(filename, index=False, encoding='utf-8-sig')

        print(f"✅ Данные успешно выгружены в файл: {filename}")

    except Exception as e:
        print(f"❌ Произошла ошибка при выгрузке данных: {e}")
    finally:
        print("Закрытие соединения с базой данных.")
        db.close()

if __name__ == "__main__":
    export_data_to_csv()
