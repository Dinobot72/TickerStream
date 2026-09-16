import sqlite3 as sql
import os

# Read the database path from an environment variable so it can be
# pointed at the Docker volume mount (/app/data/tickerstream.db).
# Falls back to the original hardcoded location for local development
# so nothing breaks when running outside Docker.
_default_path = os.path.join(os.path.dirname(__file__), '..', '..', 'tickerstream.db')
DB_PATH = os.getenv("DATABASE_PATH", _default_path)


def get_db_connection():
    conn = sql.connect(DB_PATH)
    conn.row_factory = sql.Row
    # SQLite does not enforce FOREIGN KEY constraints unless this is set
    # per-connection — without it, the FOREIGN KEY clauses below are
    # decorative only.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def setup_database():
    # Ensure the directory exists (important when the path is inside a volume)
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)

    conn = get_db_connection()
    cursor = conn.cursor()

    # User Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL
        )
    ''')

    # Portfolios Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS portfolios (
            user_id INTEGER PRIMARY KEY,
            balance REAL NOT NULL DEFAULT 0.0,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')

    # Holdings Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS holdings (
            user_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            purchase_price REAL NOT NULL,
            PRIMARY KEY (user_id, ticker),
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')

    # Trades Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            action TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_bot_trade BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')

    # Watchlist Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS watchlist (
            user_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, ticker),
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')

    # Bot Watchlist Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_watchlist (
            user_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, ticker),
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')

    # Bot User Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_settings (
            user_id INTEGER PRIMARY KEY,
            is_active BOOLEAN NOT NULL DEFAULT FALSE,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')

    # Portfolio Snapshots Table
    # Append-only daily record of each user's balance. `portfolios.balance`
    # is a single mutable row that gets overwritten on every trade, so it
    # cannot answer "what was my balance yesterday?" — this table can.
    # One row per (user_id, snapshot_date); insert/update once per day,
    # typically at market close or on first trade of a new day.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            user_id INTEGER NOT NULL,
            snapshot_date DATE NOT NULL,
            balance REAL NOT NULL,
            PRIMARY KEY (user_id, snapshot_date),
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')

    # Broker Accounts Table
    # One linked brokerage account per user. Credentials are stored encrypted
    # (see app/core/crypto.py) — never plaintext.
    #
    #   mode              'paper' or 'live'. Linking always starts as 'paper';
    #                     promoting to 'live' is a separate, explicit action.
    #   is_enabled        User can pause broker routing without deleting keys.
    #                     When 0, process_trade() falls back to simulation.
    #   live_confirmed_at Timestamp of the explicit "yes, trade real money"
    #                     acknowledgement. NULL means live was never confirmed
    #                     and live orders are refused even if mode says 'live'.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS broker_accounts (
            user_id INTEGER PRIMARY KEY,
            provider TEXT NOT NULL DEFAULT 'alpaca',
            api_key_encrypted TEXT NOT NULL,
            secret_key_encrypted TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'paper' CHECK (mode IN ('paper', 'live')),
            is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            broker_account_id TEXT,
            linked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            live_confirmed_at DATETIME,
            last_sync_at DATETIME,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')

    conn.commit()

    # --- Migrations for existing databases ---

    # `trades` predates broker integration: it assumed every row was an instantly
    # filled simulated trade. Real orders are asynchronous and can be rejected or
    # partially filled, so each trade now carries broker linkage and a lifecycle
    # status. Existing rows are backfilled as FILLED simulated trades, which is
    # what they actually were.
    for column, ddl in (
        ("broker_order_id", "ALTER TABLE trades ADD COLUMN broker_order_id TEXT"),
        ("status", "ALTER TABLE trades ADD COLUMN status TEXT NOT NULL DEFAULT 'FILLED'"),
        ("mode", "ALTER TABLE trades ADD COLUMN mode TEXT NOT NULL DEFAULT 'simulated'"),
        ("filled_qty", "ALTER TABLE trades ADD COLUMN filled_qty INTEGER"),
        ("filled_avg_price", "ALTER TABLE trades ADD COLUMN filled_avg_price REAL"),
    ):
        try:
            cursor.execute(ddl)
            conn.commit()
        except sql.OperationalError:
            pass  # Column already exists — safe to ignore

    # Index for the reconciler, which repeatedly asks "which orders are still open?"
    try:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_trades_open_orders "
            "ON trades (status, broker_order_id)"
        )
        conn.commit()
    except sql.OperationalError:
        pass

    # Migrate existing databases that were created before the timestamp column
    try:
        cursor.execute(
            "ALTER TABLE portfolios ADD COLUMN timestamp DATETIME DEFAULT CURRENT_TIMESTAMP"
        )
        conn.commit()
    except sql.OperationalError:
        pass  # Column already exists — safe to ignore

    conn.close()