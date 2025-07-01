from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base
from decouple import config # <-- Импортируем config

# Комментарий: config() автоматически найдет .env файл и загрузит из него переменную.
# Если не найдет - использует значение default.
DATABASE_URL = config("DATABASE_URL", default="postgresql://user:password@localhost/interview_bot_db")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    # Комментарий: Эта функция создает таблицы в базе данных на основе моделей.
    Base.metadata.create_all(bind=engine)