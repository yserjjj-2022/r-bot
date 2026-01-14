# app/modules/database/models.py
# Финальная версия 6.0: Этап 0 - добавлены новые модели + исправлен deprecated datetime.utcnow

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base

# Utility функция для современного UTC времени
def utc_now():
    """Возвращает текущее время в UTC (современная замена datetime.utcnow)"""
    return datetime.now(timezone.utc)


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

        # NEW: маркер официальных исследований и пауза при сбое AI
    is_official_research = Column(Boolean, default=False)
    is_paused = Column(Boolean, default=False)
    
    # === НОВЫЕ ПОЛЯ ЭТАПА 0 ===
    group_id = Column(Integer, default=None)
    session_metadata = Column(JSON, default={})
    
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
    
    # === НОВОЕ ПОЛЕ ЭТАПА 0 ===
    importance = Column(String(20), default='medium')  # ИИ-определяемая важность события
    
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


# === НОВЫЕ МОДЕЛИ ДЛЯ ЭТАПА 0 ===

class ActiveTimer(Base):
    """Активные таймеры для timing механик"""
    __tablename__ = 'active_timers'
    
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('sessions.id'))
    timer_type = Column(String(50), default='remind')  # remind, timeout, cooldown
    target_timestamp = Column(DateTime)  # когда сработать
    message_text = Column(Text, default='')
    callback_node_id = Column(String(50))  # на какой узел перейти
    callback_data = Column(JSON, default={})
    status = Column(String(20), default='pending')  # pending, executed, cancelled
    created_at = Column(DateTime, default=utc_now)  # ИСПРАВЛЕНО: современный UTC


class ResearchGroup(Base):
    """Группы для групповых исследований"""
    __tablename__ = 'research_groups'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), default='Unnamed Group')
    scenario_id = Column(String(50))  # ID сценария
    group_type = Column(String(50), default='individual')  # individual, competition, cooperation
    max_participants = Column(Integer, default=1)
    status = Column(String(20), default='forming')  # forming, active, completed
    group_data = Column(JSON, default={})  # дополнительные данные группы
    created_at = Column(DateTime, default=utc_now)  # ИСПРАВЛЕНО: современный UTC


class GroupParticipant(Base):
    """Участники групповых исследований"""
    __tablename__ = 'group_participants'
    
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey('research_groups.id'))
    user_id = Column(Integer, ForeignKey('users.id'))
    session_id = Column(Integer, ForeignKey('sessions.id'))
    role = Column(String(50), default='participant')  # participant, observer, leader
    joined_at = Column(DateTime, default=utc_now)  # ИСПРАВЛЕНО: современный UTC
    status = Column(String(20), default='active')  # active, finished, dropped_out


class GroupEvent(Base):
    """События в групповых исследованиях"""
    __tablename__ = 'group_events'
    
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey('research_groups.id'))
    participant_id = Column(Integer, ForeignKey('group_participants.id'))
    event_type = Column(String(50))  # decision, reveal, round_end, game_over
    event_data = Column(JSON, default={})  # данные события
    round_number = Column(Integer, default=1)
    created_at = Column(DateTime, default=utc_now)  # ИСПРАВЛЕНО: современный UTC
