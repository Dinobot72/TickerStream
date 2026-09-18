# Broker Integration Design (Alpaca)

Status: implemented
Scope: paper trading now, live trading behind gates

---

## 1. Why this shape

TickerStream currently simulates every trade. `process_trade()` in
`app/routers/trading.py` writes directly to the local `trades`, `portfolios` and
`holdings` tables, and both callers — the manual `/api/trade/` endpoint and the
bot loop in `app/tasks/scheduler.py` — go through it.

That single choke point is the whole reason this integration is small. There is
exactly one function where execution happens, so routing to a real broker means
adding a branch there rather than threading a broker object through the
scheduler, the portfolio manager and the risk manager.

The design goal was: **a user who never links a brokerage should see no change
at all**, and a user who does link one should have their existing portfolio UI,
trade history and bot keep working unmodified.

---

## 2. Architecture

```
  /api/trade/  (manual)          scheduler.py  (bot)
         \                            /
          \                          /
           +----> process_trade() <-+
                        |
            has enabled broker link?
                   /          \
                 no            yes
                 |              |
        _process_simulated  _process_broker_trade
        _trade()                |
           |                    v
     local ledger          services/broker.py
     (unchanged)           AlpacaBroker.submit_order()
                                |
                                v
                          Alpaca REST API
                                |
                                v
                  record trade row (real fill price)
                                |
                                v
                  sync_portfolio_from_broker()
                  (Alpaca overwrites local cache)
```

### New modules

| File | Responsibility |
|---|---|
| `app/core/crypto.py` | Fernet encryption of API credentials at rest |
| `app/services/broker.py` | All Alpaca interaction; credential CRUD; state sync; order reconciliation |
| `app/routers/broker.py` | HTTP surface for linking, status, sync |

### Modified

| File | Change |
|---|---|
| `app/routers/trading.py` | `process_trade()` split into a router plus two execution paths; oversell bug fixed |
| `app/core/database.py` | `broker_accounts` table; five new columns on `trades` |
| `app/core/config.py` | Live-trading gates, fill-poll tuning |
| `app/tasks/scheduler.py` | Reconcile + sync per user before generating a trade plan |
| `app/main.py` | Mount the broker router |
| `requirements.txt`, `.env.example`, `docker-compose.yml` | Dependency and config plumbing |

---

## 3. Multi-user model

Per-user accounts, as requested. `broker_accounts` is keyed by `user_id`, one
linked brokerage each:

```sql
CREATE TABLE broker_accounts (
    user_id              INTEGER PRIMARY KEY,
    provider             TEXT NOT NULL DEFAULT 'alpaca',
    api_key_encrypted    TEXT NOT NULL,
    secret_key_encrypted TEXT NOT NULL,
    mode                 TEXT NOT NULL DEFAULT 'paper'
                         CHECK (mode IN ('paper', 'live')),
    is_enabled           BOOLEAN NOT NULL DEFAULT TRUE,
    broker_account_id    TEXT,
    linked_at            DATETIME DEFAULT CURRENT_TIMESTAMP,
    live_confirmed_at    DATETIME,
    last_sync_at         DATETIME,
    FOREIGN KEY (user_id) REFERENCES users (user_id)
);
```

Each user brings their own Alpaca keys. Nothing is shared, and there is no
server-level house account. In practice today that means one row — yours — but
the code path is identical for the hundredth user, so opening it up later is a
UI task, not a re-architecture.

Every broker endpoint derives `user_id` from the auth token. No route accepts a
`user_id` in its body. (The pre-existing `/api/trade/` does accept one and checks
it against the token; that pattern was deliberately not repeated.)

---

## 4. Credential security

API keys are bearer credentials — whoever holds the pair can move real money.
The SQLite file is a single unencrypted file on a Docker volume, so plaintext
storage was never an option.

- Encrypted with Fernet (`cryptography`, already a dependency) under
  `BROKER_ENCRYPTION_KEY`.
- **Fail closed.** No key configured means credential storage raises rather than
  falling back to plaintext or to an ephemeral generated key. An app that
  silently degrades to plaintext key storage is worse than one that refuses to
  store keys.
- Deliberately separate from `SECRET_KEY`. Rotating JWT signing is harmless;
  rotating this orphans every linked account. Coupling them would make one
  rotation destroy the other.
- Write-only from the client's perspective. No endpoint returns a key, masked or
  otherwise.
- Verified before storage: credentials are probed against Alpaca at link time, so
  a typo fails at the link screen instead of at the first trade.
