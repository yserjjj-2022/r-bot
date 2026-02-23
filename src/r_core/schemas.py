from typing import List, Dict, Optional, Any, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

# --- Enums ---

class AgentType(str, Enum):
    INTUITION = "Intuition"
    AMYGDALA = "Amygdala"
    PREFRONTAL = "Prefrontal"
    SOCIAL = "Social"
    STRIATUM = "Striatum"
    UNCERTAINTY = "Uncertainty"  # ✨ NEW AGENT
    HIPPOCAMPUS = "Hippocampus" # System Agent

class ProcessingMode(str, Enum):
    FAST_PATH = "FAST"   # Zombie/Reflex
    SLOW_PATH = "SLOW"   # Cortical/Council

# --- Value Objects ---

class MoodVector(BaseModel):
    valence: float = 0.0   # -1.0 (Negative) to 1.0 (Positive)
    arousal: float = 0.0   # -1.0 (Calm) to 1.0 (Excited)
    dominance: float = 0.0 # -1.0 (Submissive) to 1.0 (Dominant)

    def __str__(self):
        return f"V:{self.valence:.2f} A:{self.arousal:.2f} D:{self.dominance:.2f}"

class HormonalState(BaseModel):
    """
    Biochemical internal state simulation (Lovheim Cube).
    Updated to match neuromodulation.py keys.
    """
    cort: float = 0.1     # Cortisol (Stress)
    da: float = 0.5       # Dopamine (Reward/Motivation)
    ht: float = 0.5       # Serotonin (5-HT, Mood Stability)
    ne: float = 0.1       # Norepinephrine (Arousal/Vigilance)
    oxytocin: float = 0.5 # Social Bonding (Extra axis)
    
    last_update: datetime = Field(default_factory=datetime.utcnow) # ✨ NEW

    def __str__(self):
        return f"NE:{self.ne:.2f} DA:{self.da:.2f} 5HT:{self.ht:.2f} CORT:{self.cort:.2f}"

# --- Configuration Schemas ---

class PersonalitySliders(BaseModel):
    """
    🎛️ Real-time Controls for R-Core.
    """
    risk_tolerance: float = 0.5  # 0.0 (Safe) - 1.0 (Risky)
    empathy_bias: float = 0.5    # 0.0 (Cold) - 1.0 (Warm)
    curiosity_level: float = 0.5 # 0.0 (Focused) - 1.0 (Explorative)
    pace_setting: float = 0.5    # 0.0 (Slow/Deep) - 1.0 (Fast/Reflex)
    
    # ✨ Legacy but required for UI (app_streamlit.py)
    dominance_level: float = 0.5 # 0.0 (Submissive) - 1.0 (Assertive)
    neuroticism: float = 0.1     # 0.0 (Stable) - 1.0 (Neurotic)
    
    chaos_level: float = 0.0     # 0.0 (Stable) - 1.0 (Unpredictable) ✨ NEW
    
    # ✨ NEW: Active Inference Controls
    pred_threshold: float = 0.8  # Порог ошибки для активации Uncertainty (0.1 - 1.0)
    pred_sensitivity: float = 10.0 # Резкость реакции (k)
    persistence: float = 0.5     # Воля/Упрямство (0.0 - 1.0)
    learning_speed: float = 0.5  # Скорость обучения (Plasticity)

class BotConfig(BaseModel):
    name: str = "R-Bot"
    gender: str = "Neutral" # ✨ NEW
    sliders: PersonalitySliders = Field(default_factory=PersonalitySliders)
    system_prompt_override: Optional[str] = None
    # Experimental Flags
    intuition_gain: float = 1.0
    use_unified_council: bool = False

# --- Memory & Context Schemas ---

class SemanticTriple(BaseModel):
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0
    source_message_id: Optional[str] = None
    sentiment: Optional[Dict[str, Any]] = None # ✨ NEW: Affective ToM
    embedding: Optional[List[float]] = None # ✨ NEW: Embedding

class EpisodicAnchor(BaseModel):
    raw_text: str
    emotion_score: float = 0.0
    tags: List[str] = []
    ttl_days: int = 30
    embedding_ref: Optional[str] = None 

class VolitionalPattern(BaseModel):
    """
    Represents a learned behavioral pattern or habit.
    Updated for Stage 1: Taxonomy & TEC Decay.
    """
    id: Optional[int] = None
    trigger: str
    impulse: str
    target: Optional[str] = None # ✨ NEW (Optional for backward compat)
    goal: Optional[str] = None
    
    # State
    intensity: float = 0.5
    fuel: float = 1.0       # ✨ NEW (Optional default handled in DB)
    learned_delta: float = 0.0
    
    turns_active: int = 0       # ✨ NEW
    last_novelty_turn: int = 0  # ✨ NEW
    
    is_active: bool = True
    
    # Config
    decay_rate: float = 0.01
    reinforcement_rate: float = 0.05
    energy_cost: float = 0.1 # ✨ NEW: Cost per turn
    
    # Legacy (Data Contract: nullable or safe defaults)
    conflict_detected: bool = False
    resolution_strategy: Optional[str] = None
    action_taken: Optional[str] = None
    
    # === Stage 1: TEC/Taxonomy Fields ===
    intent_category: str = "Casual"  # Phatic, Casual, Narrative, Deep, Task
    topic_engagement: float = 1.0  # TEC: 0.0-1.0
    base_decay_rate: float = 0.12  # Nature-based decay
    complexity_modifier: float = 1.0  # Topic complexity factor
    emotional_load: float = 0.0  # Emotional intensity
    recovery_rate: float = 0.05  # TEC recovery rate
    
    last_activated_at: Optional[datetime] = None

# --- Pipeline IO ---

class IncomingMessage(BaseModel):
    user_id: int
    session_id: str = "default"
    text: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    message_id: str

class AgentSignal(BaseModel):
    """
    Standardized output from any agent (Council or Unified).
    """
    agent_name: AgentType
    score: float             # 0.0 - 10.0
    rationale_short: str     # 1-2 sentences
    confidence: float = 0.5  # 0.0 - 1.0
    latency_ms: int = 0
    style_instruction: Optional[str] = None # ✨ NEW: Adverbial instruction

class CoreAction(BaseModel):
    type: str # "send_text", "wait", "search", "function_call"
    payload: Dict[str, Any]

class CoreResponse(BaseModel):
    actions: List[CoreAction]
    winning_agent: AgentType
    current_mood: MoodVector
    current_hormones: Optional[HormonalState] = None
    processing_mode: ProcessingMode
    internal_stats: Dict[str, Any] = {}
