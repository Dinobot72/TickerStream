import sqlite3
import pytest
from app.core import database


class TestGetDbConnection:
    def test_returns_connection_with_row_factory(self, tmp_db):
        conn = database.get_db_connection()
        assert conn.row_factory is sqlite3.Row
        conn.close()

    def test_foreign_keys_pragma_enabled(self, tmp_db):
        conn = database.get_db_connection()
        result = conn.execute("PRAGMA foreign_keys").fetchone()
        assert result[0] == 1
        conn.close()


class TestSetupDatabase:
    def test_creates_all_expected_tables(self, tmp_db):
        conn = database.get_db_connection()
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        expected = {
            "users", "portfolios", "holdings", "trades",
            "watchlist", "bot_watchlist", "bot_settings",
            "portfolio_snapshots",
        }
        assert expected.issubset(tables)

    def test_running_setup_twice_is_safe(self, tmp_db):
        # setup_database() already ran once via the tmp_db fixture;
        # running it again should not raise (IF NOT EXISTS + caught ALTER)
        database.setup_database()

    def test_portfolios_has_timestamp_column(self, tmp_db):
        conn = database.get_db_connection()
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(portfolios)")}
        conn.close()
        assert "timestamp" in columns

    def test_users_username_is_unique(self, tmp_db):
        conn = database.get_db_connection()
        conn.execute(
            "INSERT INTO users (username, password, first_name, last_name) VALUES (?, ?, ?, ?)",
            ("dupe", "pw", "A", "B"),
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO users (username, password, first_name, last_name) VALUES (?, ?, ?, ?)",
                ("dupe", "pw2", "C", "D"),
            )
        conn.close()

    def test_creates_directory_if_missing(self, tmp_path, monkeypatch):
        nested_path = tmp_path / "nested" / "dir" / "test.db"
        monkeypatch.setattr(database, "DB_PATH", str(nested_path))
        database.setup_database()
        assert nested_path.exists()