- Decrypted only in memory, at call time.

**Operational warning:** `BROKER_ENCRYPTION_KEY` must be stable across deploys.
Losing it does not lose money, but every user has to re-link.

---

## 5. Live trading gates

Three independent switches, all defaulting to off. All three must be on before a
bot-initiated real-money order can happen.

| Gate | Where | Default | Blocks |
|---|---|---|---|
| `ALLOW_LIVE_TRADING` | env, server-wide | `false` | all live orders |
| `mode='live'` + `live_confirmed_at` | per user, DB | paper / NULL | that user's live orders |
| `ALLOW_LIVE_BOT_TRADING` | env, server-wide | `false` | **bot** live orders only |

Notes on each:

**Promotion to live requires a fresh key pair**, not a flag flip. Alpaca issues
different credentials for paper and live, so a "switch to live" reusing paper
keys would fail at the first order anyway. Demanding the live keys makes the
consequence explicit at the moment of the decision rather than the moment of the
trade. Re-linking also clears any prior live confirmation.

**The bot gate is separate from the human gate** on purpose. With
`ALLOW_LIVE_BOT_TRADING=false`, you can place live trades by hand while the RL
bot stays confined to paper. Given the model's current near-uniform action
distribution, that is where it should stay until the policy is validated.

---

## 6. Execution semantics

### Orders are asynchronous

The original code assumed instant fills. Real orders are not instant: a market
order submitted outside regular hours sits as `accepted` until the open, and any
order can be partially filled or rejected.

`trades` gained five columns to model this:

| Column | Purpose |
|---|---|
| `broker_order_id` | Alpaca's order id, for reconciliation |
| `status` | `PENDING` / `PARTIAL` / `FILLED` / `CANCELED` / `REJECTED` |
| `mode` | `simulated` / `paper` / `live` |
| `filled_qty` | Shares actually filled |
| `filled_avg_price` | Real execution price |

Existing rows backfill as `FILLED` / `simulated`, which is what they were.

Alpaca's ~18 order states are collapsed to those five. The app only needs to know
whether an order is working, done, or dead.

### Fill handling

`submit_order()` polls briefly (default 8s) for a terminal state. If the order is
still working, the trade is recorded `PENDING` and `reconcile_open_orders()`
finishes the job on a later scheduler tick.

A `PENDING` row keeps the decision-time quote as a placeholder price, so the
column is never NULL. It is only overwritten with `filled_avg_price` once
`filled_qty > 0` — a working order has no meaningful execution price, and
recording one would show a fill that has not happened.

### Idempotency

Every order carries a generated `client_order_id`. If the process dies between
submitting and recording the trade, the retry is rejected by Alpaca as a
duplicate rather than silently doubling the position.

---

## 7. Alpaca as source of truth

Once linked, local `portfolios` and `holdings` become a **cache** of Alpaca's
account state, refreshed by `sync_portfolio_from_broker()`.

Two decisions worth stating explicitly:

**Balance syncs from `cash`, not `portfolio_value` or `equity`.**
`portfolios.balance` is what BUYs spend against. Using portfolio value would
double-count open positions and let the bot "spend" money already tied up in
stock.

**Holdings are replaced wholesale, not diffed.** A position closed outside the
app — manually on Alpaca's site, or by a stop — must disappear locally. A diff
that only updates rows it recognises would leave that position in the local table
forever.

The scheduler reconciles and syncs **before** generating each user's trade plan.
The model's observation is built from `portfolios.balance` and `holdings`; if
those are stale it decides against numbers that are not true, and position sizing
drifts from real buying power. A broker outage for one user is caught and logged
so it cannot stop the loop for everyone else.

---

## 8. Failure handling

The governing principle: **never silently simulate a trade the user believes is
real.**

| Situation | Behaviour |
|---|---|
| No linked account | Simulated path (unchanged behaviour) |
| Link exists but paused (`is_enabled=0`) | Simulated path |
| Link exists but unusable (live gate closed, undecryptable keys) | **Error returned, nothing recorded** |
| Broker rejects the order | Error surfaced with Alpaca's reason |
| Order placed but post-trade sync fails | Success + `warning` field; the trade did happen |

The third row is the important one. A user whose live gate is closed gets an
explicit error, not a fake fill.

---

## 9. Bug fixed along the way

The original `process_trade()` credited sale proceeds and *then* decremented
holdings, with no check that the shares existed:

