import os
from typing import List

# --- Security Configuration ---
SECRET_KEY = "***REMOVED_KEY***"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
COOKIE_NAME = "access_token"

# --- CORS Config --- 
ORIGINS = [
    "http://localhost:4200",
    "http://127.0.0.1:4200",
    "http://54.165.132.147",
]

class GlobalBotState:
    is_active: bool = False

bot_state = GlobalBotState()