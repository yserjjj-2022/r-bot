# web_server.py

import io
import json
import pandas as pd
import pytz
from flask import Flask, make_response, render_template, request, jsonify
from sqlalchemy import create_engine, text
from decouple import config

# --- Инициализация приложения и констант ---
app = Flask(__name__)
DATABASE_URL = config("DATABASE_URL")
engine = create_engine(DATABASE_URL)
# Определяем путь к нашему основному файлу графа
GRAPH_FILE_PATH = "graphs/default_interview.json"


# ===============================================================
#  Раздел API для редактора графов
# ===============================================================

@app.route("/editor")
def graph_editor():
    """
    Отдает HTML-страницу нашего редактора графов.
    Flask будет автоматически искать 'editor.html' в папке 'templates'.
    """
    return render_template("editor.html")


@app.route("/api/graph", methods=["GET"])
def load_graph():
    """
    API эндпоинт для ЗАГРУЗКИ графа.
    Читает JSON-файл и отдает его фронтенду.
    """
    try:
        with open(GRAPH_FILE_PATH, 'r', encoding='utf-8') as f:
            graph_data = json.load(f)
        return jsonify(graph_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/graph", methods=["POST"])
def save_graph():
    """
    API эндпоинт для СОХРАНЕНИЯ графа.
    Получает JSON от фронтенда и записывает его в файл.
    """
    try:
        # Получаем JSON данные из тела POST-запроса
        graph_data = request.json
        if not graph_data:
            return jsonify({"error": "Нет данных для сохранения"}), 400

        with open(GRAPH_FILE_PATH, 'w', encoding='utf-8') as f:
            # indent=2 делает JSON-файл читаемым для человека
            # ensure_ascii=False гарантирует корректное сохранение кириллицы
            json.dump(graph_data, f, ensure_ascii=False, indent=2)
            
        return jsonify({"success": True, "message": "Граф успешно сохранен."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===============================================================
#  Раздел для выгрузки CSV (остается без изменений)
# ===============================================================

def get_data_as_dataframe():
    """
    Выполняет запрос к БД и возвращает данные в виде pandas DataFrame.
    """
    query = text("""
        WITH all_events AS (
            SELECT session_id, 'response' AS event_type, timestamp AS event_timestamp, node_id, answer_text, NULL AS user_message, NULL AS ai_response FROM responses
            UNION ALL
            SELECT session_id, 'ai_dialogue' AS event_type, timestamp AS event_timestamp, node_id, NULL AS answer_text, user_message, ai_response FROM ai_dialogues
        )
        SELECT s.id AS session_id, u.telegram_id, s.graph_id, s.start_time AS session_start_utc, s.end_time AS session_end_utc, e.event_type, e.event_timestamp AS event_timestamp_utc, e.node_id, e.answer_text, e.user_message, e.ai_response
        FROM sessions s JOIN users u ON s.user_id = u.id
        LEFT JOIN all_events e ON e.session_id = s.id
        ORDER BY s.id, e.event_timestamp;
    """)
    with engine.connect() as connection:
        df = pd.read_sql_query(query, connection)
    return df

def convert_timezone_safe(series, target_tz='Europe/Moscow'):
    """
    Безопасно конвертирует колонку DataFrame в целевой часовой пояс.
    """
    if series.isnull().all():
        return series
    series = pd.to_datetime(series)
    if pd.api.types.is_datetime64tz_dtype(series):
        return series.dt.tz_convert(target_tz)
    else:
        return series.dt.tz_localize('UTC').dt.tz_convert(target_tz)

@app.route("/export")
def export_csv():
    """
    Формирует CSV и отдает его для скачивания.
    """
    df = get_data_as_dataframe()
    time_columns = ['session_start_utc', 'session_end_utc', 'event_timestamp_utc']
    for col in time_columns:
        if col in df.columns:
            new_col_name = col.replace('_utc', '_msk')
            df[new_col_name] = convert_timezone_safe(df[col])

    output = io.StringIO()
    df.to_csv(output, index=False, encoding='utf-8-sig')
    csv_data = output.getvalue()
    
    response = make_response(csv_data)
    response.headers["Content-Disposition"] = "attachment; filename=results.csv"
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    
    return response


# ===============================================================
#  Запуск приложения
# ===============================================================

if __name__ == "__main__":
    # debug=True автоматически перезапускает сервер при изменениях в коде
    app.run(host='0.0.0.0', port=5000, debug=True)
