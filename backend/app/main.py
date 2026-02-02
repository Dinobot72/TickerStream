from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio

from app.core.config import ORIGINS
from app.core.database import setup_database
from app.routers import auth, portfolio, trading
from app.tasks.scheduler import run_trading_bot

app = FastAPI()

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(portfolio.router)
app.include_router(trading.router)

@app.on_event("startup")
def startup_event():
    setup_database()
    # Start the background loop
    asyncio.create_task(run_trading_bot())