from datetime import datetime, timedelta
import math
from typing import Dict, Tuple

from src.r_core.schemas import HormonalState, AgentType

class NeuroModulationSystem:
    """
    Bio-chemical regulation layer (R-Core v2.3).
    Model: Lovheim Cube of Emotion + Non-Linear Metabolic Decay + Cross-Effects.
    """
    
    def __init__(self, state: HormonalState = None):
        self.state = state or HormonalState()
        
        # Baselines
        self.BASELINE_NE = 0.1
        self.BASELINE_DA = 0.3
        self.BASELINE_5HT = 0.5
        self.BASELINE_CORT = 0.1

    def metabolize_time(self, current_time: datetime) -> float:
        """
        Apply non-linear decay with cross-effects based on time passed.
        Returns delta_minutes.
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
        
        self.state.last_update = current_time
        return t

    def _decay_exponential(self, current: float, baseline: float, t: float, half_life: float) -> float:
        if current > baseline:
            diff = current - baseline
            return baseline + diff * (0.5 ** (t / half_life))
        return current  # Don't decay up for NE/DA/CORT

    def update_from_stimuli(self, prediction_error: float, winner_agent: AgentType):
        """
        Reactive update based on current turn processing.
        """
        # 1. Norepinephrine (Surprise)
        # PE > 0.3 starts spiking NE
        if prediction_error > 0.3:
            spike = (prediction_error - 0.3) * 1.5  # Strong reaction
            self.state.ne = min(1.0, self.state.ne + spike)
        
        # 2. Dopamine (Reward)
        if winner_agent == AgentType.STRIATUM:
            self.state.da = min(1.0, self.state.da + 0.2)
        elif winner_agent == AgentType.SOCIAL:
             self.state.da = min(1.0, self.state.da + 0.05)
            
        # 3. Serotonin (Consumption vs Recovery)
        # Social interactions CONSUME serotonin (emotional labor)
        if winner_agent == AgentType.SOCIAL:
             self.state.ht = max(0.0, self.state.ht - 0.05)
        # In Sync restores it
        if prediction_error < 0.2:
             self.state.ht = min(1.0, self.state.ht + 0.05)
             
        # 4. Cortisol (Stress)
        if winner_agent == AgentType.AMYGDALA:
            self.state.cort = min(1.0, self.state.cort + 0.25)
        if prediction_error > 0.8:  # Lost
            self.state.cort = min(1.0, self.state.cort + 0.1)

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
