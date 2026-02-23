import uuid
from datetime import datetime
from typing import List, Optional, Any, Dict
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Float, DateTime, Text, ForeignKey, JSON, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector
from src.r_core.config import settings
from sqlalchemy.pool import NullPool
from sqlalchemy import select, desc, text

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
    # ✨ Affective ToM - эмоциональное отношение пользователя к объекту
    sentiment: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # ✨ NEW (Migration 004): Embedding для дедупликации через гиппокамп
    embedding = mapped_column(Vector(settings.EMBEDDING_DIM), nullable=True)

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
    
    # === Core ===
    trigger: Mapped[str] = mapped_column(String(255))
    impulse: Mapped[str] = mapped_column(String(255))
    target: Mapped[Optional[str]] = mapped_column(String(255), nullable=True) # ✨ NEW: Object of focus
    goal: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)   # Legacy, keep for now
    
    # === State & Dynamics ===
    intensity: Mapped[float] = mapped_column(Float, default=0.5) 
    fuel: Mapped[float] = mapped_column(Float, default=1.0) # ✨ NEW: Current fuel
    learned_delta: Mapped[float] = mapped_column(Float, default=0.0) 
    
    turns_active: Mapped[int] = mapped_column(Integer, default=0) # ✨ NEW
    last_novelty_turn: Mapped[int] = mapped_column(Integer, default=0) # ✨ NEW
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True) 
    
    # === Config ===
    decay_rate: Mapped[float] = mapped_column(Float, default=0.01)
    reinforcement_rate: Mapped[float] = mapped_column(Float, default=0.05)
    energy_cost: Mapped[float] = mapped_column(Float, default=0.1) # ✨ NEW: Cost per turn
    
    # === Legacy (Data Contract: nullable=True or safe defaults) ===
    conflict_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution_strategy: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, default=None)
    action_taken: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    
    # === Stage 1: TEC/Taxonomy Fields ===
    intent_category: Mapped[str] = mapped_column(String(50), default="Casual")  # Phatic, Casual, Narrative, Deep, Task
    topic_engagement: Mapped[float] = mapped_column(Float, default=1.0)  # TEC: 0.0-1.0
    base_decay_rate: Mapped[float] = mapped_column(Float, default=0.12)  # Nature-based decay
    complexity_modifier: Mapped[float] = mapped_column(Float, default=1.0)  # Topic complexity factor
    emotional_load: Mapped[float] = mapped_column(Float, default=0.0)  # Emotional intensity
    recovery_rate: Mapped[float] = mapped_column(Float, default=0.05)  # TEC recovery rate
    
    last_activated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class MetricsModel(Base):
    __tablename__ = "rcore_metrics"
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    event_type: Mapped[str] = mapped_column(String(50)) 
    session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # ✨ Метрики для Affective ToM
    affective_triggers_detected: Mapped[int] = mapped_column(Integer, default=0)
    sentiment_context_used: Mapped[bool] = mapped_column(default=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, default={}) 

