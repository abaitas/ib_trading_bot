"""
Startup config validation. Call before running the bot.
"""
import sys


def validate_config() -> None:
    """Raise SystemExit with message if config is invalid."""
    from config import DB_PASSWORD, IB_HOST, IB_PORT, MA_PERIOD, SYMBOL

    errors = []
    if not SYMBOL or not str(SYMBOL).strip():
        errors.append("SYMBOL must be non-empty")
    if MA_PERIOD < 1:
        errors.append("MA_PERIOD must be >= 1")
    if MA_PERIOD > 200:
        errors.append("MA_PERIOD should typically be <= 200")
    if not DB_PASSWORD:
        errors.append("DB_PASSWORD must be set (do not use default)")
    if not IB_HOST or not str(IB_HOST).strip():
        errors.append("IB_HOST must be non-empty")
    if IB_PORT < 1 or IB_PORT > 65535:
        errors.append("IB_PORT must be between 1 and 65535")

    if errors:
        print("Config validation failed:", "; ".join(errors), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    validate_config()
