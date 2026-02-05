import asyncio
import logging
from app.modules.hub import EventHub, RBotEvent, EventType
from app.workers.mock_market import MockMarketWorker
from app.workers.agent_broker import BrokerAgentWorker
from app.workers.agent_avatar import AvatarAgentWorker

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
        # Агент - разные цвета для разных ролей
        payload = event.payload
        agent_name = payload['agent_name']
        text = payload['text']
        
        if "Risk Manager" in agent_name:
            print(f"\n🛡️  {agent_name} SAYS: {text}\n")
        else:
            print(f"\n🔥🔥🔥 {agent_name} SAYS: {text}\n")

async def main():
    logger.info("Starting Hub Simulation with DUAL AGENTS...")

    # 1. Создаем Хаб
    hub = EventHub()

    # 2. Подписываем консольный логгер
    hub.subscribe(EventType.SIGNAL_UPDATE, console_logger)
    hub.subscribe(EventType.AGENT_MESSAGE, console_logger)

    # 3. Создаем воркеров
    market = MockMarketWorker(hub, interval_sec=2.0)
    broker = BrokerAgentWorker(hub)
    avatar = AvatarAgentWorker(hub)

    # 4. Запускаем хаб
    await hub.start()
    
    # Запускаем воркеров
    tasks = [
        asyncio.create_task(market.start()),
        asyncio.create_task(broker.start()),
        asyncio.create_task(avatar.start())
    ]

    try:
        logger.info("System is running. Wait for volatility... (Press Ctrl+C to stop)")
        await asyncio.sleep(45) # Чуть дольше, чтобы поймать редкие события
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Shutting down...")
        await market.stop()
        await broker.stop()
        await avatar.stop()
        await hub.stop()
        
        for t in tasks: t.cancel()
        logger.info("Done.")

if __name__ == "__main__":
    asyncio.run(main())
