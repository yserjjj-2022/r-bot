"""
Trait Translation Engine (Task 8)
Maps HEXACO personality traits (0-100) to R-Core hyperparameters.

Mathematical Functions:
- Sigmoid: Used for thresholds and extremes (prevents linear scaling from breaking the Council)
- Exponential: Used for time/decay parameters (maps linear to logarithmic scale)
"""

import math
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class TranslatedConfig:
    """Result of translating HEXACO profile to R-Core parameters."""
    # Core sliders
    intuition_gain: float
    chaos_level: float
    base_decay_rate: float
    persistence: float
    dynamic_phatic_threshold: float
    social_agent_weight: float
    pred_sensitivity: float
    amygdala_multiplier: float
    striatum_agent_weight: float
    
    # Volitional strategies
    force_manipulation_strategies: bool
    bifurcation_threshold_modifier: float
    
    # Baseline hormones
    baseline_cortisol: float
    baseline_oxytocin: float


class TraitTranslationEngine:
    """
    Translates HEXACO personality model (0-100) to R-Core hyperparameters.
    
    HEXACO Traits:
    - H (Honesty-Humility): 0=Chetrost, 100=Iskrennost
    - E (Emotionality/Neuroticism): 0=Coldness, 100=Anxiety/Reactivity
    - X (Extraversion): 0=Reserved, 100=Sociable
    - A (Agreeableness): 0=Quarrelsome, 100=Agreeable
    - C (Conscientiousness): 0=Chaotic, 100=Goal-oriented
    - O (Openness): 0=Conservative, 100=Curious
    """
    
    # Preset configurations (Functional / Light)
    PRESETS_LIGHT = {
        "Аналитик": {"H": 70, "E": 20, "X": 60, "A": 50, "C": 90, "O": 60},
        "Эмпат": {"H": 80, "E": 60, "X": 75, "A": 85, "C": 50, "O": 50},
        "Мечтатель": {"H": 60, "E": 50, "X": 55, "A": 55, "C": 30, "O": 95},
        "Педант": {"H": 50, "E": 40, "X": 40, "A": 30, "C": 95, "O": 15},
    }
    
    # Preset configurations (Dark / Deviant)
    PRESETS_DARK = {
        "Макиавеллист": {"H": 10, "E": 20, "X": 60, "A": 40, "C": 80, "O": 50},
        "Нарцисс": {"H": 20, "E": 50, "X": 85, "A": 25, "C": 60, "O": 40},
        "Психопат": {"H": 5, "E": 85, "X": 60, "A": 5, "C": 40, "O": 30},
        "ТоксичныйТролль": {"H": 15, "E": 90, "X": 80, "A": 15, "C": 20, "O": 45},
    }
    
    ALL_PRESETS = {**PRESETS_LIGHT, **PRESETS_DARK}
    
    def __init__(self, hexaco_profile: Optional[Dict[str, int]] = None):
        """
        Initialize with HEXACO profile.
        
        Args:
            hexaco_profile: Dict with keys H, E, X, A, C, O (values 0-100)
        """
        self.profile = hexaco_profile or {
            "H": 50, "E": 50, "X": 50, "A": 50, "C": 50, "O": 50
        }
    
    # ==================== Mathematical Transfer Functions ====================
    
    @staticmethod
    def sigmoid(x: float, center: float = 0.5, steepness: float = 4.0) -> float:
        """
        Sigmoid function for threshold mapping.
        Returns value between 0 and 1.
        """
        x = max(0, min(1, x))  # Clamp to [0, 1]
        return 1 / (1 + math.exp(-steepness * (x - center)))
    
    @staticmethod
    def exponential(x: float, min_val: float = 0.01, max_val: float = 0.4) -> float:
        """
        Exponential mapping for decay parameters.
        Maps linear 0-1 to logarithmic scale.
        """
        x = max(0, min(1, x))
        # Exponential curve: low x -> low min_val, high x -> high max_val
        return min_val + (max_val - min_val) * (x ** 2)
    
    @staticmethod
    def linear(x: float, min_val: float, max_val: float) -> float:
        """Simple linear mapping."""
        x = max(0, min(1, x))
        return min_val + (max_val - min_val) * x
    
    @staticmethod
    def inverted_linear(x: float, min_val: float, max_val: float) -> float:
        """Inverted linear mapping: high x -> low value."""
        x = max(0, min(1, x))
        return max_val - (max_val - min_val) * x
    
    # ==================== Translation Methods ====================
    
    def translate(self) -> TranslatedConfig:
        """Translate HEXACO profile to R-Core configuration."""
        p = self.profile
        
        # === Openness (O) ===
        # Maps to intuition_gain: 0.5 to 3.0
        intuition_gain = self.linear(p["O"], 0.5, 3.0)
        
        # Bifurcation threshold: triggers earlier if O > 75
        bifurcation_threshold_modifier = 1.0 if p["O"] <= 75 else 1.0 + (p["O"] - 75) / 25 * 0.5
        
        # === Conscientiousness (C) ===
        # Maps to base_decay_rate: Low C = High decay (0.4), High C = Low decay (0.01)
        base_decay_rate = self.exponential(p["C"], min_val=0.01, max_val=0.4)
        
        # Persistence: 0.1 to 0.9
        persistence = self.linear(p["C"], 0.1, 0.9)
        
        # === Extraversion (X) ===
        # Dynamic phatic threshold: maps to expected word count
        dynamic_phatic_threshold = self.linear(p["X"], 2, 8)
        
        # Social agent weight: sigmoid boost
        social_agent_weight = 0.5 + self.sigmoid(p["X"] / 100) * 1.5
        
        # === Agreeableness (A) ===
        # Prediction sensitivity: inverted sigmoid. Low A = huge multiplier on PE
        pred_sensitivity = 1.0 + self.inverted_sigmoid(p["A"] / 100) * 2.0
        
        # Amygdala multiplier: Low A + High E = Extreme boost
        amygdala_multiplier = 1.0
        if p["A"] < 30 and p["E"] > 50:
            amygdala_multiplier = 1.0 + (50 - p["A"]) / 50 * (p["E"] - 50) / 50 * 2.0
        
        # === Neuroticism / Emotionality (E) ===
        # Chaos level: rises sharply after 70%
        chaos_level = self.sigmoid(p["E"] / 100, center=0.7, steepness=8.0) * 0.5
        
        # Baseline Cortisol: linear mapping
        baseline_cortisol = self.linear(p["E"], 0.1, 0.8)
        
        # === Honesty (H) ===
        # Strategy selection: if H < 30, force manipulation/challenge strategies
        force_manipulation_strategies = p["H"] < 30
        
        # Striatum agent weight: inverted linear. Low H = High reward-seeking
        striatum_agent_weight = self.inverted_linear(p["H"], 0.5, 2.0)
        
        # Baseline Oxytocin: High H + High A = High baseline
        baseline_oxytocin = self.linear(p["H"], 0.1, 0.6) if p["A"] > 50 else 0.2
        
        return TranslatedConfig(
            intuition_gain=intuition_gain,
            chaos_level=chaos_level,
            base_decay_rate=base_decay_rate,
            persistence=persistence,
            dynamic_phatic_threshold=dynamic_phatic_threshold,
            social_agent_weight=social_agent_weight,
            pred_sensitivity=pred_sensitivity,
            amygdala_multiplier=amygdala_multiplier,
            striatum_agent_weight=striatum_agent_weight,
            force_manipulation_strategies=force_manipulation_strategies,
            bifurcation_threshold_modifier=bifurcation_threshold_modifier,
            baseline_cortisol=baseline_cortisol,
            baseline_oxytocin=baseline_oxytocin
        )
    
    @staticmethod
    def inverted_sigmoid(x: float, center: float = 0.5, steepness: float = 4.0) -> float:
        """Inverted sigmoid: high x -> low value."""
        return 1.0 - TraitTranslationEngine.sigmoid(x, center, steepness)
    
    def apply_to_bot_config(self, bot_config: Any) -> Any:
        """
        Apply translated config to BotConfig object.
        
        Args:
            bot_config: BotConfig instance to modify
            
        Returns:
            Modified BotConfig with translated values
        """
        translated = self.translate()
        
        # Update sliders
        if hasattr(bot_config, 'sliders'):
            bot_config.sliders.intuition_gain = translated.intuition_gain
            bot_config.sliders.chaos_level = translated.chaos_level
            # Other sliders are mapped via logic in pipeline
        
        # Store translated values for pipeline access
        bot_config._translated_hexaco = {
            "base_decay_rate": translated.base_decay_rate,
            "persistence": translated.persistence,
            "dynamic_phatic_threshold": translated.dynamic_phatic_threshold,
            "social_agent_weight": translated.social_agent_weight,
            "pred_sensitivity": translated.pred_sensitivity,
            "amygdala_multiplier": translated.amygdala_multiplier,
            "striatum_agent_weight": translated.striatum_agent_weight,
            "force_manipulation_strategies": translated.force_manipulation_strategies,
            "bifurcation_threshold_modifier": translated.bifurcation_threshold_modifier,
            "baseline_cortisol": translated.baseline_cortisol,
            "baseline_oxytocin": translated.baseline_oxytocin,
        }
        
        return bot_config


def get_preset_profile(preset_name: str) -> Optional[Dict[str, int]]:
    """Get HEXACO profile for a preset."""
    return TraitTranslationEngine.ALL_PRESETS.get(preset_name)


def is_dark_archetype(profile: Dict[str, int]) -> bool:
    """Check if profile represents a dark/deviant archetype."""
    return profile.get("H", 50) < 25 and profile.get("A", 50) < 25
