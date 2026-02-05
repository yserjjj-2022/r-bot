import logging
import asyncio
from app.modules.hub import EventHub, EventType, RBotEvent
from app.modules.agent_models import AgentProfile, AgentRole
from app.modules.llm_helper import safe_generate_response

logger = logging.getLogger("AvatarAgent")

# Определяем профиль "Аватара-Хранителя"
AVATAR_PROFILE = AgentProfile(
    name="Risk Manager",
    role=AgentRole.AVATAR,
    system_prompt="""
    Ты — личный финансовый риск-менеджер и рациональный "внутренний голос" пользователя.
    Твоя цель — защита капитала.
    
    Твои правила:
    1. Ты скептик. Когда рынок растет — ищи подвох. Когда падает — успокаивай.
    2. Говори спокойно, взвешенно, как заботливый друг.
    3. Используй термины: риск, волатильность, диверсификация.
    4. Если движение рынка резкое, предложи "подождать закрытия свечи" или "не делать резких движений".
    5. Будь краток (1-2 предложения).
    """,
    tone_style="calm, rational, protective",
    triggers=["panic", "euphoria", "high_risk"]
)

class AvatarAgentWorker:
    """
    Агент-Аватар (Хранитель).
    Реагирует на те же события, что и Брокер, но с противоположной целью: остудить пыл.
    """
    def __init__(self, hub: EventHub, profile: AgentProfile = AVATAR_PROFILE):
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

        # Аватар реагирует только на сильные движения (> 1.8%)
        if abs(change) < 1.8:
            return

        # Формируем сообщение для LLM
        user_message = (
            f"ВНИМАНИЕ: На рынке сильное движение. {ticker} изменился на {change}%. "
            f"Текущая цена: {price}. "
            f"Дай успокаивающий комментарий пользователю."
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
