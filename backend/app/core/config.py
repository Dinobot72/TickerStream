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
origins_env = os.getenv("ALLOWED_ORIGINS")

if origins_env:
    ORIGINS = json.loads(origins_env)
else:
    ORIGINS = [
        "https://ticker-stream.com",       # Production frontend
        "https://auth.ticker-stream.com",  # Production backend
        "http://localhost:4200",           # Local development
        "http://127.0.0.1:4200",           # Local development loopback
        "http://100.85.77.37",             # Tailscale IP
    ]