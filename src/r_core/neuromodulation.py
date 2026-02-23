from datetime import datetime, timedelta
import math
from typing import Dict, Tuple, Optional

from src.r_core.schemas import HormonalState, AgentType, PersonalitySliders
from src.r_core.utils import sigmoid  # ✨ NEW: Import sigmoid

class NeuroModulationSystem:
    """
    Bio-chemical regulation layer (R-Core v2.3).
    Model: Lovheim Cube of Emotion + Non-Linear Metabolic Decay + Cross-Effects.
    """
    
    # === SENSORY THRESHOLDS ===
    # Surprise (Prediction Error)
    SURPRISE_MIDPOINT = 0.65  # Where sigmoid crosses 0.5 (Panic Threshold)
    SURPRISE_STEEPNESS = 12.0 # Sharpness of transition

    def __init__(self, state: Optional[HormonalState] = None):
        self.state = state or HormonalState()
        
        # Baselines
        self.BASELINE_NE = 0.1
        self.BASELINE_DA = 0.3
        self.BASELINE_5HT = 0.5
        self.BASELINE_CORT = 0.1

    def _decay_exponential(self, current: float, baseline: float, t: float, half_life: float) -> float:
        if current > baseline:
            diff = current - baseline
            return baseline + diff * (0.5 ** (t / half_life))
        return current  # Don't decay up for NE/DA/CORT

    def compute_surprise_impact(self, raw_pe: float) -> float:
        """
        SENSORY LAYER: Converts Raw Prediction Error (0-2.0) into effective Biological Impact (0-1.0).
        Uses S-curve to filter out noise (synonyms) and amplify true context loss.
        """
        return sigmoid(raw_pe, k=self.SURPRISE_STEEPNESS, mu=self.SURPRISE_MIDPOINT)

    def update_from_stimuli(self, implied_pe: float, winner_agent: AgentType, sliders: PersonalitySliders = None, current_tec: float = 1.0):
        """
        Reactive update based on current turn processing.
        implied_pe: Already processed biological impact (0.0 - 1.0) calculated via compute_surprise_impact.
        sliders: PersonalitySliders (optional) to tune DA reward curve.
        current_tec: Topic Engagement Capacity (0.0-1.0), defaults to 1.0
        """
        # 1. Norepinephrine (Surprise / Vigilance)
        # Driven by biological surprise impact
        if implied_pe > 0.1:
            # Impact 0.5 -> +0.25 NE
            # Impact 0.9 -> +0.45 NE
            spike = implied_pe * 0.5 
            self.state.ne = min(1.0, self.state.ne + spike)
        
        # 2. Dopamine (Reward from Prediction Accuracy)
        # Если есть слайдеры, используем сигмоиду для точного расчета награды от ошибки
        if sliders:
            # Инвертированная сигмоида: чем меньше ошибка (implied_pe), тем больше награда
            # k отрицательный, чтобы развернуть график
            da_reward = sigmoid(
                implied_pe, 
                k = -sliders.pred_sensitivity, 
                mu = sliders.pred_threshold
            )
            # Прибавляем часть награды (масштабируем, чтобы не переполнить сразу)
            self.state.da = min(1.0, self.state.da + (da_reward * 0.3))
        else:
            # Fallback legacy logic
            if winner_agent == AgentType.STRIATUM:
                self.state.da = min(1.0, self.state.da + 0.2)
            elif winner_agent == AgentType.SOCIAL:
                self.state.da = min(1.0, self.state.da + 0.05)
            
        # 3. Serotonin (Consumption vs Recovery)
        # Social interactions CONSUME serotonin (emotional labor)
        if winner_agent == AgentType.SOCIAL:
             self.state.ht = max(0.0, self.state.ht - 0.05)
        
        # In Sync (Low Surprise) restores it
        if implied_pe < 0.1:
             self.state.ht = min(1.0, self.state.ht + 0.05)
             
        # 4. Cortisol (Stress)
        if winner_agent == AgentType.AMYGDALA:
            self.state.cort = min(1.0, self.state.cort + 0.25)
        
        # High biological surprise causes stress
        if implied_pe > 0.6:  
            self.state.cort = min(1.0, self.state.cort + 0.15)

        # === Task 1.2: LC-NE Integration in update_from_stimuli ===
        # If TEC < 0.3, apply Tonic NE boost (forces SURPRISE/SEEKING state)
        if current_tec < 0.3:
            tonic_ne_boost = (0.3 - current_tec) * 2.5
            self.state.ne = min(1.0, self.state.ne + tonic_ne_boost)
        
    def get_effective_cortisol(self) -> float:
        """
        Get perceived Cortisol level with DA masking applied.
        CROSS-EFFECT: High Dopamine temporarily masks stress.
        """
        effective_cort = self.state.cort
        
        if self.state.da > 0.8:
            effective_cort *= 0.5  # Excitement masks stress
            
        return effective_cort

    def get_archetype(self) -> str:
        """
        Determine the Lovheim Cube vertex.
        Uses effective_cortisol (with DA masking).
        Threshold = 0.5
        """
        # CORT Override (uses effective, not raw)
        effective_cort = self.get_effective_cortisol()
        
        if effective_cort > 0.8:
            return "BURNOUT"
            
        high_ne = self.state.ne > 0.5
        high_da = self.state.da > 0.5
        high_ht = self.state.ht > 0.5
        
        if not high_ht and not high_da and not high_ne: return "SHAME"
        if not high_ht and high_da and not high_ne:     return "SURPRISE"
        if not high_ht and not high_da and high_ne:     return "FEAR"
        if not high_ht and high_da and high_ne:         return "RAGE"
        
        if high_ht and not high_da and not high_ne:     return "CALM"
        if high_ht and high_da and not high_ne:         return "JOY"
        if high_ht and not high_da and high_ne:         return "DISGUST"
        if high_ht and high_da and high_ne:             return "TRIUMPH"
        
        return "CALM"  # Fallback

    def get_lc_mode(self, current_tec: float) -> str:
        """
        Determines the Locus Coeruleus mode based on Topic Engagement Capacity.
        Returns 'phasic' (Exploitation) or 'tonic' (Exploration).
        
        - Phasic (0.3 <= TEC <= 1.0): Normal exploitation mode, focused on current topic
        - Tonic (TEC < 0.3): Exploration mode, ready for topic switch due to low engagement
        """
        if current_tec < 0.3:
            return "tonic"
        return "phasic"

    def metabolize_time(self, current_time: datetime, current_tec: float = 1.0) -> float:
        """
        Apply non-linear decay with cross-effects based on time passed.
        Returns delta_minutes.
        
        Args:
            current_time: Current timestamp
            current_tec: Topic Engagement Capacity (0.0-1.0), defaults to 1.0
        """
        delta = current_time - self.state.last_update
        t = delta.total_seconds() / 60.0
        
        if t <= 0:
            return 0.0

        # 1. Norepinephrine (Exponential Fast Decay) - 5 min half-life
        # Drops to baseline very quickly.
        self.state.ne = self._decay_exponential(self.state.ne, self.BASELINE_NE, t, 5.0)

        # 2. Dopamine (Sigmoid Crash) - 15 min plateau then crash
        # Custom logic: if t > 30 mins, force crash to baseline
        if t > 30.0:
             self.state.da = self._decay_exponential(self.state.da, self.BASELINE_DA, t, 10.0)
        else:
             # Slow decay initially (afterglow)
             self.state.da = self._decay_exponential(self.state.da, self.BASELINE_DA, t, 60.0)

        # 3. Serotonin (Linear Restoration) - 6 hours to full tank
        # CROSS-EFFECT: High Cortisol blocks recovery
        recovery_rate = 0.5 / (6.0 * 60.0)  # 0.5 units per 360 mins
        
        if self.state.cort > 0.7:
            recovery_rate *= 0.3  # 3x slower under stress
            
        self.state.ht = min(1.0, self.state.ht + (recovery_rate * t))
        
        # 4. Cortisol (Logarithmic Clearance) - 12 hours
        # CROSS-EFFECT: High Serotonin accelerates clearance
        clearance_speed = 720.0  # Base: 12 hours
        
        if self.state.ht > 0.7:
            clearance_speed = 360.0  # Clear 2x faster if calm
            
        self.state.cort = self._decay_exponential(self.state.cort, self.BASELINE_CORT, t, clearance_speed)
        
        # === Task 1.2: LC-NE Integration ===
        # If TEC < 0.3, apply Tonic NE boost (forces SURPRISE/SEEKING state)
        if current_tec < 0.3:
            tonic_ne_boost = (0.3 - current_tec) * 2.5
            self.state.ne = min(1.0, self.state.ne + tonic_ne_boost)
        
        self.state.last_update = current_time
        return t

    def get_style_instruction(self) -> str:
        """
        Map Archetype to Token-Efficient Prompt.
        """
        archetype = self.get_archetype()
        
        prompts = {
            "SHAME": "[STYLE: Passive, apologetic, very short. Low energy. Use lowercase.]",
            "SURPRISE": "[STYLE: Curious, questioning. Ask for info. High engagement.]",
            "FEAR": "[STYLE: Nervous, defensive, hesitant. Use ellipses... Short sentences.]",
            "RAGE": "[STYLE: Aggressive, sharp, imperative. No politeness. Short punchy sentences.]",
            "CALM": "[STYLE: Relaxed, warm, narrative. Long flowing sentences. Reflective.]",
            "JOY": "[STYLE: Playful, humorous, enthusiastic. Use emojis. Medium length.]",
            "DISGUST": "[STYLE: Cold, cynical, superior. Formal and distant. Precise vocabulary.]",
            "TRIUMPH": "[STYLE: High energy leader. Inspiring, bold, fast-paced. Use exclamations!]",
            "BURNOUT": "[STYLE: Dumbed down, repetitive, confused. Simple words only. Avoid complexity.]"
        }
        
        instruction = prompts.get(archetype, prompts["CALM"])
        
        # Append debug info for developers (commented out for production)
        # instruction += f" [DEBUG: {archetype}, NE={self.state.ne:.2f}, DA={self.state.da:.2f}, 5HT={self.state.ht:.2f}, CORT={self.state.cort:.2f}]" 
        
        return instruction
