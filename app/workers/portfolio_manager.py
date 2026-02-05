import logging
import asyncio
from typing import Dict, Optional
from dataclasses import dataclass, field

from app.modules.hub import EventHub, EventType, RBotEvent

logger = logging.getLogger("PortfolioMgr")

@dataclass
class PortfolioState:
    cash: float = 0.0  # Теперь 0 по умолчанию, ждем инициализации
    positions: Dict[str, int] = field(default_factory=dict)
    trades_count: int = 0
    total_commission_paid: float = 0.0

class PortfolioManagerWorker:
    """
    Управляет состоянием счета пользователя.
    Поддерживает динамическую инициализацию и пополнения.
    """
    def __init__(self, hub: EventHub):
        self.hub = hub
        self.state = PortfolioState()
        self.last_prices: Dict[str, float] = {}
        self._is_running = False

    async def start(self):
        self._is_running = True
        self.hub.subscribe(EventType.SIGNAL_UPDATE, self._on_market_update)
        self.hub.subscribe(EventType.USER_ACTION, self._on_user_action)
        # Подписываемся на системные события для инициализации и пополнения
        self.hub.subscribe(EventType.SYSTEM, self._on_system_event)
        
        logger.info("Portfolio Manager started. Waiting for initialization...")

    async def stop(self):
        self._is_running = False
        logger.info("Portfolio Manager stopped.")

    async def _on_market_update(self, event: RBotEvent):
        if not self._is_running: return
        payload = event.payload
        if payload.get("ticker") and payload.get("price"):
            self.last_prices[payload["ticker"]] = float(payload["price"])

    async def _on_system_event(self, event: RBotEvent):
        """Обработка системных событий (старт игры, зарплата)"""
        if not self._is_running: return
        
        payload = event.payload
        event_subtype = payload.get("type") # INIT_GAME, DEPOSIT, etc.

        if event_subtype == "INIT_GAME":
            start_cash = float(payload.get("start_cash", 100_000.0))
            self.state = PortfolioState(cash=start_cash)
            logger.info(f"💰 GAME INIT: Starting balance set to {start_cash} RUB")
            await self._publish_state_change("GAME_STARTED", f"Счет открыт. Баланс: {start_cash}")

        elif event_subtype == "DEPOSIT":
            amount = float(payload.get("amount", 0))
            source = payload.get("source", "external")
            if amount > 0:
                self.state.cash += amount
                logger.info(f"💸 DEPOSIT: +{amount} RUB from {source}")
                await self._publish_state_change("DEPOSIT", f"Поступление средств: {amount} ({source})")

    async def _on_user_action(self, event: RBotEvent):
        if not self._is_running: return

        payload = event.payload
        action_type = payload.get("action") 
        ticker = payload.get("ticker")
        quantity = payload.get("quantity", 1)

        if not (action_type and ticker): return

        # Проверка инициализации
        if self.state.cash <= 0 and self.state.trades_count == 0 and not self.state.positions:
            # Если денег 0 и не было сделок — скорее всего игра не началась, но дадим уйти в минус? 
            # Нет, лучше реджект.
            if self.state.cash == 0: 
                 await self._reject_order(ticker, "Счет не пополнен")
                 return

        current_price = self.last_prices.get(ticker)
        if not current_price:
            await self._reject_order(ticker, "Нет рыночной цены")
            return

        if action_type == "BUY":
            await self._execute_buy(ticker, current_price, quantity)
        elif action_type == "SELL":
            await self._execute_sell(ticker, current_price, quantity)

    async def _execute_buy(self, ticker: str, price: float, quantity: int):
        total_cost = price * quantity
        commission = total_cost * 0.003
        total_spend = total_cost + commission

        if self.state.cash >= total_spend:
            self.state.cash -= total_spend
            self.state.positions[ticker] = self.state.positions.get(ticker, 0) + quantity
            self.state.trades_count += 1
            self.state.total_commission_paid += commission
            
            logger.info(f"✅ BUY EXEC: {ticker} x {quantity} @ {price}. Comm: {commission:.2f}")
            await self._publish_state_change("ORDER_FILLED", f"Куплено {quantity} {ticker} по {price}")
        else:
            await self._reject_order(ticker, f"Недостаточно средств (нужно {total_spend:.2f})")

    async def _execute_sell(self, ticker: str, price: float, quantity: int):
        current_qty = self.state.positions.get(ticker, 0)
        
        if current_qty >= quantity:
            total_revenue = price * quantity
            commission = total_revenue * 0.003
            net_income = total_revenue - commission

            self.state.cash += net_income
            self.state.positions[ticker] -= quantity
            if self.state.positions[ticker] == 0:
                del self.state.positions[ticker]
            
            self.state.trades_count += 1
            self.state.total_commission_paid += commission

            logger.info(f"✅ SELL EXEC: {ticker} x {quantity} @ {price}. Comm: {commission:.2f}")
            await self._publish_state_change("ORDER_FILLED", f"Продано {quantity} {ticker} по {price}")
        else:
            await self._reject_order(ticker, "Недостаточно бумаг")

    async def _reject_order(self, ticker, reason):
        logger.warning(f"❌ ORDER REJECTED {ticker}: {reason}")
        await self.hub.publish(RBotEvent(
            event_type=EventType.SYSTEM,
            source="PORTFOLIO",
            payload={"type": "ERROR", "text": f"Ошибка заявки: {reason}"}
        ))

    async def _publish_state_change(self, change_reason: str, description: str):
        equity = self.state.cash
        for t, qty in self.state.positions.items():
            price = self.last_prices.get(t, 0)
            equity += price * qty

        payload = {
            "reason": change_reason,
            "description": description,
            "cash": round(self.state.cash, 2),
            "positions": self.state.positions,
            "total_equity": round(equity, 2),
            "trades_count": self.state.trades_count
        }
        
        await self.hub.publish(RBotEvent(
            event_type=EventType.STATE_CHANGE,
            source="PORTFOLIO",
            payload=payload
        ))
