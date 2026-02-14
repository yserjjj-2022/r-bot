from typing import List

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
    
    Used to skip Predictive Processing updates:
    - "Hi" -> No prediction error update.
    - "Ok" -> No prediction error update.
    - "Tell me about Python" -> Update PE.
    """
    if not text:
        return True
        
    cleaned = text.strip().lower()
    
    # 1. Check length (too short to be meaningful for embedding comparison)
    if len(cleaned) < 5 and cleaned not in PHATIC_PHRASES:
        # e.g. "lol", "?", "hmm"
        return True
        
    # 2. Check exact matches in phatic set
    if cleaned in PHATIC_PHRASES:
        return True
        
    # 3. Check simple emoji-only messages
    # (A simplified check, can be improved with regex if needed)
    if all(char in PHATIC_PHRASES for char in cleaned.split()):
         return True
         
    return False
