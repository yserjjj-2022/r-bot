import uuid
from datetime import datetime
from typing import List, Optional, Any, Dict
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Float, DateTime, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector
from .config import settings

# --- Setup ---

engine = create_async_engine(settings.database_url, echo=False)
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
    
    # Vector column. Note: Dimension must match settings.EMBEDDING_DIM (1536)
    embedding = mapped_column(Vector(settings.EMBEDDING_DIM))
    
    emotion_score: Mapped[float] = mapped_column(Float, default=0.0)
    tags: Mapped[List[str]] = mapped_column(JSONB, default=[]) # Tags as JSONB array
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
    """
    Таблица для логирования телеметрии (замена внешней базе метрик)
    """
    __tablename__ = "rcore_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    event_type: Mapped[str] = mapped_column(String(50)) # llm_call, memory_write, user_message
    session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, default={}) # Flexible payload

# --- Init DB Helper ---

async def init_models():
    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all) # Uncomment to reset
        await conn.run_sync(Base.metadata.create_all)
