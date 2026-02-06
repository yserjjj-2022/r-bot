import asyncio
import random
from typing import List, Optional, Dict
from abc import ABC, abstractmethod

from .schemas import (
    IncomingMessage,
    AgentSignal,
    AgentType,
    PersonalitySliders,
    SemanticTriple,
    EpisodicAnchor
)
from .infrastructure.llm import LLMService

# --- LLM Abstraction ---

class AbstractLLMClient(ABC):
    @abstractmethod
    async def generate_signal(self, system_prompt: str, user_text: str, agent_name: AgentType) -> AgentSignal:
        pass

# --- Base Agent ---

class BaseAgent(ABC):
    def __init__(self, llm: Optional[LLMService] = None):
        self.llm = llm or LLMService() # Use real service by default

    @abstractmethod
    async def process(self, message: IncomingMessage, context: Dict, sliders: PersonalitySliders) -> AgentSignal:
        pass

    def _apply_modulation(self, signal: AgentSignal, modifier: float) -> AgentSignal:
        """
        Применяет влияние настроек личности (слайдеров) на силу голоса агента.
        """
        # Модуляция не может опустить уверенность ниже 0.1 или поднять выше 1.0
        original_score = signal.score
        signal.score = max(0.0, min(10.0, original_score * modifier))
        if modifier != 1.0:
            signal.rationale_short += f" [Modulated by {modifier:.2f}]"
        return signal

# --- Specific Agents ---

class IntuitionAgent(BaseAgent):
    """
    System 1: Быстрое мышление. 
    Не использует LLM, смотрит только на сходство с прошлыми эпизодами в памяти.
    """
    async def process(self, message: IncomingMessage, context: Dict, sliders: PersonalitySliders) -> AgentSignal:
        # 1. Смотрим, есть ли похожие эпизоды в памяти
        episodes: List[Dict] = context.get("episodic_memory", [])
        
        score = 0.0
        rationale = "No similar past experiences found."
        
        # Если нашли что-то очень похожее (эмуляция)
        if episodes:
            # Берем "лучшее" совпадение. 
            # Note: В реальности episodes уже отсортированы по embedding distance в MemorySystem.
            best_match = episodes[0] 
            
            # Для демо считаем, что если есть хоть что-то, это уже сигнал.
            # В идеале нужно смотреть на `score` похожести, но пока его нет в EpisodicAnchor (там emotion_score).
            # Мы можем добавить поле similarity_score в EpisodicAnchor при поиске, но пока просто:
            score = 6.0 
            rationale = f"Déjà vu! Similar to: '{best_match['raw_text'][:30]}...'"

        signal = AgentSignal(
            agent_name=AgentType.INTUITION,
            score=score,
            rationale_short=rationale,
            confidence=0.9 if score > 5 else 0.2,
            latency_ms=10
        )
        
        # Интуиция сильнее, если Pace Setting (Темп) высокий
        # pace_setting: 1.0 (Fast) -> x1.2, 0.0 (Slow) -> x0.5
        modifier = 0.5 + (sliders.pace_setting * 0.7)
        return self._apply_modulation(signal, modifier)

class AmygdalaAgent(BaseAgent):
    """
    Safety & Threat Detection.
    Реагирует на агрессию, нарушение границ, риск.
    """
    async def process(self, message: IncomingMessage, context: Dict, sliders: PersonalitySliders) -> AgentSignal:
        system_prompt = (
            "You are the AMYGDALA module of an AI. "
            "Your job is to detect THREATS, AGGRESSION, HIGH RISK, or USER DISTRESS in the input. "
            "Output a high score (8-10) if unsafe/hostile, low score (0-2) if safe/neutral."
        )
        
        signal = await self.llm.generate_signal(system_prompt, message.text, AgentType.AMYGDALA)
        
        # Если Risk Tolerance высокий, Амигдала "спит" (сигнал слабее)
        # risk: 1.0 (Daredevil) -> x0.3, risk: 0.0 (Paranoid) -> x1.5
        modifier = 1.5 - (sliders.risk_tolerance * 1.2)
        return self._apply_modulation(signal, modifier)

class PrefrontalAgent(BaseAgent):
    """
    Logic & Planning.
    Отвечает за структуру, факты и выполнение задач.
    """
    async def process(self, message: IncomingMessage, context: Dict, sliders: PersonalitySliders) -> AgentSignal:
        system_prompt = (
            "You are the PREFRONTAL CORTEX module. "
            "Analyze the input for LOGICAL STRUCTURE, FACTUAL QUESTIONS, or COMPLEX TASKS. "
            "Output high score (7-10) if the user asks for reasoning, planning, or facts."
        )
        
        signal = await self.llm.generate_signal(system_prompt, message.text, AgentType.PREFRONTAL)
        
        # Если Empathy Bias низкий (сухой режим), Логика сильнее
        # empathy: 0.0 -> x1.3, empathy: 1.0 -> x0.7
        modifier = 1.3 - (sliders.empathy_bias * 0.6)
        return self._apply_modulation(signal, modifier)

class SocialAgent(BaseAgent):
    """
    Social Norms & Empathy.
    Отвечает за вежливость, поддержку и "лицо".
    """
    async def process(self, message: IncomingMessage, context: Dict, sliders: PersonalitySliders) -> AgentSignal:
        system_prompt = (
            "You are the SOCIAL CORTEX module. "
            "Detect SOCIAL RITUALS (greetings, thanks), EMOTIONAL CUES, or need for POLITENESS. "
            "Output high score if social interaction is required."
        )
        
        signal = await self.llm.generate_signal(system_prompt, message.text, AgentType.SOCIAL)
        
        # Прямая зависимость от Эмпатии
        # empathy: 1.0 -> x1.5, empathy: 0.0 -> x0.5
        modifier = 0.5 + sliders.empathy_bias
        return self._apply_modulation(signal, modifier)

class StriatumAgent(BaseAgent):
    """
    Reward & Desire.
    Ищет возможности для бота (или пользователя), драйв, любопытство.
    """
    async def process(self, message: IncomingMessage, context: Dict, sliders: PersonalitySliders) -> AgentSignal:
        system_prompt = (
            "You are the STRIATUM (Reward System). "
            "Detect OPPORTUNITIES for reward, fun, curiosity, or engagement. "
            "Output high score if the input is exciting, game-like, or offers a goal."
        )
        
        signal = await self.llm.generate_signal(system_prompt, message.text, AgentType.STRIATUM)
        
        # Зависит от Risk Tolerance (авантюризм)
        modifier = 0.5 + (sliders.risk_tolerance * 0.8)
        return self._apply_modulation(signal, modifier)
