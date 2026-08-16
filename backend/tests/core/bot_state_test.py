import sqlite3
import pytest
from app.core.bot_state import is_bot_active, set_bot_active, get_active_bot_user_ids


class TestBotState:
    def test_is__bot_active(self, user):
        assert is_bot_active(user) == False

    def test_set_bot_active(self,user):
        set_bot_active(user, True)
        assert is_bot_active(user) == True

    def test_set_bot_active_false(self,user):
        set_bot_active(user, True)
        set_bot_active(user, False)
        assert is_bot_active(user) == False


    def test_get_active_bot_user_ids(self, user):
        set_bot_active(user, True)
        assert get_active_bot_user_ids() == [user]

    def test_set_bot_active_nonexistent_user_raises(self):
        with pytest.raises(sqlite3.IntegrityError):
            set_bot_active(9999, True)
