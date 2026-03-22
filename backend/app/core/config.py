import os
import json
from typing import List

# --- Security Configuration ---
SECRET_KEY = "604f4b0bb91cbf5d981f3152a0b2223eceaf22f18df22d1e7511a835da818a20"
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
    
class GlobalBotState:
    is_active: bool = False

bot_state = GlobalBotState()