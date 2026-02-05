import asyncio
import random
import logging
from app.modules.hub import EventHub, EventType, RBotEvent

logger = logging.getLogger("MockMarket")

class MockMarketWorker:
    """
    Симулятор рынка для отладки Хаба.
    Генерирует случайные тики для заданных инструментов.
    """
    def __init__(self, hub: EventHub, interval_sec: float = 5.0):
        self.hub = hub
        self.interval = interval_sec
        self.tickers = {
            "SBER": 250.0,
            "GAZP": 160.0,
            "LKOH": 6000.0,
            "USDRUB": 90.0
        }
        self._is_running = False

    async def start(self):
        self._is_running = True
        logger.info("MockMarketWorker started")
        while self._is_running:
            await self._generate_tick()
            await asyncio.sleep(self.interval)

    async def stop(self):
        self._is_running = False
        logger.info("MockMarketWorker stopped")

    async def _generate_tick(self):
        """Создает случайное изменение цены и отправляет событие"""
        ticker = random.choice(list(self.tickers.keys()))
        current_price = self.tickers[ticker]
        
        # Случайное движение от -2% до +2%
        change_pct = random.uniform(-0.02, 0.02)
        new_price = round(current_price * (1 + change_pct), 2)
        
        # Обновляем "рынок"
        self.tickers[ticker] = new_price
        
        # Формируем пейлоад
        payload = {
            "ticker": ticker,
            "price": new_price,
            "change_pct": round(change_pct * 100, 2), # в процентах
            "prev_price": current_price
        }

        # Отправляем в Хаб
        event = RBotEvent(
            event_type=EventType.SIGNAL_UPDATE,
            source="MOCK_MARKET",
            payload=payload
        )
        
        await self.hub.publish(event)
        logger.debug(f"Tick generated: {ticker} {new_price} ({payload['change_pct']}%)")
