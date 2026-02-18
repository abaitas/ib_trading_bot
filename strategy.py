"""
Trading strategies: MA exit, scheduling.

Runs an end-of-day loop: wake at EXIT_CHECK_* (after close), if SYMBOL close < MA,
exit the position via market order (outside RTH). Skips non-trading days (holidays).
"""
import asyncio
import logging
from datetime import datetime, timedelta
from ib_async import IB

import shutdown

from config import (
    EXIT_CHECK_HOUR,
    EXIT_CHECK_MINUTE,
    IB_CLIENT_ID,
    IB_HOST,
    IB_PORT,
    MA_PERIOD,
    NYC_TZ,
    SYMBOL,
)
from broker import (
    get_positions,
    get_stock_position,
    get_symbol_close_and_ma,
    execute_order,
    is_trading_day,
    stock_contract,
)

logger = logging.getLogger("daily_logger")


async def sleep_until(target_hour: int, target_minute: int) -> None:
    """Sleep until target_hour:target_minute in NYC timezone (or tomorrow if passed)."""
    now = datetime.now(tz=NYC_TZ)
    target_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if now >= target_time:
        target_time = target_time + timedelta(days=1)
    sleep_seconds = (target_time - now).total_seconds()
    logger.info("Sleeping %.1f min until %s", sleep_seconds / 60, target_time.strftime("%H:%M %Z"))
    # Check shutdown flag every minute to exit promptly on SIGTERM/SIGINT
    chunk = 60.0
    while sleep_seconds > 0 and not shutdown.requested:
        await asyncio.sleep(min(chunk, sleep_seconds))
        sleep_seconds -= chunk


async def buy_test(ib: IB, size: int = 100) -> None:
    """One-off BUY for testing. Connects, qualifies, places order, disconnects."""
    contract = stock_contract()
    await execute_order(
        ib=ib,
        contract=contract,
        action="BUY",
        size=size,
        outsideRth=True,
    )


async def exit_if_below_ma(ib: IB) -> None:
    """Exit stock position for SYMBOL if close < MA."""
    pos = await get_stock_position(ib)
    if not pos:
        logger.info("No %s position to evaluate", SYMBOL)
        return

    close_px, ma = await get_symbol_close_and_ma(ib)
    if close_px is None:
        return

    if close_px < ma:
        logger.info("%s below MA%d | exiting position", SYMBOL, MA_PERIOD)
        contract = stock_contract()
        await execute_order(
            ib=ib,
            contract=contract,
            action="SELL",
            size=abs(pos.position),
            outsideRth=True,
        )
    else:
        logger.info("%s above MA%d | holding", SYMBOL, MA_PERIOD)


async def run_bot() -> None:
    """Connect to IB and run MA exit strategy loop."""
    ib = IB()
    try:
        await ib.connectAsync(IB_HOST, IB_PORT, clientId=IB_CLIENT_ID, timeout=30)
        await asyncio.sleep(1)
        logger.info("Connected to IB | %s:%s", IB_HOST, IB_PORT)

        while not shutdown.requested:
            try:
                # await sleep_until(EXIT_CHECK_HOUR, EXIT_CHECK_MINUTE)
                if shutdown.requested:
                    break

                positions = await get_positions(ib)

                # if positions:
                #     # Only run MA exit on trading days (skip weekends/holidays)
                #     symbol_contract = stock_contract()
                #     await ib.qualifyContractsAsync(symbol_contract)
                #     if await is_trading_day(ib, symbol_contract):
                #         await exit_if_below_ma(ib)
                #     else:
                #         logger.info("Not a trading day | skipping exit check")
                logger.info("Heartbeat")
                await asyncio.sleep(60*60)

            except Exception as e:
                logger.exception("Error in run loop: %s", e)
                await asyncio.sleep(5)

    except Exception as conn_error:
        logger.exception("IB connection failed: %s", conn_error)
    finally:
        if ib.isConnected():
            ib.disconnect()
            logger.info("Disconnected from IB")
