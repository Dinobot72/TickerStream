import os
from typing import List

# --- Security Configuration ---
SECRET_KEY = "***REMOVED_KEY***"
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