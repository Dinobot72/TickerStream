import importlib
import json
import pytest


@pytest.fixture
def fresh_config(monkeypatch):
    """
    Yields a function that reloads app.core.config after env vars have
    been set, so each test can control what the module 'sees' at import
    time. Restores the module to its normal state afterward so later
    tests/files aren't left with a mutated SECRET_KEY or ORIGINS.
    """
    import app.core.config as config_module

    def _reload():
        return importlib.reload(config_module)

    yield _reload

    # Restore real env and reload once more so any other test file that
    # imports app.core.config afterward gets the normal, non-monkeypatched values.
    monkeypatch.undo()
    importlib.reload(config_module)


class TestSecretKey:
    def test_uses_env_var_when_set(self, fresh_config, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "my-test-secret")
        config = fresh_config()
        assert config.SECRET_KEY == "my-test-secret"

    def test_generates_random_key_and_warns_when_unset(self, fresh_config, monkeypatch):
        monkeypatch.delenv("SECRET_KEY", raising=False)
        with pytest.warns(RuntimeWarning, match="SECRET_KEY environment variable is not set"):
            config = fresh_config()
        assert config.SECRET_KEY is not None
        assert len(config.SECRET_KEY) > 0

    def test_generated_key_differs_between_reloads(self, fresh_config, monkeypatch):
        # confirms it's actually random each time, not a hardcoded fallback
        monkeypatch.delenv("SECRET_KEY", raising=False)
        with pytest.warns(RuntimeWarning):
            config1 = fresh_config()
        key1 = config1.SECRET_KEY
        with pytest.warns(RuntimeWarning):
            config2 = fresh_config()
        assert key1 != config2.SECRET_KEY


class TestOrigins:
    def test_uses_default_origins_when_env_unset(self, fresh_config, monkeypatch):
        monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
        config = fresh_config()
        assert "https://ticker-stream.com" in config.ORIGINS
        assert "http://localhost:4200" in config.ORIGINS

    def test_parses_json_origins_from_env(self, fresh_config, monkeypatch):
        custom = ["https://example.com", "https://staging.example.com"]
        monkeypatch.setenv("ALLOWED_ORIGINS", json.dumps(custom))
        config = fresh_config()
        assert config.ORIGINS == custom

    def test_invalid_json_in_origins_raises(self, fresh_config, monkeypatch):
        monkeypatch.setenv("ALLOWED_ORIGINS", "not valid json{{{")
        with pytest.raises(json.JSONDecodeError):
            fresh_config()


class TestConstants:
    def test_algorithm_is_hs256(self, fresh_config, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "test-key")
        config = fresh_config()
        assert config.ALGORITHM == "HS256"

    def test_token_expiry_is_60_minutes(self, fresh_config, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "test-key")
        config = fresh_config()
        assert config.ACCESS_TOKEN_EXPIRE_MINUTES == 60