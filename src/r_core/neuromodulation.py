from datetime import datetime, timedelta
import math
from typing import Dict, Tuple

from src.r_core.schemas import HormonalState, AgentType

class NeuroModulationSystem:
    """
    Bio-chemical regulation layer (Hormonal Physics).
    Calculates internal state based on Time (Decay) and Events (Triggers).
    """
    
    def __init__(self, state: HormonalState = None):
        self.state = state or HormonalState()
        
        # Half-life in minutes
        self.HALFLIFE_NE = 5.0   # Fast decay (Arousal)
        self.HALFLIFE_DA = 15.0  # Medium decay (Motivation)
        self.HALFLIFE_5HT = 360.0 # Slow decay (6h) (Stability)
        self.HALFLIFE_CORT = 720.0 # Very slow (12h) (Stress)

    def metabolize_time(self, current_time: datetime) -> float:
        """
        Apply exponential decay based on time passed since last update.
        Returns delta_minutes for logging.
        """
        delta = current_time - self.state.last_update
        delta_minutes = delta.total_seconds() / 60.0
        
        if delta_minutes <= 0:
            return 0.0

        # Decay formula: N(t) = N0 * (0.5)^(t / half_life)
        # Baselines: NE=0.1, DA=0.3, 5HT=0.5, CORT=0.1
        
        self.state.ne = self._decay(self.state.ne, 0.1, delta_minutes, self.HALFLIFE_NE)
        self.state.da = self._decay(self.state.da, 0.3, delta_minutes, self.HALFLIFE_DA)
        self.state.ht = self._accumulate(self.state.ht, 0.5, delta_minutes, self.HALFLIFE_5HT) # 5HT recovers to 0.5
        self.state.cort = self._decay(self.state.cort, 0.1, delta_minutes, self.HALFLIFE_CORT)
        
        self.state.last_update = current_time
        return delta_minutes

    def _decay(self, current: float, baseline: float, t: float, half_life: float) -> float:
        if current > baseline:
            # Decay down to baseline
            diff = current - baseline
            return baseline + diff * (0.5 ** (t / half_life))
        else:
            # Recover up to baseline (if below)
            diff = baseline - current
            return baseline - diff * (0.5 ** (t / half_life))

    def _accumulate(self, current: float, target: float, t: float, half_life: float) -> float:
        """Same math, just semantic sugar for things that grow/recover over time"""
        return self._decay(current, target, t, half_life)

    def update_from_stimuli(self, prediction_error: float, winner_agent: AgentType):
        """
        Reactive update based on current turn processing.
        """
        # 1. Norepinephrine (Surprise/Novelty)
        # Grows with Prediction Error
        ne_spike = max(0.0, (prediction_error - 0.3) * 0.8) 
        self.state.ne = min(1.0, self.state.ne + ne_spike)
        
        # 2. Dopamine (Reward)
        # Striatum wins -> Reward prediction likely positive
        if winner_agent == AgentType.STRIATUM:
            self.state.da = min(1.0, self.state.da + 0.15)
        # Social wins -> Small reward
        elif winner_agent == AgentType.SOCIAL:
            self.state.da = min(1.0, self.state.da + 0.05)
            
        # 3. Serotonin (Safety/Stability)
        # Low PE (In Sync) -> Boost stability
        if prediction_error < 0.3:
            self.state.ht = min(1.0, self.state.ht + 0.05)
        # High PE (Lost) -> Drop stability
        elif prediction_error > 0.8:
            self.state.ht = max(0.0, self.state.ht - 0.1)
            
        # 4. Cortisol (Stress)
        # Amygdala wins -> Stress spike
        if winner_agent == AgentType.AMYGDALA:
            self.state.cort = min(1.0, self.state.cort + 0.2)
        # Lost state -> Stress accumulation
        if prediction_error > 0.8:
            self.state.cort = min(1.0, self.state.cort + 0.1)

    def get_control_signals(self) -> Dict[str, float]:
        """
        Mechanical Summation of hormones into Control Signals.
        """
        # Tempo: Driven by Arousal (NE) + Stress (CORT) - Calm (5HT)
        tempo = self.state.ne + (0.5 * self.state.cort) - (0.3 * self.state.ht)
        tempo = max(0.0, min(1.0, tempo))
        
        # SocialTemperature: Driven by Serotonin + Dopamine - Stress
        social_temp = self.state.ht + self.state.da - self.state.cort
        social_temp = max(0.0, min(1.0, social_temp))
        
        # CognitiveLoad: Inverse of Stress, boosted by Dopamine
        cog_load = 1.0 - self.state.cort + (0.2 * self.state.da)
        cog_load = max(0.1, min(1.0, cog_load)) # Never 0
        
        return {
            "tempo": tempo,
            "social_temp": social_temp,
            "cog_load": cog_load
        }

    def get_style_instruction(self) -> str:
        """
        Convert control signals to token-efficient LLM instructions.
        """
        signals = self.get_control_signals()
        tempo = signals["tempo"]
        social = signals["social_temp"]
        load = signals["cog_load"]
        
        parts = []
        
        # 1. Pacing / Length
        if tempo > 0.8:
            parts.append("[CONSTRAINT: Max 15 words. Direct answer.]")
        elif tempo > 0.6:
            parts.append("[CONSTRAINT: Short sentences. Fast pace.]")
        elif tempo < 0.3:
            parts.append("[STYLE: Relaxed, narrative, detailed.]")
            
        # 2. Tone / Warmth
        if social < 0.3:
            parts.append("[TONE: Dry, formal, distant.]")
        elif social > 0.7:
            parts.append("[TONE: Warm, empathetic, use emojis.]")
            
        # 3. Cognitive State (Stress effects)
        if load < 0.4:
            parts.append("[STATE: STRESSED. Simplistic thinking. Defensive.]")
        elif self.state.da > 0.8:
             parts.append("[STATE: EUPHORIC. High energy!]")
             
        if not parts:
            return "[STYLE: Balanced conversation.]"
            
        return " ".join(parts)