class ChatHistoryModel(Base):
    __tablename__ = "chat_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class UserProfileModel(Base):
    __tablename__ = "user_profiles"
    user_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    preferred_mode: Mapped[str] = mapped_column(String(20), default="formal") 
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    attributes: Mapped[Dict[str, Any]] = mapped_column(JSONB, default={}) 
    
    # ✨ NEW (Migration 003): Триггер для "ленивого гиппокампа"
    short_term_memory_load: Mapped[int] = mapped_column(Integer, default=0)
    last_consolidation_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class AgentProfileModel(Base):
    __tablename__ = "agent_profiles"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(20), default="Neutral")
    sliders_preset: Mapped[Dict[str, Any]] = mapped_column(JSONB, default={}) 
    
    # ✨ Experimental controls
    intuition_gain: Mapped[float] = mapped_column(Float, default=1.0)
    use_unified_council: Mapped[bool] = mapped_column(default=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# --- Init DB Helper ---

async def init_models():
    """Инициализация + автомиграция"""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        
        # ✨ Migration: Add sentiment column to semantic_memory
        try:
            await conn.execute(text(
                "ALTER TABLE semantic_memory ADD COLUMN IF NOT EXISTS sentiment JSONB DEFAULT NULL"
            ))
            print("[DB Init] ✅ sentiment column added to semantic_memory")
        except Exception as e:
            print(f"[DB Init] Schema update (sentiment): {e}")
        
        # ✨ Migration: Add affective metrics columns to rcore_metrics
        try:
            await conn.execute(text(
                "ALTER TABLE rcore_metrics ADD COLUMN IF NOT EXISTS affective_triggers_detected INTEGER DEFAULT 0"
            ))
            await conn.execute(text(
                "ALTER TABLE rcore_metrics ADD COLUMN IF NOT EXISTS sentiment_context_used BOOLEAN DEFAULT FALSE"
            ))
            print("[DB Init] ✅ Affective metrics columns added to rcore_metrics")
        except Exception as e:
            print(f"[DB Init] Schema update (metrics): {e}")
        
        # ✨ Migration: Create GIN index for fast sentiment queries
        try:
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_semantic_sentiment ON semantic_memory USING GIN (sentiment)"
            ))
            print("[DB Init] ✅ GIN index created for sentiment column")
        except Exception as e:
            print(f"[DB Init] Index creation (sentiment): {e}")
        
        # ✨ Migration: Add gender column to agent_profiles
        try:
            await conn.execute(text(
                "ALTER TABLE agent_profiles ADD COLUMN IF NOT EXISTS gender VARCHAR(20) DEFAULT 'Neutral'"
            ))
            print("[DB Init] ✅ gender column added to agent_profiles")
        except Exception as e:
            print(f"[DB Init] Schema update (gender): {e}")
        
        # ✨ Migration: Add intuition_gain and use_unified_council to agent_profiles
        try:
            await conn.execute(text(
                "ALTER TABLE agent_profiles ADD COLUMN IF NOT EXISTS intuition_gain FLOAT DEFAULT 1.0"
            ))
            await conn.execute(text(
                "ALTER TABLE agent_profiles ADD COLUMN IF NOT EXISTS use_unified_council BOOLEAN DEFAULT FALSE"
            ))
            await conn.execute(text(
                "ALTER TABLE agent_profiles ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ))
            print("[DB Init] ✅ intuition_gain, use_unified_council, updated_at added to agent_profiles")
        except Exception as e:
            print(f"[DB Init] Schema update (agent experimental controls): {e}")
        
        # ✨ NEW Migration 003: short_term_memory_load для гиппокампа
        try:
            await conn.execute(text(
                "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS short_term_memory_load INTEGER DEFAULT 0"
            ))
            await conn.execute(text(
                "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS last_consolidation_at TIMESTAMP DEFAULT NULL"
            ))
            print("[DB Init] ✅ short_term_memory_load, last_consolidation_at added to user_profiles")
        except Exception as e:
            print(f"[DB Init] Schema update (hippocampus trigger): {e}")
        
        # ✨ NEW Migration 004: embedding в semantic_memory для дедупликации
        try:
            await conn.execute(text(
                f"ALTER TABLE semantic_memory ADD COLUMN IF NOT EXISTS embedding vector({settings.EMBEDDING_DIM}) DEFAULT NULL"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_semantic_memory_embedding ON semantic_memory USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL"
            ))
            print("[DB Init] ✅ embedding column + HNSW index added to semantic_memory")
        except Exception as e:
            print(f"[DB Init] Schema update (semantic embedding): {e}")

        # ✨ NEW Migration 005: Volitional System Fields
        try:
            await conn.execute(text(
                "ALTER TABLE volitional_patterns ADD COLUMN IF NOT EXISTS intensity FLOAT DEFAULT 0.5"
            ))
            await conn.execute(text(
                "ALTER TABLE volitional_patterns ADD COLUMN IF NOT EXISTS learned_delta FLOAT DEFAULT 0.0"
            ))
            await conn.execute(text(
                "ALTER TABLE volitional_patterns ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE"
            ))
            await conn.execute(text(
                "ALTER TABLE volitional_patterns ADD COLUMN IF NOT EXISTS last_activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ))
            await conn.execute(text(
                "ALTER TABLE volitional_patterns ADD COLUMN IF NOT EXISTS decay_rate FLOAT DEFAULT 0.01"
            ))
            await conn.execute(text(
                "ALTER TABLE volitional_patterns ADD COLUMN IF NOT EXISTS reinforcement_rate FLOAT DEFAULT 0.05"
            ))
            # ✨ NEW Migration 006: Phase 2.2 Volitional Spec (Fuel & Target)
            await conn.execute(text(
                "ALTER TABLE volitional_patterns ADD COLUMN IF NOT EXISTS fuel FLOAT DEFAULT 1.0"
            ))
            await conn.execute(text(
                "ALTER TABLE volitional_patterns ADD COLUMN IF NOT EXISTS target VARCHAR(255) DEFAULT NULL"
            ))
            await conn.execute(text(
                "ALTER TABLE volitional_patterns ADD COLUMN IF NOT EXISTS turns_active INTEGER DEFAULT 0"
            ))
            await conn.execute(text(
                "ALTER TABLE volitional_patterns ADD COLUMN IF NOT EXISTS last_novelty_turn INTEGER DEFAULT 0"
            ))
            # ✨ NEW Migration 007: Energy Cost
            await conn.execute(text(
                "ALTER TABLE volitional_patterns ADD COLUMN IF NOT EXISTS energy_cost FLOAT DEFAULT 0.1"
            ))
            print("[DB Init] ✅ Volitional System fields added (Migration 006+007)")
        except Exception as e:
            print(f"[DB Init] Schema update (volitional 006+007): {e}")

        # ✨ NEW Migration 008: Stage 1 - TEC/Taxonomy Fields
        try:
            await conn.execute(text(
                "ALTER TABLE volitional_patterns ADD COLUMN IF NOT EXISTS intent_category VARCHAR(50) DEFAULT 'Casual'"
            ))
            await conn.execute(text(
                "ALTER TABLE volitional_patterns ADD COLUMN IF NOT EXISTS topic_engagement FLOAT DEFAULT 1.0"
            ))
            await conn.execute(text(
                "ALTER TABLE volitional_patterns ADD COLUMN IF NOT EXISTS base_decay_rate FLOAT DEFAULT 0.12"
            ))
            await conn.execute(text(
                "ALTER TABLE volitional_patterns ADD COLUMN IF NOT EXISTS complexity_modifier FLOAT DEFAULT 1.0"
            ))
            await conn.execute(text(
                "ALTER TABLE volitional_patterns ADD COLUMN IF NOT EXISTS emotional_load FLOAT DEFAULT 0.0"
            ))
            await conn.execute(text(
                "ALTER TABLE volitional_patterns ADD COLUMN IF NOT EXISTS recovery_rate FLOAT DEFAULT 0.05"
            ))
            # Fix legacy fields: make nullable
            await conn.execute(text(
                "ALTER TABLE volitional_patterns ALTER COLUMN resolution_strategy DROP NOT NULL"
            ))
            await conn.execute(text(
                "ALTER TABLE volitional_patterns ALTER COLUMN action_taken DROP NOT NULL"
            ))
            print("[DB Init] ✅ Stage 1: TEC/Taxonomy fields added (Migration 008)")
        except Exception as e:
            print(f"[DB Init] Schema update (volitional 008 - TEC/Taxonomy): {e}")

# --- Helper Methods ---

async def log_turn_metrics(
    user_id: int, 
    session_id: str, 
    metrics: Dict[str, Any]
):
    """
    Log metrics for a single turn into rcore_metrics table.
    """
    try:
        async with AsyncSessionLocal() as session:
            # Extract top-level columns
            affective_triggers = metrics.get("affective_triggers_detected", 0)
            sentiment_used = metrics.get("sentiment_context_used", False)
            latency = metrics.get("latency_ms", 0)
            
            # Everything else goes to payload
            payload_data = {
                k: v for k, v in metrics.items() 
                if k not in ["affective_triggers_detected", "sentiment_context_used", "latency_ms"]
            }
            
            new_metric = MetricsModel(
                event_type="core_turn",
                user_id=user_id,
                session_id=session_id,
                latency_ms=latency,
                affective_triggers_detected=affective_triggers,
                sentiment_context_used=sentiment_used,
                payload=payload_data
            )
            
            session.add(new_metric)
            await session.commit()
    except Exception as e:
        print(f"[Metrics] Failed to log turn metrics: {e}")

# --- LLM Raw Response Logging (Circular Buffer) ---

async def log_llm_raw_response(
    prompt_type: str,
    raw_request: str,
    raw_response: str,
    parse_status: str,
    error_message: Optional[str] = None,
    user_id: str = "system",
    session_id: Optional[str] = None,
    max_records: int = 20
):
    """
    Логирует сырой ответ LLM в БД (circular buffer).
    """
    # Проверяем флаг из settings
    if not settings.ENABLE_LLM_RAW_LOGGING:
        return
    
    try:
        # Обрезаем длинные строки для экономии места
        raw_request_truncated = raw_request[:2000] if raw_request else None
        raw_response_truncated = raw_response[:5000] if raw_response else None
        
        async with engine.begin() as conn:
            # Вставляем новую запись
            await conn.execute(text("""
                INSERT INTO llm_raw_responses 
                (user_id, session_id, prompt_type, raw_request, raw_response, parse_status, error_message)
                VALUES (:user_id, :session_id, :prompt_type, :raw_request, :raw_response, :parse_status, :error_message)
            """), {
                "user_id": user_id,
                "session_id": session_id,
                "prompt_type": prompt_type,
                "raw_request": raw_request_truncated,
                "raw_response": raw_response_truncated,
                "parse_status": parse_status,
                "error_message": error_message
            })
            
            # Удаляем старые записи (circular buffer)
            await conn.execute(text("""
                DELETE FROM llm_raw_responses
                WHERE id NOT IN (
                    SELECT id FROM llm_raw_responses
                    ORDER BY timestamp DESC
                    LIMIT :max_records
                )
            """), {"max_records": max_records})
            
    except Exception as e:
        # Silent fail - не ломаем основной flow, если что-то пошло не так
        print(f"[LLM Raw Logging] Failed to log (non-critical): {e}")
