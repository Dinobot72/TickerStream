import sqlite3 as sql
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'tickerstream.db')

def get_db_connection():
    conn = sql.connect(DB_PATH)
    conn.row_factory = sql.Row
    return conn

def setup_database():
    conn = get_db_connection()
    cursor = conn.cursor()

    # User Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS  users (
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
    
    conn.commit()
    conn.close()