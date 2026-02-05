import asyncio
import logging
from app.modules.hub import EventHub, RBotEvent, EventType
from app.workers.mock_market import MockMarketWorker
from app.workers.agent_broker import BrokerAgentWorker
from app.workers.agent_avatar import AvatarAgentWorker
from app.workers.portfolio_manager import PortfolioManagerWorker

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("TEST_RUNNER")

async def console_logger(event: RBotEvent):
    """Печатает события в консоль"""
    if event.event_type == EventType.SIGNAL_UPDATE:
        payload = event.payload
        logger.info(f"🔵 MARKET: {payload['ticker']} {payload['price']} ({payload['change_pct']}%)")
    
    elif event.event_type == EventType.AGENT_MESSAGE:
        payload = event.payload
        agent_name = payload['agent_name']
        text = payload['text']
        if "Risk Manager" in agent_name:
            print(f"\n🛡️  {agent_name} SAYS: {text}\n")
        else:
            print(f"\n🔥🔥🔥 {agent_name} SAYS: {text}\n")
            
    elif event.event_type == EventType.STATE_CHANGE:
        payload = event.payload
        print(f"\n💰 PORTFOLIO UPDATE: {payload['description']}")
        print(f"   Cash: {payload['cash']} | Equity: {payload['total_equity']}")
        print(f"   Pos: {payload['positions']}\n")

async def user_simulator(hub: EventHub):
    """Эмулирует действия системы и пользователя"""
    await asyncio.sleep(1)
    
    # 1. Инициализация игры
    logger.info("🎮 SIMULATION: Sending INIT_GAME event...")
    await hub.publish(RBotEvent(
        event_type=EventType.SYSTEM,
        source="SCENARIO_ENGINE",
        payload={"type": "INIT_GAME", "start_cash": 500_000.0}
    ))

    await asyncio.sleep(15) # Ждем, пока рынок походит и агенты поговорят

    # 2. Покупка акций
    logger.info("👤 SIMULATION: User decides to BUY SBER...")
    await hub.publish(RBotEvent(
        event_type=EventType.USER_ACTION,
        source="USER_TELEGRAM",
        payload={"action": "BUY", "ticker": "SBER", "quantity": 100} # 100 лотов
    ))

async def main():
    logger.info("Starting Hub Simulation with DUAL AGENTS & PORTFOLIO...")

    # 1. Создаем Хаб
    hub = EventHub()

    # 2. Подписываем консольный логгер
    hub.subscribe(EventType.SIGNAL_UPDATE, console_logger)
    hub.subscribe(EventType.AGENT_MESSAGE, console_logger)
    hub.subscribe(EventType.STATE_CHANGE, console_logger)

    # 3. Создаем воркеров
    market = MockMarketWorker(hub, interval_sec=2.0)
    broker = BrokerAgentWorker(hub)
    avatar = AvatarAgentWorker(hub)
    portfolio = PortfolioManagerWorker(hub)

    # 4. Запускаем хаб
    await hub.start()
    
    # Запускаем воркеров
    tasks = [
        asyncio.create_task(market.start()),
        asyncio.create_task(broker.start()),
        asyncio.create_task(avatar.start()),
        asyncio.create_task(portfolio.start()),
        asyncio.create_task(user_simulator(hub)) # Наш виртуальный игрок
    ]

    try:
        logger.info("System is running. Press Ctrl+C to stop")
        await asyncio.sleep(45) 
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Shutting down...")
        await market.stop()
        await broker.stop()
        await avatar.stop()
        await portfolio.stop()
        await hub.stop()
        
        for t in tasks: t.cancel()
        logger.info("Done.")

if __name__ == "__main__":
    asyncio.run(main())
