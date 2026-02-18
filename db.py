"""
Database: PostgreSQL connection pool and position persistence.

Uses SimpleConnectionPool with lazy init; retries on connect failure (e.g. DB not ready).
get_conn() yields pooled connections; insert_position() writes position snapshots.
"""
import logging
import time

import shutdown
from contextlib import contextmanager
from typing import Any, Generator

import psycopg2
from psycopg2 import pool

from config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER

logger = logging.getLogger(__name__)

_connection_pool: pool.SimpleConnectionPool | None = None


def _get_pool() -> pool.SimpleConnectionPool:
    """Lazy-init connection pool."""
    global _connection_pool
    if _connection_pool is None:
        while not shutdown.requested:
            try:
                _connection_pool = pool.SimpleConnectionPool(
                    minconn=1,
                    maxconn=5,
                    host=DB_HOST,
                    port=DB_PORT,
                    database=DB_NAME,
                    user=DB_USER,
                    password=DB_PASSWORD,
                )
                logger.info("Database pool initialized | %s", DB_HOST)
                break
            except psycopg2.OperationalError as e:
                logger.warning("Database not ready, retrying in 2s: %s", e)
                time.sleep(2)
        if _connection_pool is None:
            raise RuntimeError("Database pool init aborted (shutdown requested)")
    return _connection_pool


@contextmanager
def get_conn() -> Generator[Any, None, None]:
    """Context manager yielding a pooled connection. Returns conn to pool on exit."""
    conn = _get_pool().getconn()
    returned = False
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        yield conn
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
        logger.warning("Connection unhealthy, releasing: %s", e)
        try:
            conn.close()
        except (psycopg2.OperationalError, psycopg2.InterfaceError, AttributeError):
            pass
        # putconn(..., close=True) removes from pool so we don't double-put in finally
        _get_pool().putconn(conn, close=True)
        returned = True
        raise
    finally:
        if not returned:
            try:
                _get_pool().putconn(conn)
            except Exception as e:
                logger.warning("Failed to return connection to pool: %s", e)


def insert_position(pos: Any) -> None:
    """Insert a position snapshot. Handles None values and connection issues."""
    try:
        with get_conn() as conn:
            contract = pos.contract
            expiry = getattr(contract, "lastTradeDateOrContractMonth", None) or ""
            multiplier = contract.multiplier
            if multiplier is not None and not isinstance(multiplier, str):
                multiplier = str(multiplier)

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO positions (
                        account, con_id, symbol, instrument, sec_type,
                        expiry, strike, multiplier, currency, exchange,
                        size, avg_cost, market_price, market_value,
                        unrealized_pnl, realized_pnl, recorded_at
                    )
                    VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW()
                    )
                    """,
                    (
                        pos.account,
                        contract.conId,
                        contract.symbol or "",
                        contract.localSymbol or "",
                        contract.secType or "",
                        expiry,
                        contract.strike if contract.strike is not None else None,
                        multiplier,
                        contract.currency or "",
                        contract.exchange or "",
                        pos.position,
                        pos.averageCost,
                        pos.marketPrice,
                        pos.marketValue,
                        pos.unrealizedPNL,
                        pos.realizedPNL,
                    ),
                )
        logger.debug(
            "Inserted position: %s %s size=%s",
            contract.symbol, contract.localSymbol, pos.position,
        )
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
        logger.exception(
            "Insert position failed | %s: %s",
            getattr(pos.contract, "localSymbol", "?"), e,
        )
