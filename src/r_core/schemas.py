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
    Biochemical internal state simulation.
    """
    cortisol: float = 0.2    # Stress (0.0 - 1.0)
    dopamine: float = 0.5    # Reward/Motivation
    oxytocin: float = 0.5    # Social Bonding
    serotonin: float = 0.5   # Mood Stability
    adrenaline: float = 0.1  # Acute Arousal (Fight/Flight)

    def __str__(self):
        return f"Cort:{self.cortisol:.2f} Dop:{self.dopamine:.2f} Oxy:{self.oxytocin:.2f} Ser:{self.serotonin:.2f} Adr:{self.adrenaline:.2f}"

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
    
    chaos_level: float = 0.0     # 0.0 (Stable) - 1.0 (Unpredictable) ✨ NEW
    
    # ✨ NEW: Active Inference Controls
    pred_threshold: float = 0.8  # Порог ошибки для активации Uncertainty (0.1 - 1.0)
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
    Updated for Phase 2.2 with Target & Fuel.
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
    
    # Legacy
    conflict_detected: bool = False
    resolution_strategy: str = ""
    action_taken: str = ""
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
