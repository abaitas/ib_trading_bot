# IB Trading Bot

MA exit strategy for equity positions on Interactive Brokers. Connects to IB, checks after market close whether the close price is below the N-day moving average, and exits the position if so. MA period is configurable (default 40).

**Tested to run on EC2.** Deploy via GitHub Actions requires [GitHub repo secrets](https://docs.github.com/en/actions/security-guides/encrypted-secrets): `EC2_SSH_KEY` (PEM contents), `EC2_HOST` (EC2 IP or hostname). Without these, push-to-main runs tests but deploy skips. Runtime secrets (DB, IB, VNC) live on the EC2 instance.

> **Risk disclaimer:** This bot executes real trades with real money. Use at your own risk. Past performance does not guarantee future results. Always test in paper trading first.

## Architecture

```
main.py          → validate_config, signal handlers, argparse (--test-buy)
     ↓
strategy.py      → EOD loop, sleep_until (timezone-aware), exit_if_below_ma
     ↓
broker.py        → IB API: positions, historical bars, MA computation, order execution
     ↓
db.py            → PostgreSQL connection pool, position snapshots
config.py        → Env-driven config (12-factor style)
```

**Design choices:**

| Layer | Implementation |
|-------|----------------|
| **Async I/O** | `asyncio` + `ib_async` — non-blocking IB API calls, efficient event loop |
| **Strategy logic** | Pure functions for MA computation (`_compute_ma_from_bars`); broker handles I/O |
| **DB access** | `SimpleConnectionPool` with lazy init, context manager `get_conn()`, retries on startup |
| **Graceful shutdown** | Global `shutdown.requested` flag; `sleep_until` checks every 60s; infinite retries (`is_market_open`, `_get_pool`) respect shutdown |
| **Market hours** | IB `tradingHours` string parsing — handles `CLOSED`, same-day/next-day session formats |
| **Order flow** | Cancel stale orders → market order → wait for fill → confirm portfolio; outside RTH for EOD |
| **Config** | Env vars only; startup validation rejects bad `MA_PERIOD`, missing `DB_PASSWORD` |

**Stack:** Python 3.10+, ib_async, PostgreSQL, Docker, GitHub Actions (test + deploy).

**Code quality & readability:**

| Principle | How it's applied |
|-----------|------------------|
| **Separation of concerns** | Strategy logic (`_compute_ma_from_bars`) is pure and testable; broker handles I/O; config is centralized |
| **Type hints** | Functions annotated with `Optional`, `tuple`, `Generator`; improves IDE support and maintainability |
| **Docstrings** | Module- and function-level docs; complex logic (trading hours parsing, order flow) commented inline |
| **Narrow exception handling** | `ConnectionError`, `TimeoutError`, `OSError` caught explicitly; unexpected errors re-raised |
| **Consistent logging** | Structured `key=value` style; lazy `%s` formatting (no f-strings in log calls) |
| **Unit tests** | 13 tests for MA computation, trading-day logic, session parsing — no mocks of external services |

The codebase is small enough to review in ~30 minutes. Start with `strategy.py` for the control flow, then `broker.py` for the IB integration. Solo-authored; end-to-end from strategy logic to Docker deployment.

## Setup

1. **Secrets** — `DB_PASSWORD` (required), VNC password for headless IB Gateway (EC2), IB credentials. No secrets are bundled; you must configure them.
2. **Python 3.10+**
3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
4. **PostgreSQL** (for position logging)
5. **IB Gateway or TWS** running and configured for API access

## Running

**Full bot** (EOD MA exit loop):
```bash
DB_PASSWORD=yourpassword python main.py
```
Or export `DB_PASSWORD` first: `export DB_PASSWORD=yourpassword`

**Test buy** (one-off buy, then exit):
```bash
DB_PASSWORD=yourpassword python main.py --test-buy 100
```
Buys 100 shares of `SYMBOL` (default SPY) and exits. Useful for paper-trading tests.

## Environment Variables

| Variable   | Default    | Description                    |
|-----------|------------|--------------------------------|
| `IB_HOST` | 127.0.0.1  | IB Gateway/TWS host            |
| `IB_PORT` | 4001       | IB port (4000=paper, 4001=live, 4002=live alt) |
| `SYMBOL`  | SPY        | Equity ticker (SPY, TSLA, NVDA, etc.) |
| `MA_PERIOD` | 40       | Moving average period. Exit when close < MA. |
| `EXIT_CHECK_HOUR` | 9   | Hour (ET) to run EOD exit check |
| `EXIT_CHECK_MINUTE` | 29 | Minute (ET) to run EOD exit check |
| `STRATEGY_TAG` | *(none)* | Order reference tag in IB (for filtering/debugging) |
| `DB_HOST` | localhost  | PostgreSQL host                |
| `DB_NAME` | trading    | Database name                  |
| `DB_USER` | botuser    | Database user                  |
| `DB_PASSWORD` | *(required)* | Database password (must be set) |

## Docker

```bash
cp .env.example .env   # Edit .env and set DB_PASSWORD
docker compose up -d
```

Requires IB Gateway/TWS on the host; the bot connects via `host.docker.internal`.

**Docker env vars** — Override via `environment:` in compose or `.env`:
- `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` — PostgreSQL connection (defaults match `docker-compose.yml`)
- `SYMBOL`, `MA_PERIOD`, `EXIT_CHECK_*`, `STRATEGY_TAG` — Strategy config

**Shared EC2 instance** — Deploys to `/home/ubuntu/ib_trading_bot` (does not touch `trading-system`). Uses Postgres on host port 5433 to avoid conflict with prod on 5432. Deploy overwrites CloudWatch config; merge if you need both.

To enable deploy on push-to-main, add GitHub repo secrets: `EC2_SSH_KEY` (full PEM file contents), `EC2_HOST` (e.g. `ec2-xx-xx-xx-xx.compute.amazonaws.com`). No secrets bundled—you supply them.

## Running on EC2 (IB Gateway + bot)

The bot needs IB Gateway running and logged in before it can connect. On a headless EC2 instance, use the `start_ib.sh` script:

1. **Prerequisites** (one-time on EC2):
   ```bash
   sudo apt install -y xvfb fluxbox x11vnc openjdk-17-jdk
   x11vnc -storepasswd /home/ubuntu/.vnc/passwd   # set VNC password
   ```
   IB Gateway must be installed at `/home/ubuntu/IBGateway`. In IB Gateway: **Configure → API → Settings** → enable socket clients, port **4001**, add `127.0.0.1` to trusted IPs.

2. **Run** (after deploy):
   ```bash
   cd /home/ubuntu/ib_trading_bot
   ./scripts/start_ib.sh
   ```
   Or add alias: `echo 'alias ib="/home/ubuntu/ib_trading_bot/scripts/start_ib.sh"' >> ~/.bashrc && source ~/.bashrc`, then type `ib`.

3. **Flow**: Script starts Xvfb → fluxbox → x11vnc → IB Gateway. Connect via VNC:
   ```bash
   ssh -i YOUR_KEY.pem -L 5901:localhost:5901 ubuntu@YOUR_EC2_IP
   ```
   Then open VNC Viewer → `localhost:5901`, log into IB (MFA if required). Back in the SSH session, press **ENTER**. Script then starts the Docker bot.

4. **Logs**: `docker logs -f ib_trading_bot-bot`

## Tests

```bash
python -m unittest discover tests -v
```

## Development

`.idea/` (PyCharm) and `.vscode/` (VS Code) are in `.gitignore`, so IDE config stays local. If you use a different editor and want to ignore its config, add it to `.gitignore` (e.g. `*.sublime-*` or your editor’s project folder).
