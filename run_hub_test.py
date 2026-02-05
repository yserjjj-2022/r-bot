import asyncio
import logging
from app.modules.hub import EventHub, RBotEvent, EventType
from app.workers.mock_market import MockMarketWorker
from app.workers.agent_broker import BrokerAgentWorker

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("TEST_RUNNER")

async def console_logger(event: RBotEvent):
    """Просто печатает все события в консоль красивым цветом"""
    if event.event_type == EventType.SIGNAL_UPDATE:
        # Рынок - серым/синим
        payload = event.payload
        logger.info(f"🔵 MARKET: {payload['ticker']} {payload['price']} ({payload['change_pct']}%)")
    
    elif event.event_type == EventType.AGENT_MESSAGE:
        # Агент - зеленым/ярким
        payload = event.payload
        print(f"\n🔥🔥🔥 {payload['agent_name']} SAYS: {payload['text']}\n")

async def main():
    logger.info("Starting Hub Simulation...")

    # 1. Создаем Хаб
    hub = EventHub()

    # 2. Подписываем консольный логгер на всё
    hub.subscribe(EventType.SIGNAL_UPDATE, console_logger)
    hub.subscribe(EventType.AGENT_MESSAGE, console_logger)

    # 3. Создаем воркеров
    market = MockMarketWorker(hub, interval_sec=2.0) # Быстрый рынок для теста
    broker = BrokerAgentWorker(hub)

    # 4. Запускаем всё
    await hub.start()
    
    # Запускаем воркеров как фоновые задачи
    tasks = [
        asyncio.create_task(market.start()),
        asyncio.create_task(broker.start())
    ]

    try:
        # Работаем 30 секунд и выходим
        logger.info("System is running. Press Ctrl+C to stop manually.")
        await asyncio.sleep(30)
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Shutting down...")
        await market.stop()
        await broker.stop()
        await hub.stop()
        
        # Отменяем таски
        for t in tasks: t.cancel()
        logger.info("Done.")

if __name__ == "__main__":
    asyncio.run(main())
