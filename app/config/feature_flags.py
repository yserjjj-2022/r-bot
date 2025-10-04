# app/config/feature_flags.py
# Feature Flags для поэтапного развертывания новых функций

class FeatureFlags:
    """
    Централизованное управление функциональностью.
    Позволяет включать/выключать функции без изменения кода.
    """
    
    # === ЭТАП 0: FOUNDATION ===
    ENABLE_AI_IMPORTANCE_ANALYSIS = False  # ИИ-анализ важности событий
    ENABLE_NEW_DB_FIELDS = True           # Новые поля в БД (уже созданы)
    
    # === СПРИНТ 1: ADVANCED TIMING ===  
    ENABLE_DELAYED_MESSAGES = False       # Отложенные сообщения
    ENABLE_TIMEOUTS = False               # Таймауты для узлов
    ENABLE_COOLDOWNS = False              # Кулдауны между действиями
    ENABLE_PERSISTENCE_TIMERS = False     # Сохранение таймеров при рестарте
    
    # === СПРИНТ 2: BEHAVIORAL EFFECTS ===
    ENABLE_AI_THINKING_DELAY = False      # ИИ "думает" перед ответом
    ENABLE_COMPLEXITY_SIMULATION = False  # Имитация сложности задач
    ENABLE_EMOTIONAL_PAUSES = False       # Эмоциональные паузы
    
    # === СПРИНТ 3: MEMORY MANAGEMENT ===
    ENABLE_SMART_CONTEXT = False          # Умное управление контекстом ИИ
    ENABLE_AI_SUMMARIZATION = False       # ИИ-суммаризация старых событий
    ENABLE_HIERARCHICAL_MEMORY = False    # Иерархическая память (важные + summaries)
    
    # === СПРИНТ 4: GROUP MECHANICS ===
    ENABLE_GROUP_RESEARCH = False         # Групповые исследования
    ENABLE_COMPETITIONS = False           # Соревнования между игроками
    ENABLE_COOPERATION = False            # Кооперативные игры
    ENABLE_AUCTIONS = False               # Аукционные механики
    
    @classmethod
    def is_enabled(cls, feature_name: str) -> bool:
        """Проверить включена ли функция"""
        return getattr(cls, feature_name, False)
    
    @classmethod  
    def enable_feature(cls, feature_name: str):
        """Включить функцию"""
        setattr(cls, feature_name, True)
        
    @classmethod
    def disable_feature(cls, feature_name: str):
        """Выключить функцию"""
        setattr(cls, feature_name, False)

# Удобные функции для проверки
def is_timing_enabled() -> bool:
    """Проверить включены ли timing механики"""
    return (FeatureFlags.ENABLE_DELAYED_MESSAGES or 
            FeatureFlags.ENABLE_TIMEOUTS or 
            FeatureFlags.ENABLE_COOLDOWNS)

def is_ai_enhanced() -> bool:
    """Проверить включены ли ИИ улучшения"""
    return (FeatureFlags.ENABLE_AI_IMPORTANCE_ANALYSIS or
            FeatureFlags.ENABLE_AI_THINKING_DELAY or
            FeatureFlags.ENABLE_SMART_CONTEXT)

def is_group_mode() -> bool:
    """Проверить включены ли групповые механики"""
    return (FeatureFlags.ENABLE_GROUP_RESEARCH or
            FeatureFlags.ENABLE_COMPETITIONS or
            FeatureFlags.ENABLE_COOPERATION)
