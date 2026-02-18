"""
Centralized configuration: constants and env-driven settings.

Env vars override defaults (MA_PERIOD, SYMBOL, EXIT_CHECK_*, DB_*).
See README for full list.
"""
import os
from zoneinfo import ZoneInfo

# --- IB connection ---
IB_HOST = os.getenv("IB_HOST", "127.0.0.1")
IB_PORT = int(os.getenv("IB_PORT", "4001"))  # 4000=paper, 4001=live, 4002=live alt
IB_CLIENT_ID = 2

# --- EOD exit check (NYC time) ---
# Wake at this time to run MA exit check (after 4pm ET market close)
EXIT_CHECK_HOUR = int(os.getenv("EXIT_CHECK_HOUR", "16"))
EXIT_CHECK_MINUTE = int(os.getenv("EXIT_CHECK_MINUTE", "2"))

# --- Timezone ---
NYC_TZ = ZoneInfo("America/New_York")

# --- Symbol & strategy ---
SYMBOL = os.getenv("SYMBOL", "SPY")
STRATEGY_TAG = os.getenv("STRATEGY_TAG") or None

# Moving average period. Exit when close < MA.
MA_PERIOD = int(os.getenv("MA_PERIOD", "40"))

# --- Timeouts ---
TIMEOUT = 2.0

# --- Database ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "trading")
DB_USER = os.getenv("DB_USER", "botuser")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