```python
# before
proceeds = quantity * price
cursor.execute("UPDATE portfolios SET balance = balance + ? ...")
cursor.execute("UPDATE holdings SET quantity = quantity - ? ...")
```

A SELL on a ticker the user did not hold created cash from nothing and drove
`holdings.quantity` negative. In an app whose core feature is an autonomous bot
emitting SELL signals, that quietly corrupts every downstream P&L number.

The simulated path now verifies the position before crediting anything. The
broker path gets this for free: Alpaca rejects the oversell itself, which is a
second reason to treat it as the source of truth.

Four regression tests cover it, including one asserting the bot is held to the
same rule.

---

## 10. API surface

All routes authenticate via the existing cookie/bearer dependency.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/broker/status` | Link state + server gate visibility |
| POST | `/api/broker/link` | Link a **paper** account |
| POST | `/api/broker/link/live` | Promote to **live** (requires acknowledgement) |
| POST | `/api/broker/enabled` | Pause/resume routing without deleting keys |
| DELETE | `/api/broker/unlink` | Delete credentials (history retained) |
| GET | `/api/broker/account` | Live account snapshot |
| GET | `/api/broker/positions` | Open positions |
| GET | `/api/broker/clock` | Authoritative market hours |
| POST | `/api/broker/sync` | Force refresh of balance and holdings |
| POST | `/api/broker/reconcile` | Update still-working orders |

`/api/broker/status` returns the server gates alongside the link state so the UI
can explain *why* live is unavailable rather than just failing when the user
tries.

`/api/broker/clock` is worth adopting in the scheduler: the current market-hours
check is hand-rolled hour arithmetic that does not know about holidays or half
days.

---

## 11. Configuration

```bash
# Required to link any brokerage
BROKER_ENCRYPTION_KEY=          # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Live trading gates
ALLOW_LIVE_TRADING=false
ALLOW_LIVE_BOT_TRADING=false

# Optional tuning
BROKER_FILL_POLL_TIMEOUT=8
BROKER_FILL_POLL_INTERVAL=0.75
```

Dependency added: `alpaca-py==0.44.0` (plus `msgpack`, `sseclient-py`; the rest
of its tree was already pinned).

---

## 12. Rollout

1. Generate `BROKER_ENCRYPTION_KEY`, add to `.env`. Leave both live flags false.
2. Deploy. Migrations run on startup; existing users are unaffected.
3. Link an Alpaca **paper** account via `/api/broker/link`.
4. Trade manually to confirm orders reach Alpaca and fills come back.
5. Turn the bot on against paper. Let it run.
6. Only after the model's action distribution is fixed and paper results are
   acceptable, consider `ALLOW_LIVE_TRADING=true` and a live link.
7. Leave `ALLOW_LIVE_BOT_TRADING=false` well beyond that point.

---

## 13. Known gaps

Deliberately out of scope for this pass:

- **Market orders only.** No limit, stop or bracket orders. The RL model emits
  BUY/SELL/HOLD with no price target, so limits would need a policy change first.
- **Long-only.** The schema assumes positive quantities; shorts are skipped
  during sync.
- **Whole shares only.** `holdings.quantity` and `trades.quantity` are INTEGER.
  Fractional shares would need a schema migration.
- **Polling, not streaming.** Alpaca offers a websocket trade-update stream that
  would replace `reconcile_open_orders()` with push updates. Polling on the
  existing scheduler tick is simpler and adequate at current volume.
- **No frontend.** The Angular UI needs a broker-settings page; the endpoints are
  ready for it.
- **Risk manager still reads local state.** `RiskManager` runs before the broker
  call against the synced cache. Since the sync happens immediately before, this
  is correct in practice, but Alpaca's own buying power is the stronger check and
  is applied by Alpaca regardless.
- **PDT tracking is local.** Alpaca reports `daytrade_count` and
  `pattern_day_trader` on the account; the risk manager's own counter could be
  replaced by those.

---

## 14. Tests

36 new tests, all passing alongside the existing 88.

`tests/services/broker_test.py` (24) — credential encryption and fail-closed
behaviour, link lifecycle, all three live gates, order status mapping, fill
handling, `client_order_id` uniqueness, portfolio sync semantics, reconciliation.

`tests/routers/process_trade_test.py` (12) — both execution paths, the oversell
regressions, fill-price-over-quote recording, and the assertion that an unusable
link errors rather than silently simulating.

No test touches the network; the Alpaca client is faked throughout.