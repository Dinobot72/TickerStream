# TickerStream AI — Backend

FastAPI service that powers authentication, portfolio/watchlist management, manual trading, market data, and the autonomous trading bot.

## Stack

- FastAPI + Uvicorn
- SQLite (raw `sqlite3`, no ORM)
- JWT auth stored in an `httponly` cookie (`PyJWT`, `passlib`/bcrypt for password hashing)
- `yfinance` for quotes, history, screeners, and fundamentals
- `sb3-contrib` `RecurrentPPO` + PyTorch for the trading bot's decision model

## Setup

```bash
cd backend
pip install -r requirements.txt
pip install -r ../model/requirements.txt   # needed for the AI scorer (torch, sb3-contrib, gymnasium)
uvicorn app.main:app --reload
```

The API serves on `http://localhost:8000`. The Angular dev server proxies `/api/*` to this port (see `frontend/proxy.conf.json`).

## Environment variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `SECRET_KEY` | JWT signing secret. **Required in production** — a random key is generated (and a warning logged) if unset, which invalidates all tokens on restart. | random, ephemeral |
| `ALLOWED_ORIGINS` | JSON array of CORS origins. | hardcoded list in `app/core/config.py` |
| `ENV` | Set to `production` to enable secure/cross-site cookies (`Secure`, `SameSite=None`, cookie domain `.ticker-stream.com`). | `development` |

Create a `.env` file in `backend/` (loaded via `python-dotenv`) or set these in your shell/container.

## Project structure

```
backend/app/
├── core/         # config (CORS, secrets, bot state), SQLite connection + schema setup
├── routers/      # auth, portfolio, trading — FastAPI route handlers
├── services/     # market data, risk management, screener, AI scoring, portfolio orchestration
├── tasks/        # background asyncio loop that runs the bot during market hours
└── main.py       # app factory, middleware, router registration, startup hook
```

## Database

SQLite database at `backend/tickerstream.db`, created on startup by `setup_database()`. Tables:

- **users** — username, bcrypt password hash, name.
- **portfolios** — one row per user, cash `balance`.
- **holdings** — per-user, per-ticker `quantity` and average `purchase_price`.
- **trades** — full trade history, including an `is_bot_trade` flag.
- **watchlist** — user-curated tickers shown on the Watchlist page.
- **bot_watchlist** — tickers the *bot* considers, populated by the screener (separate from the user's personal watchlist).

## Authentication

Login issues a JWT (`PyJWT`, HS256) containing `sub` (username) and `id` (user id), set as an `httponly` cookie (`access_token`). `CookieBearer` (in `auth.py`) accepts either the cookie or a standard `Authorization: Bearer` header, so the API can be exercised directly as well as from the browser. All portfolio/trading routes depend on `get_current_user` and enforce that the authenticated user matches the `user_id` in the path.

## Risk management

`services/risk_manager.py` gates every trade (manual or bot-originated) before it's recorded:

- Rejects buys that exceed available cash, or more than 20% of buying power (`MAX_POSITION_PCT`) in a single position.
- Halts all trading if the portfolio has lost more than 2% since the prior day's close (`DAILY_LOSS_LIMIT_PCT`).
- Enforces a simplified pattern-day-trader (PDT) rule below the $25k SEC threshold: blocks new buys after 3 day-trades in a rolling 5-day window, and blocks selling a same-day buy once that limit is hit.

## The trading bot pipeline

1. **`services/screener.py`** — runs a `yfinance` equity screen (price $2–$100, volume > 500k, up >3% on the day) and refreshes `bot_watchlist`.
2. **`services/data_prep_live.py`** — builds a 707-feature observation (5 candidate tickers × 20-day lookback × 7 technical-indicator features, plus 7 portfolio features) matching the shape the model was trained on in `model/newAI/advanced_training_env.py`.
3. **`services/ai_scorer.py`** — loads the trained `RecurrentPPO` model and turns an observation into a BUY/SELL/HOLD signal per ticker, maintaining per-ticker LSTM hidden state.
4. **`services/portfolio_manager.py`** — orchestrates scoring across the watchlist + current holdings and turns signals into a concrete trade plan (respecting `max_positions`, confidence thresholds, and position sizing).
5. **`tasks/scheduler.py`** — an `asyncio` background loop, started on app startup, that runs only while the bot is toggled on (`/api/bot/start`) and the US market is open, refreshes the screener hourly, and executes the generated trade plan every 5 minutes via the same `process_trade()` used by manual trades.

## Known issues / cleanup candidates

- `routers/trading.py` imports `ai_bridge` but the import is commented out — direct model invocation from the trading router isn't currently wired up.
- `services/ai_scorer.py`'s `score_stock` references an undefined `ticker` variable (should be `state_key`) when initializing per-ticker LSTM state — this will raise a `NameError` the first time a new ticker is scored.
- `services/portfolio_manager.py`'s `generate_trade_plan()` and `get_portfolio_summary()` still call `self.scorer.score_stock(ticker, balance, holdings[ticker])`, which doesn't match the current `score_stock(candidates, held_ticker, balance, shares, ...)` signature used elsewhere in the same file.
- `services/services.py` duplicates `services/market_data.py` (an older, less defensive version) and doesn't appear to be imported anywhere — safe to delete after confirming.
- `docker-compose.yml` has a live Cloudflare tunnel token and a placeholder `SECRET_KEY` committed directly — rotate both and inject via a secrets manager or a `.env` file excluded from version control.

## API summary

| Area | Endpoints |
| --- | --- |
| Auth | `POST /api/register`, `POST /api/login`, `POST /api/logout`, `GET /api/auth/status`, `POST /api/user/{id}/change-password` |
| Portfolio | `GET /api/user/{id}`, `POST /api/user/{id}/deposit`, `GET /api/holdings/{id}`, `GET /api/activity/{id}`, `GET/POST /api/watchlist/{id}`, `DELETE /api/watchlist/{id}/{ticker}` |
| Trading & market data | `POST /api/trade/`, `GET /api/stock/{ticker}`, `GET /api/stock/{ticker}/history`, `GET /api/market/gainers`, `GET /api/market/losers`, `GET /api/metrics/{ticker}`, `GET /api/change/{ticker}` |
| Bot controls | `GET /api/bot/status`, `POST /api/bot/start`, `POST /api/bot/stop` |