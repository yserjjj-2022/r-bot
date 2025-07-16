# app/modules/database/models.py
# Финальная версия 5.24: Добавлено поле node_text в модель Response для полного контекста.

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base

class User(Base):
    """Модель пользователя. Хранит основную информацию."""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    states = relationship("UserState", back_populates="user", cascade="all, delete-orphan")

class Session(Base):
    """Модель сессии. Каждая новая команда /start создает новую сессию."""
    __tablename__ = 'sessions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    graph_id = Column(String, nullable=False)
    start_time = Column(DateTime(timezone=True), server_default=func.now())
    end_time = Column(DateTime(timezone=True), nullable=True)
    
    user = relationship("User", back_populates="sessions")
    responses = relationship("Response", back_populates="session", cascade="all, delete-orphan")
    ai_dialogues = relationship("AIDialogue", back_populates="session", cascade="all, delete-orphan")
    states = relationship("UserState", back_populates="session", cascade="all, delete-orphan")

class Response(Base):
    """Модель ответа пользователя на узел сценария."""
    __tablename__ = 'responses'
    
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('sessions.id'), nullable=False)
    node_id = Column(String, nullable=False)
    
    # --- ИЗМЕНЕНИЕ: Добавлено поле для хранения текста самого вопроса/события ---
    # Это позволяет ИИ видеть полную картину: "Что произошло" -> "Как отреагировал игрок".
    node_text = Column(Text, nullable=False, default='N/A')
    
    answer_text = Column(Text, nullable=False) # Текст трактовки или кнопки
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    session = relationship("Session", back_populates="responses")

class AIDialogue(Base):
    """Модель для хранения диалогов пользователя с AI-ассистентом."""
    __tablename__ = 'ai_dialogues'
    
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('sessions.id'), nullable=False)
    node_id = Column(String, nullable=False)
    user_message = Column(Text, nullable=False)
    ai_response = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    session = relationship("Session", back_populates="ai_dialogues")

class UserState(Base):
    """Модель для хранения произвольных состояний пользователя в рамках сессии."""
    __tablename__ = "user_states"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    state_key = Column(String, nullable=False, index=True)
    state_value = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="states")
    session = relationship("Session", back_populates="states")
