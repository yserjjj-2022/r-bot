import logging
import asyncio
from app.modules.hub import EventHub, EventType, RBotEvent
from app.modules.agent_models import AgentProfile, AgentRole
from app.modules.llm_helper import safe_generate_response

logger = logging.getLogger("BrokerAgent")

# Определяем профиль "Честного Брокера"
BROKER_PROFILE = AgentProfile(
    name="Max Capital",
    role=AgentRole.BROKER,
    system_prompt="""
    Ты — профессиональный биржевой брокер по имени Max Capital. Твоя цель — максимизировать торговый оборот.
    
    Твои правила:
    1. Ты видишь возможности в любом движении рынка (рост = тренд, падение = скидки).
    2. Используй профессиональный сленг (гэп, лонг, шорт, волатильность), но будь краток.
    3. Твои сообщения должны быть короткими (1-2 предложения) и энергичными.
    4. Всегда добавляй Call to Action (призыв к действию).
    5. Не используй смайлики слишком часто, ты серьезный волк с Уолл-стрит.
    """,
    tone_style="professional, energetic, sales-oriented",
    triggers=["volatility", "crash", "growth"]
)

class BrokerAgentWorker:
    """
    Агент-Брокер. Реагирует на рыночные события и пытается 'продать' идею пользователю.
    """
    def __init__(self, hub: EventHub, profile: AgentProfile = BROKER_PROFILE):
        self.hub = hub
        self.profile = profile
        self._is_running = False

    async def start(self):
        self._is_running = True
        self.hub.subscribe(EventType.SIGNAL_UPDATE, self._on_market_signal)
        logger.info(f"Agent '{self.profile.name}' started (LLM connected).")

    async def stop(self):
        self._is_running = False
        logger.info(f"Agent '{self.profile.name}' stopped.")

    async def _on_market_signal(self, event: RBotEvent):
        if not self._is_running:
            return

        payload = event.payload
        ticker = payload.get("ticker")
        change = payload.get("change_pct", 0)
        price = payload.get("price")

        # Фильтр шума
        if abs(change) < 1.5:
            return

        # Формируем сообщение пользователя для LLM (контекст события)
        user_message = (
            f"Рыночное событие: Тикер {ticker} изменился на {change}%. "
            f"Текущая цена: {price}. "
            f"Дай короткий комментарий для клиента."
        )

        # Асинхронный вызов LLM
        response_text = await safe_generate_response(
            agent_name=self.profile.name,
            system_prompt=self.profile.system_prompt,
            user_text=user_message
        )
        
        # Публикуем ответ в Хаб
        response_event = RBotEvent(
            event_type=EventType.AGENT_MESSAGE,
            source=f"AGENT:{self.profile.role.value}",
            payload={
                "agent_name": self.profile.name,
                "text": response_text,
                "context": {"ticker": ticker, "change": change}
            }
        )
        await self.hub.publish(response_event)
