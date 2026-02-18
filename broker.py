"""
IB broker: positions, orders, historical data, market hours.

Fetches daily bars for moving-average (MA) exit logic, checks trading hours,
places market orders outside RTH (extended hours), and persists position snapshots.
"""
from __future__ import annotations

import asyncio
import logging
import time as pytime
from datetime import date, datetime
from typing import Any, Optional

from ib_async import IB, BarDataList, Contract, MarketOrder, Stock, Trade, util

from config import MA_PERIOD, NYC_TZ, STRATEGY_TAG, SYMBOL, TIMEOUT
from db import insert_position

import broker_math
import shutdown

logger = logging.getLogger("daily_logger")


def stock_contract(
    exchange: str = "SMART",
    primary_exchange: str = "ARCA",
) -> Stock:
    """Build stock contract for SYMBOL with SMART routing for orders."""
    return Stock(
        symbol=SYMBOL,
        exchange=exchange,
        currency="USD",
        primaryExchange=primary_exchange,
    )


async def get_stock_position(ib: IB) -> Optional[Any]:
    """Return stock position for SYMBOL (shares), or None if no position exists."""
    for pos in ib.portfolio():
        contract = pos.contract
        if (
            contract.symbol.strip() == SYMBOL
            and contract.secType == "STK"
            and pos.position != 0
        ):
            logger.info("Position: %s | %s shares", SYMBOL, pos.position)
            return pos
    logger.info("No open %s position", SYMBOL)
    return None


async def _fetch_symbol_daily_bars(ib: IB) -> Optional[BarDataList]:
    """Fetch last ~90 daily bars for SYMBOL from IB."""
    contract = stock_contract(exchange="ARCA")
    await ib.qualifyContractsAsync(contract)
    return await ib.reqHistoricalDataAsync(
        contract,
        endDateTime="",
        durationStr="3 M",
        barSizeSetting="1 day",
        whatToShow="TRADES",
        useRTH=True,
        formatDate=1,
    )


def _compute_ma_from_bars(
    bars: BarDataList, today_date: date, period: int
) -> tuple[float, float, date, list[float]]:
    """Convert bars to DataFrame and delegate to broker_math."""
    df = util.df(bars)
    return broker_math.compute_ma_from_bars(df, today_date, period)


def _log_symbol_ma(
    last_bar_date: date,
    today_date: date,
    last_close: float,
    ma: float,
    closes_for_ma: list[float],
    period: int,
) -> None:
    """Log MA computation results for SYMBOL."""
    today_included = last_bar_date == today_date
    logger.info(
        "[%s] last_bar_date=%s | today=%s | today_included=%s",
        SYMBOL, last_bar_date, today_date, today_included,
    )
    logger.debug(
        "[%s MA%d] last %d closes: %s",
        SYMBOL, period, period,
        ", ".join(f"{c:.2f}" for c in closes_for_ma),
    )
    logger.info(
        "[%s] close=%.2f | MA%d=%.2f | today_included=%s",
        SYMBOL, last_close, period, ma, today_included,
    )


def _compute_last_close_and_ma(bars: BarDataList, period: int) -> tuple[float, float]:
    """Compute last close and MA from daily bars. Caller must ensure len(bars) >= period."""
    today_date = datetime.now(NYC_TZ).date()
    last_close, ma, last_bar_date, closes_for_ma = _compute_ma_from_bars(
        bars, today_date, period
    )
    _log_symbol_ma(last_bar_date, today_date, last_close, ma, closes_for_ma, period)
    return last_close, ma


async def get_symbol_close_and_ma(
    ib: IB,
) -> tuple[Optional[float], Optional[float]]:
    """Fetch daily bars for SYMBOL and compute MA. Returns (last_close, ma)."""
    bars = await _fetch_symbol_daily_bars(ib)
    if not bars or len(bars) < MA_PERIOD:
        logger.warning("Insufficient historical bars for MA%d (need %d)", MA_PERIOD, MA_PERIOD)
        return None, None
    last_close, ma = _compute_last_close_and_ma(bars, MA_PERIOD)
    return last_close, ma


