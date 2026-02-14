import math
from typing import List

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

def cosine_distance(v1: List[float], v2: List[float]) -> float:
    """
    Calculates Cosine Distance (1 - Similarity).
    Range: 0.0 (Identical) to 2.0 (Opposite).
    Returns 1.0 if vectors are empty or zero-magnitude.
    """
    if not v1 or not v2 or len(v1) != len(v2):
        return 1.0
    
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    
    if norm_a == 0.0 or norm_b == 0.0:
        return 1.0
        
    similarity = dot_product / (norm_a * norm_b)
    # Clamp to handle float precision errors
    similarity = max(-1.0, min(1.0, similarity))
    
    return 1.0 - similarity
