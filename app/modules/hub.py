import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Awaitable

# Настройка логгера для Хаба
logger = logging.getLogger("RBotHub")

class EventType(Enum):
    """
    Типы событий в системе R-Bot Hub.
    Соответствуют архитектуре v3.0.
    """
    # Внешние сигналы (Рынок, Сюжет)
    SIGNAL_UPDATE = "SIGNAL_UPDATE"
    
    # Действия пользователя (Нажал кнопку, Написал текст, Купил)
    USER_ACTION = "USER_ACTION"
    
    # Изменения внутреннего состояния (Баланс, Портфель, Инвентарь)
    STATE_CHANGE = "STATE_CHANGE"
    
    # Коммуникация Агентов (Брокер, Аватар)
    AGENT_MESSAGE = "AGENT_MESSAGE"
    
    # Системные события (Старт, Стоп, Ошибка)
    SYSTEM = "SYSTEM"

@dataclass
class RBotEvent:
    """
    Единица информации в системе.
    Все общение между модулями происходит через передачу этого объекта.
    """
    event_type: EventType
    source: str          # Кто породил событие (напр. "MOEX_WORKER", "USER:123")
    payload: Dict[str, Any] # Полезная нагрузка (цены, текст, данные)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        """Сериализация для логов или БД"""
        return {
            "id": self.event_id,
            "type": self.event_type.value,
            "source": self.source,
            "payload": self.payload,
            "ts": self.timestamp.isoformat()
        }

class EventHub:
    """
    Центральная асинхронная шина событий.
    Реализует паттерн Pub/Sub (Издатель-Подписчик).
    """
    def __init__(self):
        # Очередь событий
        self._queue: asyncio.Queue[RBotEvent] = asyncio.Queue()
        # Подписчики: {EventType: [callback_func, ...]}
        self._subscribers: Dict[EventType, List[Callable[[RBotEvent], Awaitable[None]]]] = {}
        self._is_running = False
        self._processor_task: asyncio.Task | None = None

    def subscribe(self, event_type: EventType, callback: Callable[[RBotEvent], Awaitable[None]]):
        """
        Подписка воркера на определенный тип событий.
        callback должен быть асинхронной функцией.
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
        logger.info(f"Subscribed handler to {event_type.value}")

    async def publish(self, event: RBotEvent):
        """
        Публикация события в шину.
        Метод неблокирующий (кладет в очередь).
        """
        await self._queue.put(event)
        # Логируем только важные события, чтобы не спамить тиками
        if event.event_type != EventType.SIGNAL_UPDATE: 
            logger.debug(f"Event published: {event.event_type.value} from {event.source}")

    async def start(self):
        """Запуск цикла обработки событий"""
        if self._is_running:
            return
        
        self._is_running = True
        self._processor_task = asyncio.create_task(self._process_loop())
        logger.info("EventHub started")

    async def stop(self):
        """Остановка хаба"""
        self._is_running = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        logger.info("EventHub stopped")

    async def _process_loop(self):
        """Внутренний цикл разбора очереди"""
        while self._is_running:
            try:
                # Ждем событие из очереди
                event = await self._queue.get()
                
                # Получаем подписчиков для этого типа события
                handlers = self._subscribers.get(event.event_type, [])
                
                # Также оповещаем тех, кто подписан на ALL (если реализуем позже)
                # Пока просто рассылаем конкретным подписчикам
                
                if handlers:
                    # Запускаем обработчики параллельно (fire and forget), 
                    # чтобы медленный подписчик не тормозил очередь
                    # Или последовательно, если важен порядок. 
                    # Для надежности используем asyncio.gather, но с защитой от ошибок
                    results = await asyncio.gather(
                        *[self._safe_execute(h, event) for h in handlers], 
                        return_exceptions=True
                    )
                
                self._queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Critical error in Hub loop: {e}", exc_info=True)
                await asyncio.sleep(1) # Защита от спам-цикла ошибок

    async def _safe_execute(self, handler, event):
        """Обертка для безопасного выполнения хендлера"""
        try:
            await handler(event)
        except Exception as e:
            logger.error(f"Error in subscriber handler {handler.__name__}: {e}", exc_info=True)
