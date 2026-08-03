from app.core.database import get_db_connection

def is_bot_active( user_id: int ) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_active FROM bot_settings WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row["is_active"]) if row else False

def set_bot_active( user_id: int, active: bool ) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO bot_settings (user_id, is_active) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET is_active = excluded.is_active",
        (user_id, active),
    )
    conn.commit()
    conn.close()

def get_active_bot_user_ids() -> list[int]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM bot_settings WHERE is_active = 1")
    ids = [row["user_id"] for row in cursor.fetchall()]
    conn.close()
    return ids