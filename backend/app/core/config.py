import os
from typing import List

# --- Security Configuration ---
SECRET_KEY = "604f4b0bb91cbf5d981f3152a0b2223eceaf22f18df22d1e7511a835da818a20"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
COOKIE_NAME = "access_token"

# --- CORS Config --- 
ORIGINS = [
    "https://ticker-stream.com",       # Your production frontend
    "https://auth.ticker-stream.com",  # Your production backend
    "http://localhost:4200",           # Local development
    "http://100.85.77.37",             # Tailscale/Local IP
]

class GlobalBotState:
    is_active: bool = False

bot_state = GlobalBotState()