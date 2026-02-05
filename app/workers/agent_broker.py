import logging
import asyncio
from app.modules.hub import EventHub, EventType, RBotEvent
from app.modules.agent_models import AgentProfile, AgentRole

logger = logging.getLogger("BrokerAgent")

# Определяем профиль "Честного Брокера"
BROKER_PROFILE = AgentProfile(
    name="Max Capital",
    role=AgentRole.BROKER,
    system_prompt="""
    Ты — профессиональный биржевой брокер. Твоя цель — максимизировать торговый оборот клиента.
    Ты видишь возможности в любой волатильности.
    Ты используешь профессиональный сленг (просадка, отскок, гэп, лонг, шорт), но говоришь кратко и понятно.
    Всегда предлагай действие (Call to Action).
    Не ври, но подавай факты так, чтобы побудить к сделке.
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
        # Подписываемся на изменения рынка
        self.hub.subscribe(EventType.SIGNAL_UPDATE, self._on_market_signal)
        logger.info(f"Agent '{self.profile.name}' started and listening.")

    async def stop(self):
        self._is_running = False
        logger.info(f"Agent '{self.profile.name}' stopped.")

    async def _on_market_signal(self, event: RBotEvent):
        """
        Основной цикл реакции на рынок.
        В будущем здесь будет вызов LLM (GigaChat/OpenAI).
        Пока — эвристика на шаблонах.
        """
        if not self._is_running:
            return

        payload = event.payload
        ticker = payload.get("ticker")
        change = payload.get("change_pct", 0)
        price = payload.get("price")

        # Фильтр шума: реагируем только на движение > 1.5%
        if abs(change) < 1.5:
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
        Заглушка вместо LLM. Выбирает реплику в зависимости от знака изменения.
        """
        if change > 0:
            # Рост
            return f"📈 {ticker} летит вверх (+{change}%)! Пробиваем сопротивление на {price}. Срочно докупаем, пока не ушли на луну! 🚀"
        else:
            # Падение
            return f"📉 {ticker} просел на {change}%. Отличная точка входа по {price}. Это просто коррекция, надо брать дно! 💰"
