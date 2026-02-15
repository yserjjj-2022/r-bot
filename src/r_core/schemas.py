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
    UNCERTAINTY = "uncertainty_agent"  # Predictive Processing Handler

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
    # Legacy Sliders (still used by Agents?)
    empathy_bias: float = Field(0.5, description="Приоритет чувств vs эффективности")
    dominance_level: float = Field(0.5, description="Лидерство vs Подстройка")
    risk_tolerance: float = Field(0.5, description="Авантюризм vs Осторожность")
    neuroticism: float = Field(0.1, description="Степень случайности/эмоциональности")
    
    # === Dashboard Controls (Homeostasis) ===
    chaos_level: float = Field(0.2, ge=0.0, le=1.0, description="Стабильность vs Хаос (Uncertainty Boost)")
    learning_speed: float = Field(0.5, ge=0.0, le=1.0, description="Скорость обучения (RL Rate)")
    persistence: float = Field(0.5, ge=0.0, le=1.0, description="Рассеянность vs Упорство (Fuel Restoration)")

    # === Prediction Error (can be derived from Chaos Level) ===
    pred_threshold: float = Field(0.65, ge=0.1, le=1.0, description="Порог хорошей ошибки (mu)")
    pred_sensitivity: float = Field(10.0, ge=1.0, le=20.0, description="Чувствительность к ошибке (k)")

class BotConfig(BaseModel):
    character_id: str
    name: str
    gender: str = "Neutral"
    sliders: PersonalitySliders
    core_values: List[str]
    
    use_unified_council: bool = Field(
        default=False, 
        description="Использовать единый Council Report для всех агентов (включая Intuition)"
    )
    intuition_gain: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        description="Множитель для Intuition Agent score (0.0 = отключен, 1.0 = норма, 2.0 = усилен)"
    )

# --- Hormonal / Mood System ---

class HormonalState(BaseModel):
    """
    Биохимическое состояние ("Большая Четверка")
    Диапазон: 0.0 - 1.0
    """
    ne: float = Field(0.1, ge=0.0, le=1.0, description="Norepinephrine (Arousal/Focus)")
    da: float = Field(0.3, ge=0.0, le=1.0, description="Dopamine (Motivation/Action)")
    ht: float = Field(0.5, ge=0.0, le=1.0, description="Serotonin (Stability/Calm)")
    cort: float = Field(0.1, ge=0.0, le=1.0, description="Cortisol (Stress/Defense)")
    last_update: datetime = Field(default_factory=datetime.now)

    def __str__(self):
        return f"NE:{self.ne:.2f} DA:{self.da:.2f} 5HT:{self.ht:.2f} CORT:{self.cort:.2f}"

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
    sentiment: Optional[Dict[str, float]] = None
    embedding: Optional[List[float]] = None

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
    Updated for Phase 2.2 (Attention * Persistence)
    """
    # === Core ===
    trigger: str  # Context Condition (e.g. "time:late_night")
    impulse: str  # Behavioral Response (e.g. "deep_talk")
    target: str   # Object of Focus (e.g. "topic:Python")
    
    # === Dynamics ===
    intensity: float = Field(0.5, ge=0.0, le=1.0)
    fuel: float = Field(1.0, ge=0.0, le=1.0)
    intrinsic_value: float = Field(0.5, ge=0.0, le=1.0)
    depletion_rate: float = Field(0.05, ge=0.0, le=1.0)
    
    # === State ===
    turns_active: int = 0
    last_novelty_turn: int = 0
    learned_delta: float = Field(0.0, ge=-1.0, le=1.0)
    
    # === Legacy / Optional ===
    goal: Optional[str] = None
    conflict_detected: bool = False
    resolution_strategy: Optional[str] = None
    action_taken: Optional[str] = None

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
    mood_impact: Optional[MoodVector] = None
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
    
    internal_stats: Dict[str, Any] = Field(default_factory=dict) 
    winning_agent: Optional[AgentType] = None
    current_mood: Optional[MoodVector] = None 
    current_hormones: Optional[HormonalState] = None 
    processing_mode: ProcessingMode
    memory_updates: Dict[str, int] = Field(default_factory=dict) 
