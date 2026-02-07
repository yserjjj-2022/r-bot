"""
Поведенческие коэффициенты для R-Core Kernel.

Все пороги и модификаторы вынесены в конфигурацию для удобной калибровки.
Можно переопределить через переменные окружения.
"""

import os
from typing import Dict
from dataclasses import dataclass, field


@dataclass
class PredictionErrorThresholds:
    """
    Пороги для Empathy Alignment (= 1 - Prediction Error).
    
    Диапазоны:
    - in_sync: PE < этого значения → бот в потоке с пользователем
    - puzzled: PE между in_sync и lost → лёгкая озадаченность
    - lost: PE >= этого значения → бот потерял нить диалога
    """
    in_sync: float = field(
        default_factory=lambda: float(os.getenv("PE_THRESHOLD_IN_SYNC", "0.3"))
    )
    lost: float = field(
        default_factory=lambda: float(os.getenv("PE_THRESHOLD_LOST", "0.8"))
    )
    
    @property
    def puzzled_min(self) -> float:
        """Нижняя граница Puzzled = верхняя граница In Sync"""
        return self.in_sync
    
    @property
    def puzzled_max(self) -> float:
        """Верхняя граница Puzzled = нижняя граница Lost"""
        return self.lost


@dataclass
class MoodAdjustmentCoefficients:
    """
    Коэффициенты изменения настроения (VAD) для каждого состояния PE.
    
    Формат: {"valence": float, "arousal": float, "dominance": float}
    Диапазон каждого: -1.0 ... +1.0
    """
    
    # In Sync (PE < 0.3): Удовлетворение от правильного прогноза
    in_sync: Dict[str, float] = field(default_factory=lambda: {
        "valence": float(os.getenv("MOOD_IN_SYNC_VALENCE", "0.05")),
        "arousal": float(os.getenv("MOOD_IN_SYNC_AROUSAL", "0.0")),
        "dominance": float(os.getenv("MOOD_IN_SYNC_DOMINANCE", "0.03"))
    })
    
    # Puzzled (0.3 < PE < 0.8): Лёгкая озадаченность
    puzzled: Dict[str, float] = field(default_factory=lambda: {
        "valence": float(os.getenv("MOOD_PUZZLED_VALENCE", "-0.05")),
        "arousal": float(os.getenv("MOOD_PUZZLED_AROUSAL", "0.1")),
        "dominance": float(os.getenv("MOOD_PUZZLED_DOMINANCE", "-0.05"))
    })
    
    # Lost (PE >= 0.8): Бот потерял понимание собеседника
    lost: Dict[str, float] = field(default_factory=lambda: {
        "valence": float(os.getenv("MOOD_LOST_VALENCE", "-0.1")),
        "arousal": float(os.getenv("MOOD_LOST_AROUSAL", "0.2")),
        "dominance": float(os.getenv("MOOD_LOST_DOMINANCE", "-0.15"))
    })


@dataclass
class AgentModifierCoefficients:
    """
    Модификаторы силы агентов (умножение score) для каждого состояния PE.
    
    Формат: {"agent_type": float}
    Где float - множитель (1.0 = без изменений, 1.3 = +30%, 0.7 = -30%)
    """
    
    # Puzzled (0.3 < PE < 0.8): Усилить эмпатию
    puzzled: Dict[str, float] = field(default_factory=lambda: {
        "social_cortex": float(os.getenv("AGENT_MOD_PUZZLED_SOCIAL", "1.15")),
        "intuition_system1": float(os.getenv("AGENT_MOD_PUZZLED_INTUITION", "0.9"))
    })
    
    # Lost (PE >= 0.8): Сильно усилить эмпатию, ослабить интуицию
    lost: Dict[str, float] = field(default_factory=lambda: {
        "social_cortex": float(os.getenv("AGENT_MOD_LOST_SOCIAL", "1.3")),
        "intuition_system1": float(os.getenv("AGENT_MOD_LOST_INTUITION", "0.6")),
        "prefrontal_logic": float(os.getenv("AGENT_MOD_LOST_PREFRONTAL", "0.9"))
    })


