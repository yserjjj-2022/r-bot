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
    🚨 Uncertainty Agent (Lost State Handler)
    Activates when the bot loses track of the user's intent or when Prediction Error is high.
    Requires the bot to ask clarifying questions instead of making assumptions.
    """
    agent_type = AgentType.UNCERTAINTY
    
    @property
    def style_instruction(self) -> str:
        return "...but you are lost, so ask clarifying questions instead of making assumptions."

    async def process(self, message: IncomingMessage, context: Dict, sliders: PersonalitySliders) -> AgentSignal:
        """
        Activates based on 'prediction_error' in context.
        Only fires if PE >= threshold defined in behavioral_config.
        """
        # Получаем PE из контекста (рассчитывается в pipeline)
        prediction_error = context.get("prediction_error", 0.0)
        
        # Получаем конфиг
        config = behavioral_config.uncertainty_agent
        threshold = config.activation_threshold
        
        # FIX: Ensure default if behavioral_config is missing keys
        if not threshold: threshold = 0.85
        
        score = 0.0
        rationale = "In sync (Low Error)"
        confidence = 0.1 # Default low confidence
        
        if prediction_error >= threshold:
            # Активация!
            score = config.active_score if config.active_score else 8.5
            confidence = config.active_confidence if config.active_confidence else 0.9
            rationale = f"High Prediction Error ({prediction_error:.2f}) -> LOST TRACK"
            
            # Эффект накопления: если уже были потеряны, усиливаем (симуляция)
            if prediction_error > 0.9:
                score += 1.0 # Critical failure
                rationale += " [CRITICAL]"
                
        else:
            # Спящий режим
            score = config.inactive_score if config.inactive_score else 0.0
            confidence = config.inactive_confidence if config.inactive_confidence else 0.1
            rationale = "In sync (Low Error)"

        signal = AgentSignal(
            agent_name=self.agent_type,
            score=score,
            rationale_short=rationale,
            confidence=confidence,
            latency_ms=1,  # Very fast check
            style_instruction=self.style_instruction
        )
        # У Uncertainty нет слайдеров-модификаторов, она зависит от ошибки прогноза
        return signal

    def _calculate_modifier(self, sliders: PersonalitySliders) -> float:
        return 1.0
