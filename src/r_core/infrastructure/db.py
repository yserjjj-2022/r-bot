import uuid
from datetime import datetime
from typing import List, Optional, Any, Dict
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Float, DateTime, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector
from src.r_core.config import settings
from sqlalchemy.pool import NullPool
from sqlalchemy import select, desc

# --- Setup ---
engine = create_async_engine(
    settings.database_url, 
    echo=False,
    poolclass=NullPool 
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class Base(DeclarativeBase):
    pass

# --- Models ---

class SemanticModel(Base):
    __tablename__ = "semantic_memory"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    subject: Mapped[str] = mapped_column(String(255))
    predicate: Mapped[str] = mapped_column(String(255))
    object: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source_message_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class EpisodicModel(Base):
    __tablename__ = "episodic_memory"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    raw_text: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(Vector(settings.EMBEDDING_DIM))
    emotion_score: Mapped[float] = mapped_column(Float, default=0.0)
    tags: Mapped[List[str]] = mapped_column(JSONB, default=[])
    ttl_days: Mapped[int] = mapped_column(Integer, default=30)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class VolitionalModel(Base):
    __tablename__ = "volitional_patterns"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    trigger: Mapped[str] = mapped_column(String(255))
    impulse: Mapped[str] = mapped_column(String(255))
    goal: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    conflict_detected: Mapped[bool] = mapped_column(default=False)
    resolution_strategy: Mapped[str] = mapped_column(String(255))
    action_taken: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class MetricsModel(Base):
    __tablename__ = "rcore_metrics"
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    event_type: Mapped[str] = mapped_column(String(50)) 
    session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, default={}) 

class ChatHistoryModel(Base):
    __tablename__ = "chat_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

# --- NEW: User Profile Model ---
class UserProfileModel(Base):
    __tablename__ = "user_profiles"
    
    user_id: Mapped[int] = mapped_column(primary_key=True) # One profile per user
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(20), nullable=True) # 'M', 'F', 'N'
    preferred_mode: Mapped[str] = mapped_column(String(20), default="formal") # 'formal' (Вы), 'informal' (Ты)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    attributes: Mapped[Dict[str, Any]] = mapped_column(JSONB, default={}) # Flexible storage

# --- Init DB Helper ---

async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
