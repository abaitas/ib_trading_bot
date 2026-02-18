"""
IB Trading Bot — Entry point.

Validates config, sets up logging and signal handlers (SIGTERM/SIGINT),
then runs the MA exit strategy loop until shutdown.
"""
import argparse
import asyncio
import signal

from logging_config import setup_daily_logger
import shutdown
from strategy import buy_test, run_bot
from validate_config import validate_config


def _on_signal(signum, frame):
    """Set shutdown flag so run_bot exits gracefully from its sleep loop."""
    shutdown.requested = True


async def _run_buy_test(size: int):
    from ib_async import IB
    from config import IB_HOST, IB_PORT, IB_CLIENT_ID
    ib = IB()
    try:
        await ib.connectAsync(IB_HOST, IB_PORT, clientId=IB_CLIENT_ID, timeout=30)
        await buy_test(ib, size=size)
    finally:
        if ib.isConnected():
            ib.disconnect()


def main():
    parser = argparse.ArgumentParser(description="IB MA exit bot")
    parser.add_argument(
        "--test-buy",
        type=int,
        metavar="N",
        help="One-off buy N shares of SYMBOL for testing (then exit)",
    )
    args = parser.parse_args()
    validate_config()
    setup_daily_logger()
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    if args.test_buy is not None:
        asyncio.run(_run_buy_test(args.test_buy))
    else:
        asyncio.run(run_bot())


if __name__ == "__main__":
    main()
