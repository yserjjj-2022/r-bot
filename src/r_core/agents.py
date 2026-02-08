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
        # Mapping generic names to specific AgentType in subclass required? 
        # Actually we know the agent type in subclass.
        
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

        signal = AgentSignal(
            agent_name=self.agent_type,
            score=score,
            rationale_short=rationale,
            confidence=0.85 if score >= 5 else 0.3,  # Более строгий порог для высокой уверенности
            latency_ms=10,
            style_instruction=self.style_instruction # NEW
        )
        return self._apply_modulation(signal, self._calculate_modifier(sliders))

    def _calculate_modifier(self, sliders: PersonalitySliders) -> float:
        return 0.5 + (sliders.pace_setting * 0.7)

class AmygdalaAgent(BaseAgent):
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
        return 1.3 - (sliders.empathy_bias * 0.6)

class SocialAgent(BaseAgent):
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
