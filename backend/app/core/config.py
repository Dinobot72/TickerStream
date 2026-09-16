import os
import json
import secrets
from typing import List

# --- Security Configuration ---
# If SECRET_KEY is not set, generate a random one and warn loudly.
_secret_key_env = os.getenv("SECRET_KEY")
if not _secret_key_env:
    # This will only happen locally without a .env file. In production,
    # SECRET_KEY must be set — tokens signed with a random key are invalidated on restart.
    import warnings
    warnings.warn(
        "SECRET_KEY environment variable is not set. "
        "A temporary key has been generated. All tokens will be invalidated on restart. "
        "Set SECRET_KEY in your environment or .env file.",
        RuntimeWarning,
        stacklevel=2,
    )
    _secret_key_env = secrets.token_hex(32)


SECRET_KEY = _secret_key_env
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
COOKIE_NAME = "access_token"

# --- CORS Config --- 
_origins_env = os.getenv("ALLOWED_ORIGINS")

if _origins_env:
    ORIGINS = json.loads(_origins_env)
else:
    ORIGINS = [
        "https://ticker-stream.com",       # Production frontend
        "https://auth.ticker-stream.com",  # Production backend
        "http://localhost:4200",           # Local development
        "http://127.0.0.1:4200",           # Local development loopback
        "http://100.85.77.37",             # Tailscale IP
    ]


# --- Broker / Live Trading Configuration ---
#
# Three independent switches gate real money. All three must be deliberately
# turned on; none of them default to permissive.
#
#   1. ALLOW_LIVE_TRADING      — server-wide kill switch for live (real money)
#                                orders. Off by default. When off, any account
#                                configured for live mode is refused at the
#                                broker layer regardless of what the DB says.
#
#   2. per-user account mode   — each user's linked account is stored with
#                                mode='paper' or mode='live' (see broker_accounts).
#                                Linking defaults to paper; switching to live
#                                requires a separate explicit confirmation call.
#
#   3. ALLOW_LIVE_BOT_TRADING  — even with 1 and 2 on, the autonomous RL bot is
#                                blocked from live orders unless this is set.
#                                Manual UI trades are unaffected. This exists
#                                because a model producing near-uniform action
#                                probabilities should not be given a live account;
#                                keep it off until the policy is validated.

def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


ALLOW_LIVE_TRADING = _env_bool("ALLOW_LIVE_TRADING", False)
ALLOW_LIVE_BOT_TRADING = _env_bool("ALLOW_LIVE_BOT_TRADING", False)

# Seconds to wait for a market order to reach a terminal state before giving up
# and recording it as PENDING for the reconciler to pick up later.
BROKER_FILL_POLL_TIMEOUT = float(os.getenv("BROKER_FILL_POLL_TIMEOUT", "8"))
BROKER_FILL_POLL_INTERVAL = float(os.getenv("BROKER_FILL_POLL_INTERVAL", "0.75"))