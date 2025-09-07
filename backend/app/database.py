import sqlite3 as sql

def get_db_connection():
    conn = sql.connect("stockBot.db")
    conn.row_factory = sql.Row
    return conn

def setup_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS portfolio (
            user_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            purchase_price REAL NOT NULL,
            PRIMARY KEY (user_id, ticker)
        )
    ''')
    conn.commit()
    conn.close()