@dataclass
class UncertaintyAgentConfig:
    """
    Конфигурация Uncertainty Agent.
    
    Uncertainty Agent активируется только при критичном PE (>= lost_threshold).
    """
    
    # Порог активации (должен совпадать с PE_THRESHOLD_LOST)
    activation_threshold: float = field(
        default_factory=lambda: float(os.getenv("UNCERTAINTY_ACTIVATION_THRESHOLD", "0.8"))
    )
    
    # Score при активации (должен быть достаточно высоким для гарантии победы)
    active_score: float = field(
        default_factory=lambda: float(os.getenv("UNCERTAINTY_ACTIVE_SCORE", "7.5"))
    )
    
    # Score в неактивном состоянии
    inactive_score: float = field(
        default_factory=lambda: float(os.getenv("UNCERTAINTY_INACTIVE_SCORE", "1.0"))
    )
    
    # Confidence при активации
    active_confidence: float = field(
        default_factory=lambda: float(os.getenv("UNCERTAINTY_ACTIVE_CONFIDENCE", "0.9"))
    )
    
    # Confidence в неактивном состоянии
    inactive_confidence: float = field(
        default_factory=lambda: float(os.getenv("UNCERTAINTY_INACTIVE_CONFIDENCE", "0.1"))
    )


@dataclass
class BehavioralConfig:
    """
    Главный класс с поведенческими коэффициентами.
    
    Usage:
        from src.r_core.behavioral_config import behavioral_config
        
        if prediction_error >= behavioral_config.pe_thresholds.lost:
            # Применить Lost коэффициенты
            mood_changes = behavioral_config.mood_adjustments.lost
    """
    
    pe_thresholds: PredictionErrorThresholds = field(default_factory=PredictionErrorThresholds)
    mood_adjustments: MoodAdjustmentCoefficients = field(default_factory=MoodAdjustmentCoefficients)
    agent_modifiers: AgentModifierCoefficients = field(default_factory=AgentModifierCoefficients)
    uncertainty_agent: UncertaintyAgentConfig = field(default_factory=UncertaintyAgentConfig)
    
    def get_state_name(self, prediction_error: float) -> str:
        """
        Определить текущее состояние по Prediction Error.
        
        Returns:
            "in_sync" | "neutral" | "puzzled" | "lost"
        """
        if prediction_error < self.pe_thresholds.in_sync:
            return "in_sync"
        elif prediction_error >= self.pe_thresholds.lost:
            return "lost"
        elif prediction_error >= self.pe_thresholds.puzzled_min:
            return "puzzled"
        else:
            return "neutral"
    
    def get_mood_adjustments(self, prediction_error: float) -> Dict[str, float]:
        """
        Получить изменения Mood для текущего PE.
        
        Returns:
            {"valence": float, "arousal": float, "dominance": float}
        """
        state = self.get_state_name(prediction_error)
        
        if state == "in_sync":
            return self.mood_adjustments.in_sync
        elif state == "puzzled":
            return self.mood_adjustments.puzzled
        elif state == "lost":
            return self.mood_adjustments.lost
        else:
            return {"valence": 0.0, "arousal": 0.0, "dominance": 0.0}
    
    def get_agent_modifiers(self, prediction_error: float) -> Dict[str, float]:
        """
        Получить модификаторы агентов для текущего PE.
        
        Returns:
            {"agent_type": modifier_float}
        """
        state = self.get_state_name(prediction_error)
        
        if state == "puzzled":
            return self.agent_modifiers.puzzled
        elif state == "lost":
            return self.agent_modifiers.lost
        else:
            return {}


# Глобальный singleton instance
behavioral_config = BehavioralConfig()
