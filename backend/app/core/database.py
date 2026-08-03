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

    conn.commit()

    # Migrate existing databases that were created before the timestamp column
    try:
        cursor.execute(
            "ALTER TABLE portfolios ADD COLUMN timestamp DATETIME DEFAULT CURRENT_TIMESTAMP"
        )
        conn.commit()
    except sql.OperationalError:
        pass  # Column already exists — safe to ignore

    conn.close()