async def is_trading_day(ib: IB, contract: Contract) -> bool:
    """Check if today is a trading day. Returns False for weekends/holidays (CLOSED)."""
    now = datetime.now(NYC_TZ)
    try:
        details = await ib.reqContractDetailsAsync(contract)
        if not details or not details[0].tradingHours:
            return False
        return broker_math.is_trading_day_from_hours(details[0].tradingHours, now)
    except (ConnectionError, TimeoutError, OSError) as e:
        logger.warning("Trading day check failed: %s", e)
        return False


async def is_market_open(
    ib: IB, contract: Contract
) -> tuple[bool, Optional[datetime]]:
    """Check if market is open. Returns (is_open, market_close_time)."""
    now = datetime.now(NYC_TZ)
    while not shutdown.requested:
        try:
            details = await ib.reqContractDetailsAsync(contract)
            if not details or not details[0].tradingHours:
                return False, None
            return broker_math.parse_trading_sessions_for_today(details[0].tradingHours, now)
        except (ConnectionError, TimeoutError, OSError) as e:
            logger.warning("Trading hours fetch failed, retrying in 5s: %s", e)
            await asyncio.sleep(5)
        except Exception as e:
            logger.warning("Unexpected error fetching trading hours: %s", e)
            raise
    return False, None  # shutdown requested


def _log_trade_fills(trade: Trade, contract: Contract) -> None:
    """Log execution details for each fill in the trade."""
    recorded_exec_ids: set[str] = set()
    for t in trade.fills:
        exec_id = t.execution.execId
        if exec_id not in recorded_exec_ids:
            recorded_exec_ids.add(exec_id)
            ny_time = t.execution.time.astimezone(NYC_TZ)
            commission = t.commissionReport.commission if t.commissionReport else 0.0
            logger.info(
                "Fill: %s | side=%s | size=%s | price=%s | time=%s | commission=%s",
                contract.symbol, t.execution.side, t.execution.shares,
                t.execution.price, ny_time.strftime("%H:%M:%S"), commission,
            )


async def _wait_for_cancellations(
    ib: IB, contract: Contract, confirm_timeout: int
) -> None:
    """Wait for open orders for contract to be cancelled."""
    start = pytime.time()
    while pytime.time() - start < confirm_timeout:
        try:
            await asyncio.wait_for(ib.updateEvent, timeout=TIMEOUT)
        except asyncio.TimeoutError:
            pass
        still_open = [t for t in ib.openTrades() if t.contract.conId == contract.conId]
        if not still_open:
            logger.info("All orders cancelled | %s", contract.symbol)
            return
    logger.warning("Orders still open after timeout | %s", contract.symbol)


async def cancel_orders_for_contract(
    ib: IB, contract: Contract, confirm_timeout: int = 30
) -> None:
    """Cancel any open orders for the given contract."""
    open_trades = [t for t in ib.openTrades() if t.contract.conId == contract.conId]
    if not open_trades:
        logger.info("No open orders | %s", contract.symbol)
        return

    for trade in open_trades:
        ib.cancelOrder(trade.order)
        logger.info("Cancel requested | permId=%s | %s", trade.order.permId, contract.symbol)

    await _wait_for_cancellations(ib, contract, confirm_timeout)


async def _wait_for_order_fill(
    ib: IB,
    trade: Trade,
    order: MarketOrder,
    contract: Contract,
    timeout: int,
) -> bool:
    """Wait for order to fill. Returns True if filled, False if cancelled on timeout."""
    start_time = pytime.time()
    last_status = ""

    while True:
        try:
            await asyncio.wait_for(ib.updateEvent, timeout=TIMEOUT)
        except asyncio.TimeoutError:
            pass
        status = trade.orderStatus.status
        filled = trade.orderStatus.filled
        remaining = trade.orderStatus.remaining
        if status != last_status:
            logger.info(
                "Order %s | status=%s | filled=%s | remaining=%s",
                trade.order.permId, status, filled, remaining,
            )
            last_status = status

        if status == "Filled" and remaining == 0:
            logger.info("Order filled | permId=%s", trade.order.permId)
            _log_trade_fills(trade, contract)
            return True

        if pytime.time() - start_time > timeout:
            logger.warning("Order timeout, cancelling | permId=%s | waited=%ds", trade.order.permId, timeout)
            ib.cancelOrder(order)
            return False


