import math
from typing import List, Union, Optional

# Expected embedding dimension (VseGPT text-embedding-3-small)
EXPECTED_EMBEDDING_DIM = 1536

def cosine_distance(v1: List[float], v2: List[float]) -> float:
    """
    Computes cosine distance between two vectors.
    Returns: float between 0.0 (identical) and 2.0 (opposite).
    """
    if not v1 or not v2: 
        return 1.0
        
    # ✨ FIX: Validate dimensions match
    if len(v1) != len(v2):
        print(f"[ cosine_distance] Dimension mismatch: {len(v1)} vs {len(v2)}, returning 1.0")
        return 1.0
    
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_a = sum(a * a for a in v1) ** 0.5
    norm_b = sum(b * b for b in v2) ** 0.5
    
    if norm_a == 0 or norm_b == 0:
        return 1.0
        
    similarity = dot_product / (norm_a * norm_b)
    # Clip to avoid float errors slightly outside [-1, 1]
    similarity = max(-1.0, min(1.0, similarity))
    
    return 1.0 - similarity


def validate_embedding(emb: Optional[List[float]], context: str = "") -> Optional[List[float]]:
    """Validate embedding dimension matches expected size."""
    if emb is None:
        return None
    
    actual_dim = len(emb)
    if actual_dim != EXPECTED_EMBEDDING_DIM:
        print(f"[validate_embedding] {context}: Invalid dimension {actual_dim}, expected {EXPECTED_EMBEDDING_DIM}")
        return None
    
    return emb

def sigmoid(x: float, k: float = 10.0, mu: float = 0.5) -> float:
    """
    S-curve function for biological sensitivity modeling.
    x: Input value
    k: Steepness (growth rate). Higher = sharper transition.
    mu: Midpoint (x-value where y=0.5). The threshold.
    """
    try:
        return 1 / (1 + math.exp(-k * (x - mu)))
    except OverflowError:
        return 0.0 if x < mu else 1.0

def is_phatic_message(text: str) -> bool:
    """
    Detects short, non-informational messages that shouldn't trigger heavy logic.
    """
    phatic_set = {
        "да", "нет", "ага", "угу", "ок", "хорошо", "спасибо", "привет", "пока",
        "yes", "no", "ok", "okay", "thanks", "hello", "hi", "bye", "cool"
    }
    
    clean_text = "".join(ch for ch in text.lower() if ch.isalnum() or ch.isspace()).strip()
    
    if clean_text in phatic_set:
        return True
    
    # Also catch very short generic phrases like "ну да", "так и есть"
    if len(clean_text.split()) <= 2 and len(clean_text) < 10:
        return True
        
    return False
