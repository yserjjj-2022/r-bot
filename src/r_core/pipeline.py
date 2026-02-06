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
from .infrastructure.llm import LLMService
from .agents import (
    IntuitionAgent,
    AmygdalaAgent,
    PrefrontalAgent,
    SocialAgent,
    StriatumAgent
)

class RCoreKernel:
    def __init__(self, config: BotConfig):
        self.config = config
        self.llm = LLMService() 
        self.memory = MemorySystem(store=None) # Will use PostgresMemoryStore by default
        
        # Инициализация агентов (LLMService прокидывается внутри, если не передан явно)
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
        # Ищем контекст по тексту сообщения (Embeddings + DB)
        context = await self.memory.recall_context(message.user_id, message.text)
        
        # Ждем завершения восприятия, чтобы сохранить новые факты
        extraction_result = await perception_task
        await self.memory.memorize_event(message, extraction_result)

        # 3. Parliament Debate (Agents)
        # Запускаем всех агентов параллельно. Теперь они ходят в реальный API.
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
        # Генерируем ответ. Можно подключить LLM, но для теста оставим шаблоны,
        # чтобы четко видеть, какой агент победил.
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
        Здесь стоит подключить реальный LLM для извлечения троек и цитат.
        Для Sprint 2 оставим базовое сохранение цитаты.
        """
        await asyncio.sleep(0.1)
        # Эмулируем, что мы "запомнили" сообщение как эпизод
        return {
            "triples": [], 
            "anchors": [
                {
                    "raw_text": message.text,
                    "emotion_score": 0.5,
                    "tags": ["auto-memory"]
                }
            ],
            "volitional_pattern": None
        }

    async def _generate_response(self, agent_name: AgentType, user_text: str) -> str:
        """
        Имитация генерации текста в стиле победителя.
        """
        styles = {
            AgentType.AMYGDALA: f"⚠️ [Amygdala] ОСТОРОЖНО! Я чувствую напряжение: '{user_text}'.",
            AgentType.SOCIAL: f"❤️ [Social] Ох, я понимаю... '{user_text}' звучит важно. Я с тобой!",
            AgentType.PREFRONTAL: f"🧠 [Logic] Принято. Анализирую: '{user_text}'.",
            AgentType.STRIATUM: f"🔥 [Striatum] Ого! '{user_text}'?! Звучит хайпово!",
            AgentType.INTUITION: f"🔮 [Intuition] Хм... '{user_text}'... дежавю."
        }
        return styles.get(agent_name, "Я здесь.")
