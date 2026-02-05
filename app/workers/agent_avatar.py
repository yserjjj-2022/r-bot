import logging
import asyncio
from app.modules.hub import EventHub, EventType, RBotEvent
from app.modules.agent_models import AgentProfile, AgentRole

logger = logging.getLogger("AvatarAgent")

# Определяем профиль "Аватара-Хранителя"
AVATAR_PROFILE = AgentProfile(
    name="Risk Manager",
    role=AgentRole.AVATAR,
    system_prompt="""
    Ты — личный финансовый риск-менеджер и рациональный "внутренний голос" пользователя.
    Твоя цель — защита капитала и предотвращение эмоциональных решений (FOMO, паника).
    Ты скептик. Когда все кричат "покупай", ты ищешь подвох.
    Когда рынок падает, ты напоминаешь о долгосрочной стратегии.
    Говори спокойно, взвешенно, используй термины "риск", "волатильность", "фундаментал".
    Твоя задача — не запретить, а заставить задуматься.
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
        # В будущем подпишемся еще и на USER_ACTION (чтобы отговаривать от сделок)
        logger.info(f"Agent '{self.profile.name}' started and watching.")

    async def stop(self):
        self._is_running = False
        logger.info(f"Agent '{self.profile.name}' stopped.")

    async def _on_market_signal(self, event: RBotEvent):
        """
        Реакция на рынок.
        Аватар вступает, когда волатильность высокая, чтобы предупредить о рисках.
        """
        if not self._is_running:
            return

        payload = event.payload
        ticker = payload.get("ticker")
        change = payload.get("change_pct", 0)
        price = payload.get("price")

        # Аватар реагирует чуть реже Брокера, только на сильные движения (> 1.8%)
        if abs(change) < 1.8:
            return

        # Генерируем "мысль" агента
        message_text = self._generate_stub_response(ticker, change, price)
        
        # Публикуем ответ в Хаб
        response_event = RBotEvent(
            event_type=EventType.AGENT_MESSAGE,
            source=f"AGENT:{self.profile.role.value}",
            payload={
                "agent_name": self.profile.name,
                "text": message_text,
                "context": {"ticker": ticker, "change": change}
            }
        )
        await self.hub.publish(response_event)

    def _generate_stub_response(self, ticker, change, price) -> str:
        """
        Заглушка. Успокаивает пользователя.
        """
        if change > 0:
            # Рост (Эйфория)
            return f"🛡️ {ticker} вырос на {change}%. Осторожно, это может быть ложный пробой. Не поддавайся FOMO. Помнишь наш план по фиксации прибыли?"
        else:
            # Падение (Паника)
            return f"🧘 {ticker} упал на {change}%. Не паникуй. Фундаментально компания сильная. Просадка — это нормально, не продавай на эмоциях."
