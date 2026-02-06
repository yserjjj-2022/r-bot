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

# --- LLM Abstraction (To be replaced by DeepSeek Client) ---

class AbstractLLMClient(ABC):
    @abstractmethod
    async def generate_signal(self, system_prompt: str, user_text: str) -> AgentSignal:
        pass

class MockLLMClient(AbstractLLMClient):
    """
    Эмулятор LLM для тестов без API ключей.
    Возвращает заглушки, но разные для разных агентов.
    """
    async def generate_signal(self, system_prompt: str, user_text: str) -> AgentSignal:
        # Имитация задержки "мышления"
        await asyncio.sleep(0.1)
        
        # Простая эвристика для демонстрации разницы агентов
        msg_lower = user_text.lower()
        score = 5.0
        rationale = "Neutral analysis."
        
        if "amygdala" in system_prompt.lower():
            if "ненавижу" in msg_lower or "устал" in msg_lower:
                score = 9.0
                rationale = "DETECTED: Strong negative emotion (hate/fatigue). Potential conflict trigger."
            else:
                score = 2.0
                rationale = "Environment seems safe."
                
        elif "striatum" in system_prompt.lower():
            if "хочу" in msg_lower or "интересно" in msg_lower:
                score = 8.5
                rationale = "DETECTED: User desire/curiosity. Opportunity for reward."
            else:
                score = 3.0
                rationale = "No obvious rewards detected."
                
        elif "logic" in system_prompt.lower():
            score = 6.0
            rationale = "Standard processing required. No logical fallacies detected."
            
        elif "social" in system_prompt.lower():
            if "привет" in msg_lower or "спасибо" in msg_lower:
                score = 8.0
                rationale = "Social ritual detected. Politeness required."
            elif "ненавижу" in msg_lower:
                score = 7.0
                rationale = "User is upset. Empathy protocol required."

        return AgentSignal(
            agent_name=AgentType.PREFRONTAL, # Заглушка, перепишется в агенте
            score=score,
            rationale_short=rationale,
            confidence=0.8,
            latency_ms=100
        )

# --- Base Agent ---

class BaseAgent(ABC):
    def __init__(self, llm: AbstractLLMClient):
        self.llm = llm

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
            # Берем "лучшее" совпадение (в реальности тут будет cosine similarity score)
            best_match = episodes[0] 
            # Допустим, мы считаем теги как маркер похожести
            score = 8.0 
            rationale = f"Déjà vu! Similar to episode: '{best_match['raw_text']}'"

        signal = AgentSignal(
            agent_name=AgentType.INTUITION,
            score=score,
            rationale_short=rationale,
            confidence=0.9 if score > 7 else 0.2,
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
        system_prompt = "You are the AMYGDALA. Detect threats, aggression, or user distress."
        
        signal = await self.llm.generate_signal(system_prompt, message.text)
        signal.agent_name = AgentType.AMYGDALA
        
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
        system_prompt = "You are the PREFRONTAL CORTEX. Analyze logic, facts, and required tasks."
        
        signal = await self.llm.generate_signal(system_prompt, message.text)
        signal.agent_name = AgentType.PREFRONTAL
        
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
        system_prompt = "You are the SOCIAL CORTEX. Ensure politeness, empathy, and social adherence."
        
        signal = await self.llm.generate_signal(system_prompt, message.text)
        signal.agent_name = AgentType.SOCIAL
        
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
        system_prompt = "You are the STRIATUM. Seek rewards, curiosity, and engagement opportunities."
        
        signal = await self.llm.generate_signal(system_prompt, message.text)
        signal.agent_name = AgentType.STRIATUM
        
        # Зависит от Risk Tolerance (авантюризм)
        modifier = 0.5 + (sliders.risk_tolerance * 0.8)
        return self._apply_modulation(signal, modifier)
