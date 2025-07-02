# app/modules/database/models.py

# ИЗМЕНЕНИЕ: Добавляем импорт 'func' из sqlalchemy
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, nullable=False)
    # ИЗМЕНЕНИЕ: Используем server_default с функцией NOW() базы данных
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")

class Session(Base):
    __tablename__ = 'sessions'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    graph_id = Column(String, nullable=False)
    # ИЗМЕНЕНИЕ: Используем server_default
    start_time = Column(DateTime(timezone=True), server_default=func.now())
    end_time = Column(DateTime(timezone=True), nullable=True)
    user = relationship("User", back_populates="sessions")
    responses = relationship("Response", back_populates="session", cascade="all, delete-orphan")
    ai_dialogues = relationship("AIDialogue", back_populates="session", cascade="all, delete-orphan")

class Response(Base):
    __tablename__ = 'responses'
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('sessions.id'), nullable=False)
    node_id = Column(String, nullable=False)
    answer_text = Column(Text, nullable=False)
    # ИЗМЕНЕНИЕ: Используем server_default
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    session = relationship("Session", back_populates="responses")

class AIDialogue(Base):
    __tablename__ = 'ai_dialogues'
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('sessions.id'), nullable=False)
    node_id = Column(String, nullable=False)
    user_message = Column(Text, nullable=False)
    ai_response = Column(Text, nullable=False)
    # ИЗМЕНЕНИЕ: Используем server_default
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    session = relationship("Session", back_populates="ai_dialogues")
