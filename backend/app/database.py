import sqlite3 as sql

def get_db_connection():
    conn = sql.connect("stockBot.db")
    conn.row_factory = sql.Row
    return conn

def setup_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS  users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS portfolio (
            user_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            purchase_price REAL NOT NULL,
            PRIMARY KEY (user_id, ticker),
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    conn.commit()
    conn.close()