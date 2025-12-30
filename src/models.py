from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

# --- Enums (Fixed Vocabularies) ---

class VolitionalStepType(str, Enum):
    """The 8 steps of the Synthetic Volitional Model v2.0"""
    CONTEXT = "CONTEXT"
    TRIGGER = "TRIGGER"
    DOUBLE_ACTIVATION = "DOUBLE_ACTIVATION" # Impulse vs Goal
    CONFLICT = "CONFLICT"
    REGULATION = "REGULATION"               # Inhibition & Check
    ARBITRATION = "ARBITRATION"
    ACTION = "ACTION"
    REFLECTION = "REFLECTION"

class ComBCategory(str, Enum):
    """COM-B Model Categories for tagging context factors"""
    CAPABILITY_PHYSICAL = "CAPABILITY_PHYSICAL"       # Strength, skill, stamina
    CAPABILITY_PSYCHOLOGICAL = "CAPABILITY_PSYCHOLOGICAL" # Knowledge, memory, attention, logic
    OPPORTUNITY_PHYSICAL = "OPPORTUNITY_PHYSICAL"     # Time, resources, location
    OPPORTUNITY_SOCIAL = "OPPORTUNITY_SOCIAL"         # Norms, pressure, support
    MOTIVATION_AUTOMATIC = "MOTIVATION_AUTOMATIC"     # Emotion, habit, impulse (System 1)
    MOTIVATION_REFLECTIVE = "MOTIVATION_REFLECTIVE"   # Planning, beliefs, goals (System 2)
    STATE_PHYSIO = "STATE_PHYSIO"                     # Hunger, fatigue, pain (Added for 'State')

class InfluenceType(str, Enum):
    """Direction of influence"""
    FACILITATOR = "FACILITATOR" # Helps the step succeed (Green arrow)
    BARRIER = "BARRIER"         # Hinders the step (Red arrow)

# --- Core Data Structures ---

class ContextFactor(BaseModel):
    """
    Represents an arrow from the Context (Ribs) to the Process (Spine).
    Example: 'Fatigue (State) -> Hinders Regulation'
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    description: str = Field(..., description="Short text description of the factor, e.g., 'High fatigue'")
    category: ComBCategory = Field(..., description="Which COM-B bucket this falls into")
    influence: InfluenceType = Field(..., description="Does it help or hurt the target step?")
    strength: float = Field(..., ge=0.0, le=1.0, description="Estimated impact strength (0.0 to 1.0)")

class VolitionalNode(BaseModel):
    """
    A single node in the 8-step spine.
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    step_index: int = Field(..., ge=1, le=8, description="Order in the sequence (1-8)")
    step_type: VolitionalStepType
    
    # Specific for step 3 (Double Activation) to distinguish Impulse from Goal
    sub_type: Optional[str] = Field(None, description="E.g., 'IMPULSE' or 'GOAL' for step 3")
    
    description: str = Field(..., description="What actually happened in this step")
    
    # The 'Ribs': Context factors affecting this specific node
    modifiers: List[ContextFactor] = Field(default_factory=list, description="List of context factors influencing this step")
    
    # Vector embedding placeholder (not stored in JSON sent to LLM, but used in DB)
    embedding: Optional[List[float]] = Field(None, exclude=True)

class VolitionalGraph(BaseModel):
    """The complete structure of one behavioral episode"""
    nodes: List[VolitionalNode]

class Episode(BaseModel):
    """
    The top-level unit of analysis.
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    source_text: str = Field(..., description="Original interview text chunk")
    
    # Analysis results
    graph: VolitionalGraph
    relevance_score: float = Field(0.0, description="Relevance to the research domain (0-1)")
    
    # Metadata for clustering
    context_summary: Optional[str] = Field(None, description="Aggregated text of all Context Factors")
    
    class Config:
        use_enum_values = True
