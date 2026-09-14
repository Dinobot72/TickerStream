import pytest
from app.core import database


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """
    Points every test at an isolated temp sqlite file instead of the real
    tickerstream.db. Autouse because there's no legitimate reason any test
    should ever touch the real database.
    """
    db_file = tmp_path / "tmp_tickerstream.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_file))
    database.setup_database()
    yield str(db_file)


@pytest.fixture
def logged_in_user(tmp_db):
    """Inserts a real user row. Opt-in — not every test wants a valid user
    (e.g. tests asserting FK behavior on a nonexistent user_id)."""
    conn = database.get_db_connection()
    conn.execute(
        "INSERT INTO users (username, password, first_name, last_name) VALUES (?, ?, ?, ?)",
        ("testuser", "hashed_pw", "Test", "User"),
    )
    conn.commit()
    user_id = conn.execute(
        "SELECT user_id FROM users WHERE username = ?", ("testuser",)
    ).fetchone()["user_id"]
    conn.close()
    return user_id