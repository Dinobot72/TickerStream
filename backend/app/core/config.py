import os
from typing import List

# --- Security Configuration ---
SECRET_KEY = "604f4b0bb91cbf5d981f3152a0b2223eceaf22f18df22d1e7511a835da818a20"
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