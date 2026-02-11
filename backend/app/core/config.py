import os
from typing import List

# --- Security Configuration ---
SECRET_KEY = "***REMOVED_KEY***"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
COOKIE_NAME = "access_token"

# --- CORS Config --- 
ORIGINS = [
    "http://localhost:4200",
    "http://127.0.0.1:4200",
    # -- PI Addresses --
    "http://100.85.77.37", # Tailwind IP
    "https://ticker-stream.com",
    "https://auth.ticker-stream.com"
]

class GlobalBotState:
    is_active: bool = False

bot_state = GlobalBotState()