import math
import re
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


def sanitize_bot_history(text: str, intimacy_score: float = 0.0) -> str:
    """
    Removes roleplay formatting and conditionally removes diminutives from bot messages 
    before injecting them into the LLM prompt context.
    """
    if not text:
        return text
        
    # 1. ALWAYS remove anything between asterisks (e.g., *улыбается*)
    text = re.sub(r'\*.*?\*', '', text)
    
    # 2. ALWAYS remove anything between parentheses if it looks like an action (e.g., (улыбается))
    text = re.sub(r'\(.*?\)', '', text)
    
    # 3. ALWAYS remove common action verbs
    actions_to_remove = [
        "смеется", "улыбается", "подмигивает", "вздыхает", 
        "кивает", "смеется и подмигивает", "довольно улыбается",
        "smiles", "laughs", "winks", "nods", "sighs"
    ]
    for action in actions_to_remove:
        pattern = re.compile(rf'\b{re.escape(action)}\b', re.IGNORECASE)
        text = pattern.sub('', text)
        
    # 4. CONDITIONAL: Replace/Remove diminutives if trust is low/medium
    if intimacy_score < 0.8:
        diminutives = ["Сереженька", "Сережа", "Сашенька", "Сергеюшка", "Андрюшка", "Петрушка"]
        for dim in diminutives:
            pattern = re.compile(rf'\b{re.escape(dim)}\b', re.IGNORECASE)
            text = pattern.sub('дружище', text)
            
    # Clean up double spaces left by replacements
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def calculate_new_intimacy(
    current_score: float,
    turn_metrics: dict,
    last_interaction_timestamp: Optional[str] = None
) -> float:
    """
    Calculates the new intimacy score based on turn events.
    
    Growth:
    - +0.005 per conversation turn (base growth)
    - +0.02 for each affective trigger detected (emotional bonding)
    
    Decay:
    - -0.05 if user hasn't interacted for > 3 days
    - -0.1 if Rage/Panic archetype triggered (conflict/toxicity)
    
    Args:
        current_score: Current intimacy_score (0.0 to 1.0)
        turn_metrics: Dict with keys:
            - affective_triggers_detected: int
            - hormonal_archetype: str (e.g., "RAGE", "PANIC", "FEAR", "CALM")
            - user_emotion_score: float (0.0 to 1.0)
            - prediction_error: float
        last_interaction_timestamp: ISO timestamp string of last interaction
    
    Returns:
        New intimacy score (capped between 0.0 and 1.0)
    """
    new_score = current_score
    
    # 1. Base growth per interaction
    new_score += 0.005
    
    # 2. Emotional bonding (Affective ToM triggers)
    affective_triggers = turn_metrics.get("affective_triggers_detected", 0)
    if affective_triggers > 0:
        new_score += 0.02 * affective_triggers
    
    # 3. Bonus for positive emotion score
    user_emotion = turn_metrics.get("user_emotion_score", 0.0)
    if user_emotion > 0.6:
        new_score += 0.01
    
    # 4. Penalty for negative archetypes (conflict/toxicity)
    hormonal_archetype = turn_metrics.get("hormonal_archetype", "")
    if hormonal_archetype in ["RAGE", "PANIC"]:
        new_score -= 0.1
        print(f"[Intimacy] Penalty applied for archetype: {hormonal_archetype}")
    
    # 5. Time-based decay (if no interaction for > 3 days)
    if last_interaction_timestamp:
        from datetime import datetime, timedelta
        try:
            last_ts = datetime.fromisoformat(last_interaction_timestamp.replace("Z", "+00:00"))
            now = datetime.now(last_ts.tzinfo)
            days_diff = (now - last_ts).total_seconds() / 86400
            if days_diff > 3:
                decay = 0.05 * (days_diff - 3)  # Additional decay per extra day
                new_score -= decay
                print(f"[Intimacy] Time decay: {days_diff:.1f} days, penalty: {decay:.3f}")
        except Exception as e:
            print(f"[Intimacy] Failed to parse timestamp: {e}")
    
    # Cap between 0.0 and 1.0
    return max(0.0, min(1.0, new_score))


def get_trust_stage(intimacy_score: float) -> str:
    """
    Returns the trust stage string based on intimacy score.
    
    0.0 - 0.3: stranger
    0.3 - 0.7: acquaintance  
    0.7 - 1.0: friend
    """
    if intimacy_score < 0.3:
        return "stranger"
    elif intimacy_score < 0.7:
        return "acquaintance"
    else:
        return "friend"


def get_intimacy_instruction(intimacy_score: float) -> str:
    """
    Returns dynamic intimacy instruction for LLM based on score.
    """
    stage = get_trust_stage(intimacy_score)
    
    if stage == "stranger":
        return (
            "Keep emotional distance. Be polite, formal, and objective. "
            "Do not act overly familiar. Use 'Вы' or very respectful 'Ты'."
        )
    elif stage == "acquaintance":
        return (
            "Act as a friendly acquaintance. You can be warm and casual, "
            "but respect boundaries. Use 'Ты' naturally."
        )
    else:  # friend
        return (
            "Act as a close, trusted friend. Be highly empathetic, emotionally open, "
            "and deeply supportive. Use 'Ты' and show genuine care."
        )
