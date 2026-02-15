import asyncio
import random
from typing import List, Optional, Dict
from abc import ABC, abstractmethod

# FIX: Absolute imports
from src.r_core.schemas import (
    IncomingMessage,
    AgentSignal,
    AgentType,
    PersonalitySliders,
    SemanticTriple,
    EpisodicAnchor
)
from src.r_core.infrastructure.llm import LLMService
from src.r_core.behavioral_config import behavioral_config

class AbstractLLMClient(ABC):
    @abstractmethod
    async def generate_signal(self, system_prompt: str, user_text: str, agent_name: AgentType) -> AgentSignal:
        pass

class BaseAgent(ABC):
    def __init__(self, llm: Optional[LLMService] = None):
        self.llm = llm or LLMService()

    @abstractmethod
    async def process(self, message: IncomingMessage, context: Dict, sliders: PersonalitySliders) -> AgentSignal:
        pass
    
    @property
    @abstractmethod
    def style_instruction(self) -> str:
        """Return the specific adverbial style instruction for this agent."""
        pass

    def process_from_report(self, report_data: Dict, sliders: PersonalitySliders) -> AgentSignal:
        """
        New method for Batch Processing.
        Accepts data {score, rationale, confidence} directly from the Council Report.
        """
        signal = AgentSignal(
            agent_name=self.agent_type, # Define in subclass
            score=float(report_data.get("score", 0.0)),
            rationale_short=report_data.get("rationale", "No rationale"),
            confidence=float(report_data.get("confidence", 0.0)),
            latency_ms=0, # already accounted for in batch
            style_instruction=self.style_instruction # NEW: Populate style instruction
        )
        return self._apply_modulation(signal, self._calculate_modifier(sliders))

    def _apply_modulation(self, signal: AgentSignal, modifier: float) -> AgentSignal:
        original_score = signal.score
        signal.score = max(0.0, min(10.0, original_score * modifier))
        if modifier != 1.0:
            signal.rationale_short += f" [Mod {modifier:.2f}]"
        return signal
    
    @abstractmethod
    def _calculate_modifier(self, sliders: PersonalitySliders) -> float:
        return 1.0

# --- Specific Agents ---

class IntuitionAgent(BaseAgent):
    """
    🔮 Intuition (Pattern Matching)
    Fast system responsible for 'gut feelings' and déjà vu.
    Detects recurring patterns from episodic memory.
    """
    agent_type = AgentType.INTUITION
    
    @property
    def style_instruction(self) -> str:
        return "...but trust your gut feeling and be concise."

    async def process(self, message: IncomingMessage, context: Dict, sliders: PersonalitySliders) -> AgentSignal:
        episodes: List[Dict] = context.get("episodic_memory", [])
        score = 0.0
        rationale = "No signal"
        
        if episodes:
            # FIX: Более консервативный подход к Déjà vu
            # Проверяем, что эпизод не слишком короткий (избегаем ложных совпадений)
            episode_text = episodes[0].get('raw_text', '')
            
            if len(episode_text) > 10:  # Минимум 10 символов для валидного совпадения
                score = 5.0  # Снижено с 6.0 до 5.0 (более консервативно)
                # Показываем до 30 символов для лучшей читаемости
                rationale = f"Déjà vu: '{episode_text[:30]}...'" if len(episode_text) > 30 else f"Déjà vu: '{episode_text}'"
            else:
                # Слишком короткий эпизод — снижаем уверенность
                score = 3.0
                rationale = "Weak pattern match"
        
        # Calculate confidence separately to avoid 'UnboundLocalError' if episodes is empty
        confidence = 0.85 if score >= 5 else 0.3

        signal = AgentSignal(
            agent_name=self.agent_type,
            score=score,
            rationale_short=rationale,
            confidence=confidence,  
            latency_ms=10,
            style_instruction=self.style_instruction # NEW
        )
        return self._apply_modulation(signal, self._calculate_modifier(sliders))

    def _calculate_modifier(self, sliders: PersonalitySliders) -> float:
        """
        ✨ НОВАЯ ЛОГИКА: Инвертная связь с pace_setting.
        pace_setting 0.0 (Low Logic) → Intuition усилена (1.5x)
        pace_setting 1.0 (High Logic) → Intuition ослаблена (0.5x)
        """
        return 1.5 - (sliders.pace_setting * 1.0)

class AmygdalaAgent(BaseAgent):
    """
    🛡️ Amygdala (Safety & Boundaries)
    Scans input for threats, aggression, or violations.
    Activates Fight/Flight response.
    """
    agent_type = AgentType.AMYGDALA
    
    @property
    def style_instruction(self) -> str:
        return "...but maintain firm boundaries and safety."
    
    async def process(self, message: IncomingMessage, context: Dict, sliders: PersonalitySliders) -> AgentSignal:
        # Legacy single mode (backup)
        sys = "You are AMYGDALA. Detect threats (8-10) or safety (0-2)."
        sig = await self.llm.generate_signal(sys, message.text, self.agent_type)
        sig.style_instruction = self.style_instruction # NEW (manual set for legacy path)
        return self._apply_modulation(sig, self._calculate_modifier(sliders))

    def _calculate_modifier(self, sliders: PersonalitySliders) -> float:
        return 1.5 - (sliders.risk_tolerance * 1.2)

