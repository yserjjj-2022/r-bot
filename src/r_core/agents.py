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
            latency_ms=0 # already accounted for in batch
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

    async def process(self, message: IncomingMessage, context: Dict, sliders: PersonalitySliders) -> AgentSignal:
        episodes: List[Dict] = context.get("episodic_memory", [])
        score = 0.0
        rationale = "No signal"
        
        if episodes:
            score = 6.0 
            rationale = f"Déjà vu: '{episodes[0]['raw_text'][:20]}...'"

        signal = AgentSignal(
            agent_name=self.agent_type,
            score=score,
            rationale_short=rationale,
            confidence=0.9 if score > 5 else 0.2,
            latency_ms=10
        )
        return self._apply_modulation(signal, self._calculate_modifier(sliders))

    def _calculate_modifier(self, sliders: PersonalitySliders) -> float:
        return 0.5 + (sliders.pace_setting * 0.7)

class AmygdalaAgent(BaseAgent):
    agent_type = AgentType.AMYGDALA
    
    async def process(self, message: IncomingMessage, context: Dict, sliders: PersonalitySliders) -> AgentSignal:
        # Legacy single mode (backup)
        sys = "You are AMYGDALA. Detect threats (8-10) or safety (0-2)."
        sig = await self.llm.generate_signal(sys, message.text, self.agent_type)
        return self._apply_modulation(sig, self._calculate_modifier(sliders))

    def _calculate_modifier(self, sliders: PersonalitySliders) -> float:
        return 1.5 - (sliders.risk_tolerance * 1.2)

class PrefrontalAgent(BaseAgent):
    agent_type = AgentType.PREFRONTAL

    async def process(self, message: IncomingMessage, context: Dict, sliders: PersonalitySliders) -> AgentSignal:
        sys = "You are LOGIC. Detect tasks/facts (8-10) or chat (0-2)."
        sig = await self.llm.generate_signal(sys, message.text, self.agent_type)
        return self._apply_modulation(sig, self._calculate_modifier(sliders))

    def _calculate_modifier(self, sliders: PersonalitySliders) -> float:
        return 1.3 - (sliders.empathy_bias * 0.6)

class SocialAgent(BaseAgent):
    agent_type = AgentType.SOCIAL

    async def process(self, message: IncomingMessage, context: Dict, sliders: PersonalitySliders) -> AgentSignal:
        sys = "You are SOCIAL. Detect emotions/politeness (8-10)."
        sig = await self.llm.generate_signal(sys, message.text, self.agent_type)
        return self._apply_modulation(sig, self._calculate_modifier(sliders))

    def _calculate_modifier(self, sliders: PersonalitySliders) -> float:
        return 0.5 + sliders.empathy_bias

class StriatumAgent(BaseAgent):
    agent_type = AgentType.STRIATUM

    async def process(self, message: IncomingMessage, context: Dict, sliders: PersonalitySliders) -> AgentSignal:
        sys = "You are REWARD. Detect fun/goals (8-10)."
        sig = await self.llm.generate_signal(sys, message.text, self.agent_type)
        return self._apply_modulation(sig, self._calculate_modifier(sliders))

    def _calculate_modifier(self, sliders: PersonalitySliders) -> float:
        return 0.5 + (sliders.risk_tolerance * 0.8)
