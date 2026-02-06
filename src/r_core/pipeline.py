import asyncio
from typing import Dict, List, Optional
from datetime import datetime

from .schemas import (
    IncomingMessage, 
    CoreResponse, 
    CoreAction, 
    BotConfig, 
    ProcessingMode,
    AgentType
)
from .memory import MemorySystem
from .agents import (
    MockLLMClient, # В будущем заменим на RealDeepSeekClient
    IntuitionAgent,
    AmygdalaAgent,
    PrefrontalAgent,
    SocialAgent,
    StriatumAgent
)

class RCoreKernel:
    def __init__(self, config: BotConfig):
        self.config = config
        self.llm = MockLLMClient() # Пока мок
        self.memory = MemorySystem()
        
        # Инициализация агентов
        self.agents = [
            IntuitionAgent(self.llm),
            AmygdalaAgent(self.llm),
            PrefrontalAgent(self.llm),
            SocialAgent(self.llm),
            StriatumAgent(self.llm)
        ]

    async def process_message(self, message: IncomingMessage) -> CoreResponse:
        start_time = datetime.now()
        
        # 1. Perception & Memorization (Parallel)
        # В реальности тут вызов LLM для извлечения фактов. Пока заглушка.
        perception_task = self._mock_perception(message)
        
        # 2. Retrieval (Recall)
        # Ищем контекст по тексту сообщения
        context = await self.memory.recall_context(message.user_id, message.text)
        
        # Ждем завершения восприятия, чтобы сохранить новые факты
        extraction_result = await perception_task
        await self.memory.memorize_event(message, extraction_result)

        # 3. Parliament Debate (Agents)
        # Запускаем всех агентов параллельно
        agent_tasks = [
            agent.process(message, context, self.config.sliders) 
            for agent in self.agents
        ]
        signals = await asyncio.gather(*agent_tasks)
        
        # 4. Arbitration (Winner Selection)
        # Сортируем по score
        signals.sort(key=lambda s: s.score, reverse=True)
        winner = signals[0]
        
        # 5. Response Generation (Action)
        # Генерируем ответ в стиле победителя
        response_text = await self._generate_response(winner.agent_name, message.text)
        
        # Сборка финального ответа
        latency = (datetime.now() - start_time).total_seconds() * 1000
        
        return CoreResponse(
            actions=[
                CoreAction(type="send_text", payload={"text": response_text})
            ],
            winning_agent=winner.agent_name,
            processing_mode=ProcessingMode.SLOW_PATH,
            internal_stats={
                "latency_ms": int(latency),
                "winner_score": winner.score,
                "winner_reason": winner.rationale_short
            }
        )

    async def _mock_perception(self, message: IncomingMessage) -> Dict:
        """
        Имитация работы DeepSeek по извлечению фактов (Extractor).
        """
        await asyncio.sleep(0.1)
        return {
            "triples": [], # Пока пусто, чтобы не засорять
            "anchors": [],
            "volitional_pattern": None
        }

    async def _generate_response(self, agent_name: AgentType, user_text: str) -> str:
        """
        Имитация генерации текста в стиле победителя.
        """
        styles = {
            AgentType.AMYGDALA: f"⚠️ ОСТОРОЖНО! Я чувствую напряжение в твоих словах: '{user_text}'. Давай успокоимся.",
            AgentType.SOCIAL: f"Ох, я понимаю... '{user_text}' звучит грустно. Я с тобой, держись! ❤️",
            AgentType.PREFRONTAL: f"Принято. Анализирую запрос: '{user_text}'. Задача ясна.",
            AgentType.STRIATUM: f"Ого! '{user_text}'?! Это звучит интересно! Давай попробуем!",
            AgentType.INTUITION: f"Хм... '{user_text}'... мне кажется, я уже видел такое раньше."
        }
        return styles.get(agent_name, "Я здесь.")
