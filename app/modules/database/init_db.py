# app/modules/database/init_db.py

from .database import engine  # Точка означает "из текущего пакета"
from . import models

def create_tables():
    """
    Создает все таблицы в базе данных на основе моделей SQLAlchemy.
    """
    print("--- [init_db] Попытка создать таблицы... ---")
    try:
        # Эта одна команда делает всю магию
        models.Base.metadata.create_all(bind=engine)
        print("--- [init_db] Таблицы успешно созданы или уже существуют. ---")
    except Exception as e:
        print(f"!!! [init_db] КРИТИЧЕСКАЯ ОШИБКА при создании таблиц: {e} !!!")
        # Важно выбросить ошибку дальше, чтобы остановить запуск, если БД недоступна
        raise

if __name__ == "__main__":
    create_tables()
