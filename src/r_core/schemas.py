from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

class AgentType(str, Enum):
    # Core Parliament
    AMYGDALA = "amygdala_safety"
    INTUITION = "intuition_system1"
    PREFRONTAL = "prefrontal_logic"
    SOCIAL = "social_cortex"
    STRIATUM = "striatum_reward"
    
    # Special Agents
    UNCERTAINTY = "uncertainty_agent"  # New: Handles Lost state (Predictive Processing)
    
    # Meta
    COUNCIL = "council_integrator"

@dataclass
class AgentSignal:
    """
    Standard output from any cognitive agent.
    """
    agent_name: AgentType
    score: float  # 0.0 to 10.0
    rationale_short: str
    confidence: float # 0.0 to 1.0 (internal confidence)
    latency_ms: int = 0
    style_instruction: Optional[str] = None # E.g., "...but keep it brief"

@dataclass
class IncomingMessage:
    """
    Standard input wrapper.
    """
    text: str
    user_id: int
    session_id: str
    platform: str = "telegram"
    timestamp: float = 0.0
    metadata: Dict = field(default_factory=dict)

@dataclass
class PersonalitySliders:
    """
    Dynamic configuration of the bot's current state.
    Controlled by Neuro-Modulation System.
    """
    risk_tolerance: float = 0.5   # 0.0 (Coward) - 1.0 (Reckless) -> Amygdala/Striatum
    empathy_bias: float = 0.5     # 0.0 (Cold) - 1.0 (Bleeding Heart) -> Social
    pace_setting: float = 0.5     # 0.0 (Reflective) - 1.0 (Fast/Impulsive) -> Prefrontal/Intuition
    curiosity_drive: float = 0.5  # 0.0 (Bored) - 1.0 (Wonder) -> Striatum

    def to_dict(self) -> Dict[str, float]:
        return {
            "risk_tolerance": self.risk_tolerance,
            "empathy_bias": self.empathy_bias,
            "pace_setting": self.pace_setting,
            "curiosity_drive": self.curiosity_drive
        }

# --- Memory Schemas ---

@dataclass
class SemanticTriple:
    """
    Fact: (Subject, Predicate, Object)
    Example: (User, LIKES, Python)
    """
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0
    source_message_id: Optional[str] = None

@dataclass
class EpisodicAnchor:
    """
    Key memory anchor for narrative identity.
    """
    anchor_id: str
    text: str
    embedding: List[float]
    emotional_tags: List[str] # e.g. ["shame", "triumph"]
    amygdala_intensity: float # 0.0 - 1.0
    created_at: str
