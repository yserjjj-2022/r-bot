# app/modules/database/database.py

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from decouple import config

# 1. Получаем строку подключения к базе данных из переменных окружения.
#    В Amvera эта переменная будет установлена автоматически при привязке БД.
#    Для локального запуска она будет браться из файла .env.
DATABASE_URL = config("DATABASE_URL")

# 2. СОЗДАЕМ ДВИГАТЕЛЬ (ENGINE)!
#    Это главный объект для работы с базой данных.
#    Мы говорим SQLAlchemy: "Подключись к PostgreSQL по этому адресу".
engine = create_engine(DATABASE_URL)

# 3. Создаем "фабрику" сессий. 
#    Каждый раз, когда нам нужно будет поговорить с БД (в crud.py или telegram_handler.py),
#    мы будем вызывать SessionLocal(), чтобы получить новую, свежую сессию.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 4. Создаем базовый класс для наших моделей.
#    Все наши классы-таблицы (User, Session и т.д. из models.py) должны наследоваться от него.
Base = declarative_base()
