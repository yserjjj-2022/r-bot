import os
from typing import List, Dict, Optional, Any, Union
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

# --- Enums ---

class AgentType(str, Enum):
    INTUITION = "intuition_system1"
    AMYGDALA = "amygdala_safety"
    STRIATUM = "striatum_reward"
    PREFRONTAL = "prefrontal_logic"
    SOCIAL = "social_cortex"

class ProcessingMode(str, Enum):
    FAST_PATH = "fast_path"
    SLOW_PATH = "slow_path"

class MemoryType(str, Enum):
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    VOLITIONAL = "volitional"

# --- Personality & Config ---

class PersonalitySliders(BaseModel):
    """
    Настройки характера бота (0.0 - 1.0)
    """
    empathy_bias: float = Field(0.5, description="Приоритет чувств vs эффективности")
    dominance_level: float = Field(0.5, description="Лидерство vs Подстройка")
    risk_tolerance: float = Field(0.5, description="Авантюризм vs Осторожность")
    pace_setting: float = Field(0.5, description="Быстрый (Intuition) vs Медленный (Logic)")
    neuroticism: float = Field(0.1, description="Степень случайности/эмоциональности")

class BotConfig(BaseModel):
    character_id: str
    name: str
    gender: str = "Neutral"
    sliders: PersonalitySliders
    core_values: List[str]
    
    # ✨ Experimental flag for Unified Council
    use_unified_council: bool = Field(
        default=False, 
        description="Использовать единый Council Report для всех агентов (включая Intuition)"
    )
    # REMOVED: intuition_gain - теперь используется pace_setting для обоих режимов

# --- Hormonal / Mood System ---

class MoodVector(BaseModel):
    """
    Модель VAD (Valence, Arousal, Dominance)
    Диапазон: от -1.0 до +1.0
    """
    valence: float = Field(0.0, ge=-1.0, le=1.0, description="Негатив (-1) <-> Позитив (+1)")
    arousal: float = Field(0.0, ge=-1.0, le=1.0, description="Спокойствие (-1) <-> Возбуждение (+1)")
    dominance: float = Field(0.0, ge=-1.0, le=1.0, description="Покорность (-1) <-> Контроль (+1)")

    def __str__(self):
        return f"V:{self.valence:.2f} A:{self.arousal:.2f} D:{self.dominance:.2f}"

# --- Inputs ---

class IncomingMessage(BaseModel):
    """
    Унифицированный формат входящего сообщения от Hub
    """
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: int
    session_id: str
    text: str
    timestamp: datetime = Field(default_factory=datetime.now)
    channel_meta: Dict[str, Any] = Field(default_factory=dict)

# --- Memory Structures ---

class SemanticTriple(BaseModel):
    """
    Единица семантической памяти (Knowledge Graph)
    Subject -> Predicate -> Object
    """
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0
    source_message_id: Optional[str] = None
    # Affective extension placeholder
    sentiment: Optional[Dict[str, float]] = None 

class EpisodicAnchor(BaseModel):
    """
    Единица эпизодической памяти (Цитата-Якорь)
    """
    raw_text: str
    embedding_ref: Optional[str] = None 
    emotion_score: float # 0.0 - 1.0
    tags: List[str]
    ttl_days: int = 30 

class VolitionalPattern(BaseModel):
    """
    Паттерн поведения (Micro-Graph)
    """
    trigger: str
    impulse: str
    goal: Optional[str] = None
    conflict_detected: bool
    resolution_strategy: str
    action_taken: str

# --- Internal Agent Signals ---

class AgentSignal(BaseModel):
    """
    Голос одного агента в Парламенте
    """
    agent_name: AgentType
    score: float = Field(..., ge=0, le=10, description="Сила сигнала 0-10")
    rationale_short: str
    confidence: float = Field(..., ge=0, le=1.0)
    latency_ms: int
    # Agent's influence on mood
    mood_impact: Optional[MoodVector] = None
    # Style modulation instruction (Adverb)
    style_instruction: Optional[str] = None

# --- Output ---

class CoreAction(BaseModel):
    """
    Действие, которое должен выполнить Hub
    """
    type: str # "send_text", "show_keyboard", "wait"
    payload: Dict[str, Any]
    
class CoreResponse(BaseModel):
    """
    Финальный ответ ядра
    """
    response_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    actions: List[CoreAction]
    
    # Meta for debugging & logging
    internal_stats: Dict[str, Any] = Field(default_factory=dict) 
    winning_agent: Optional[AgentType] = None
    current_mood: Optional[MoodVector] = None # <-- Added Mood State
    processing_mode: ProcessingMode
    memory_updates: Dict[str, int] = Field(default_factory=dict) 