class PrefrontalAgent(BaseAgent):
    """
    🧠 Prefrontal Cortex (Logic & Control)
    Responsible for structured reasoning, planning, and factual accuracy.
    Inhibits impulsive responses.
    """
    agent_type = AgentType.PREFRONTAL
    
    @property
    def style_instruction(self) -> str:
        return "...but ensure the answer is logical, structured, and fact-based."

    async def process(self, message: IncomingMessage, context: Dict, sliders: PersonalitySliders) -> AgentSignal:
        sys = "You are LOGIC. Detect tasks/facts (8-10) or chat (0-2)."
        sig = await self.llm.generate_signal(sys, message.text, self.agent_type)
        sig.style_instruction = self.style_instruction
        return self._apply_modulation(sig, self._calculate_modifier(sliders))

    def _calculate_modifier(self, sliders: PersonalitySliders) -> float:
        """
        ✨ НОВАЯ ЛОГИКА: Прямая связь с pace_setting.
        pace_setting 0.0 (Low Logic) → Logic ослаблена (0.7x)
        pace_setting 1.0 (High Logic) → Logic усилена (1.5x)
        
        ВАЖНО: empathy_bias больше НЕ влияет на Logic напрямую.
        Теперь Logic контролируется только через pace_setting.
        """
        return 0.7 + (sliders.pace_setting * 0.8)

class SocialAgent(BaseAgent):
    """
    🤝 Social Cortex (Empathy & Norms)
    Manages relationships, politeness, and emotional resonance.
    Ensures social coherence.
    """
    agent_type = AgentType.SOCIAL
    
    @property
    def style_instruction(self) -> str:
        return "...but express it with warmth, politeness, and empathy."

    async def process(self, message: IncomingMessage, context: Dict, sliders: PersonalitySliders) -> AgentSignal:
        sys = "You are SOCIAL. Detect emotions/politeness (8-10)."
        sig = await self.llm.generate_signal(sys, message.text, self.agent_type)
        sig.style_instruction = self.style_instruction
        return self._apply_modulation(sig, self._calculate_modifier(sliders))

    def _calculate_modifier(self, sliders: PersonalitySliders) -> float:
        return 0.5 + sliders.empathy_bias

class StriatumAgent(BaseAgent):
    """
    💎 Striatum (Reward & Drive)
    Seeks novelty, engagement, and dopamine rewards.
    Drives playful and energetic responses.
    """
    agent_type = AgentType.STRIATUM
    
    @property
    def style_instruction(self) -> str:
        return "...but keep it playful, energetic, and engaging."

    async def process(self, message: IncomingMessage, context: Dict, sliders: PersonalitySliders) -> AgentSignal:
        sys = "You are REWARD. Detect fun/goals (8-10)."
        sig = await self.llm.generate_signal(sys, message.text, self.agent_type)
        sig.style_instruction = self.style_instruction
        return self._apply_modulation(sig, self._calculate_modifier(sliders))

    def _calculate_modifier(self, sliders: PersonalitySliders) -> float:
        return 0.5 + (sliders.risk_tolerance * 0.8)

class UncertaintyAgent(BaseAgent):
    """
    🚨 Uncertainty Agent (Lost State Handler) - Active Inference v2.0
    Activates when Prediction Error (PE) exceeds a threshold controlled by user settings.
    Implements 'Persistence' (Willpower) logic:
    - High Persistence: Bot ignores errors (Stubborn).
    - Low Persistence: Bot yields to errors (Flexible).
    """
    agent_type = AgentType.UNCERTAINTY
    
    @property
    def style_instruction(self) -> str:
        return "...but admit you are confused and ask clarifying questions."

    async def process(self, message: IncomingMessage, context: Dict, sliders: PersonalitySliders) -> AgentSignal:
        """
        Decides activation based on PE, Threshold, and Persistence.
        """
        # 1. Get Prediction Error (PE)
        prediction_error = context.get("prediction_error", 0.0)
        
        # 2. Get Thresholds from Sliders (Active Inference Control)
        # Default to high threshold if slider missing (safe fallback)
        pe_threshold = getattr(sliders, "pred_threshold", 0.8) 
        persistence = getattr(sliders, "persistence", 0.5)
        
        score = 0.0
        rationale = "In sync"
        confidence = 0.1
        
        # 3. Active Inference Logic: Willpower Check
        # If Persistence is HIGH, we artificially LOWER the perceived error.
        # "I'm sure I'm right, the user is just weird."
        perceived_error = prediction_error * (1.0 - (persistence * 0.5)) 
        
        if perceived_error >= pe_threshold:
            # --- LOST TRACK (Surprise Minimization Failed) ---
            score = 8.5
            confidence = 0.9
            rationale = f"High PE ({prediction_error:.2f}) > Threshold ({pe_threshold:.2f}). Persistence failed."
            
            # Critical failure escalation
            if prediction_error > 0.95:
                score = 10.0
                rationale += " [CRITICAL SURPRISE]"
                
        else:
            # --- IN SYNC (or Stubbornly Ignoring) ---
            score = 0.0
            confidence = 0.1
            if prediction_error > pe_threshold:
                rationale = f"High PE ({prediction_error:.2f}) suppressed by Persistence ({persistence:.2f})"
            else:
                rationale = f"Low PE ({prediction_error:.2f})"

        signal = AgentSignal(
            agent_name=self.agent_type,
            score=score,
            rationale_short=rationale,
            confidence=confidence,
            latency_ms=1, 
            style_instruction=self.style_instruction
        )
        return signal

    def _calculate_modifier(self, sliders: PersonalitySliders) -> float:
        return 1.0
