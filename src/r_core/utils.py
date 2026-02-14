from typing import List
import math

PHATIC_PHRASES = {
    "привет", "здравствуй", "добрый день", "доброе утро", "добрый вечер", "хай", "ку",
    "пока", "до свидания", "удачи", "спокойной ночи",
    "спасибо", "спс", "благодарю", "сяп",
    "пожалуйста", "пжл",
    "ок", "хорошо", "ладно", "ага", "угу", "да", "нет",
    "ясно", "понятно", "круто", "класс",
    "👍", "👋", "🙂", "👌", "🙏", "❤️"
}

def is_phatic_message(text: str) -> bool:
    """
    Check if the message is purely phatic (social lubricant) or too short to carry semantic weight.
    """
    if not text:
        return True
        
    cleaned = text.strip().lower()
    
    # 1. Check length (too short to be meaningful for embedding comparison)
    if len(cleaned) < 5 and cleaned not in PHATIC_PHRASES:
        return True
        
    # 2. Check exact matches in phatic set
    if cleaned in PHATIC_PHRASES:
        return True
        
    # 3. Check simple emoji-only messages
    if all(char in PHATIC_PHRASES for char in cleaned.split()):
         return True
         
    return False

def cosine_distance(v1: List[float], v2: List[float]) -> float:
    """
    Calculate Cosine Distance between two vectors (1 - Cosine Similarity).
    
    Returns:
        0.0 = Identical
        1.0 = Orthogonal (Unrelated)
        2.0 = Opposite
    """
    if not v1 or not v2 or len(v1) != len(v2):
        return 1.0 # Maximum error if vectors are invalid
        
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_v1 = math.sqrt(sum(a * a for a in v1))
    norm_v2 = math.sqrt(sum(b * b for b in v2))
    
    if norm_v1 == 0 or norm_v2 == 0:
        return 1.0
        
    similarity = dot_product / (norm_v1 * norm_v2)
    
    # Clamp to [-1, 1] to avoid floating point errors
    similarity = max(-1.0, min(1.0, similarity))
    
    return 1.0 - similarity
