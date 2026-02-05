import logging
import asyncio
from typing import Dict, Optional
from dataclasses import dataclass, field

from app.modules.hub import EventHub, EventType, RBotEvent

logger = logging.getLogger("PortfolioMgr")

@dataclass
class PortfolioState:
    cash: float = 100_000.0  # Стартовый капитал в рублях
    positions: Dict[str, int] = field(default_factory=dict)  # ticker -> quantity
    # История сделок (упрощенно)
    trades_count: int = 0
    total_commission_paid: float = 0.0

class PortfolioManagerWorker:
    """
    Управляет состоянием счета пользователя.
    Исполняет ордера, считает комиссию, обновляет оценку портфеля.
    """
    def __init__(self, hub: EventHub):
        self.hub = hub
        # Пока храним состояние в памяти (для одного юзера). В будущем -> БД.
        self.state = PortfolioState()
        # Храним последние известные цены для оценки портфеля
        self.last_prices: Dict[str, float] = {}
        self._is_running = False

    async def start(self):
        self._is_running = True
        # Слушаем рынок (чтобы знать цены)
        self.hub.subscribe(EventType.SIGNAL_UPDATE, self._on_market_update)
        # Слушаем приказы пользователя
        self.hub.subscribe(EventType.USER_ACTION, self._on_user_action)
        logger.info("Portfolio Manager started. Initial cash: 100,000 RUB")

    async def stop(self):
        self._is_running = False
        logger.info("Portfolio Manager stopped.")

    async def _on_market_update(self, event: RBotEvent):
        """Обновляем кэш цен для оценки портфеля"""
        if not self._is_running: return
        
        payload = event.payload
        ticker = payload.get("ticker")
        price = payload.get("price")
        
        if ticker and price:
            self.last_prices[ticker] = float(price)

    async def _on_user_action(self, event: RBotEvent):
        """Обработка торгового приказа"""
        if not self._is_running: return

        payload = event.payload
        action_type = payload.get("action") # BUY / SELL
        ticker = payload.get("ticker")
        quantity = payload.get("quantity", 1) # лоты

        if not (action_type and ticker):
            return

        # Получаем текущую цену (считаем, что исполняем "по рынку")
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
        commission = total_cost * 0.003  # 0.3% комиссия брокера
        total_spend = total_cost + commission

        if self.state.cash >= total_spend:
            # Исполняем
            self.state.cash -= total_spend
            self.state.positions[ticker] = self.state.positions.get(ticker, 0) + quantity
            self.state.trades_count += 1
            self.state.total_commission_paid += commission
            
            logger.info(f"✅ BUY EXEC: {ticker} x {quantity} @ {price}. Comm: {commission:.2f}")
            await self._publish_state_change("ORDER_FILLED", f"Куплено {quantity} {ticker} по {price}")
        else:
            await self._reject_order(ticker, "Недостаточно средств")

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
        """Уведомляем всех об изменении баланса"""
        # Считаем полную стоимость портфеля
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