async def _confirm_portfolio_position(
    ib: IB, contract: Contract, expected_pos: float, confirm_timeout: int
) -> None:
    """Wait for portfolio to reflect expected position."""
    confirm_start = pytime.time()
    while pytime.time() - confirm_start < confirm_timeout:
        try:
            await asyncio.wait_for(ib.updateEvent, timeout=1.0)
        except asyncio.TimeoutError:
            pass
        pos = next((p for p in ib.portfolio() if p.contract.conId == contract.conId), None)
        current_pos = pos.position if pos else 0
        if current_pos == expected_pos:
            logger.info("Portfolio confirmed | %s | position=%s", contract.symbol, expected_pos)
            return
    logger.warning(
        "Portfolio confirmation timeout | %s | expected=%s | timeout=%ds",
        contract.symbol, expected_pos, confirm_timeout,
    )


def _resolve_order_params(
    ib: IB,
    contract: Contract,
    action: Optional[str],
    size: Optional[float],
) -> Optional[tuple[str, int, float]]:
    """Resolve action, size, expected_pos. Returns None if early exit (no position to close)."""
    pos = next((p for p in ib.portfolio() if p.contract.conId == contract.conId), None)
    current_pos = pos.position if pos else 0

    if size is None:
        if current_pos == 0:
            logger.info("No position to close | %s", contract.symbol)
            return None
        action = "BUY" if pos.position < 0 else "SELL"
        size = abs(current_pos)

    # BUY adds to position, SELL reduces it
    expected_pos = current_pos + size if action.upper() == "BUY" else current_pos - size
    size_int = int(size)
    logger.info("Placing order | %s %s %s | expected_position=%s", action, size_int, contract.symbol, expected_pos)
    return action, size_int, expected_pos


async def execute_order(
    ib: IB,
    contract: Contract,
    action: Optional[str] = None,
    size: Optional[float] = None,
    timeout: int = 60,
    confirm_timeout: int = 10,
    outsideRth: bool = True,
) -> None:
    """Place market order with fill wait and portfolio confirmation."""
    await ib.qualifyContractsAsync(contract)
    if contract.secType == "STK" and contract.exchange != "SMART":
        raise ValueError(
            f"Invalid stock routing: exchange={contract.exchange}. "
            "Stocks must use exchange='SMART' (primaryExchange may be ARCA)."
        )

    resolved = _resolve_order_params(ib, contract, action, size)
    if resolved is None:
        return
    action, size, expected_pos = resolved

    # Cancel stale orders before placing new one
    await cancel_orders_for_contract(ib, contract)

    order = MarketOrder(action, size)
    order.outsideRth = outsideRth
    order.orderRef = STRATEGY_TAG
    trade = ib.placeOrder(contract, order)
    logger.info("Order submitted | %s %s %s | MKT | tag=%s", action, size, contract.symbol, STRATEGY_TAG)

    if not await _wait_for_order_fill(ib, trade, order, contract, timeout):
        return

    await _confirm_portfolio_position(ib, contract, expected_pos, confirm_timeout)


async def get_positions(ib: IB) -> list[Any]:
    """Return open positions for SYMBOL, persisting to DB."""
    positions = []
    # portfolio() includes zero-size; we filter and write non-zero to positions table
    for pos in ib.portfolio():
        if pos.position == 0:
            continue
        if pos.contract.symbol != SYMBOL:
            continue
        insert_position(pos)
        positions.append(pos)
    return positions
