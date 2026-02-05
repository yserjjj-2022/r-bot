import logging
import asyncio
from app.modules.hub import EventHub, EventType, RBotEvent

logger = logging.getLogger("BrokerAgent")

class BrokerAgent:
    """
    Агент-Брокер (The Salesman).
    Цель: Стимулировать торговую активность, используя рыночные инфоповоды.
    Стиль общения: Профессиональный, деловой, с легким акцентом на возможности.
    """
    def __init__(self, hub: EventHub, agent_id: str = "BROKER_01"):
        self.hub = hub
        self.agent_id = agent_id
        
    async def start(self):
        # Подписываемся на изменения рынка
        self.hub.subscribe(EventType.SIGNAL_UPDATE, self._on_market_signal)
        # Подписываемся на действия пользователя (чтобы хвалить за сделки)
        self.hub.subscribe(EventType.USER_ACTION, self._on_user_action)
        logger.info(f"Agent {self.agent_id} started listening")

    async def _on_market_signal(self, event: RBotEvent):
        """Реакция на рыночные данные"""
        payload = event.payload
        ticker = payload.get("ticker")
        change = payload.get("change_pct", 0)
        price = payload.get("price")

        # Фильтр шума: реагируем только на изменения > 1%
        if abs(change) < 1.0:
            return

        # Генерация "мысли" агента (в будущем здесь будет LLM)
        if change < -1.5:
            message = f"📉 {ticker}: коррекция на {change}%. Текущая цена {price}. Техническая картина допускает вход в длинную позицию на отскок."
        elif change > 1.5:
            message = f"📈 {ticker}: рост на {change}% (цена {price}). Наблюдаем сильный импульс. Возможно, стоит усилить позицию по тренду."
        else:
            return

        # Отправка реакции в Хаб
        response_event = RBotEvent(
            event_type=EventType.AGENT_MESSAGE,
            source=self.agent_id,
            payload={
                "text": message,
                "target_user": "ALL", # Пока вещаем всем
                "intent": "persuasion_trade"
            }
        )
        await self.hub.publish(response_event)
        logger.info(f"Broker sent message: {message}")

    async def _on_user_action(self, event: RBotEvent):
        """Реакция на действия пользователя"""
        # Заглушка: Брокер всегда одобряет активность
        action_type = event.payload.get("action_type")
        if action_type == "ORDER_NEW":
            msg = "Ордер принят в обработку. Оперативное решение."
            await self.hub.publish(RBotEvent(
                event_type=EventType.AGENT_MESSAGE,
                source=self.agent_id,
                payload={"text": msg}
            ))
