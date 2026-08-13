import os


from dotenv import load_dotenv
load_dotenv()


import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


# Custon imports
from app.core.config import ORIGINS
from app.core.database import setup_database
from app.routers import auth, portfolio, trading
from app.tasks.scheduler import run_trading_bot


try:
    is_production = os.getenv("ENV", "development").lower() == "production"
    if is_production:
        docs = None
        redoc = None
    else:
        docs = "/docs"
        redoc = "/redoc"
except Exception as e:
    print("ENV is missing from .env file")


app = FastAPI(
    title="TickerStream AI API",
    version="1.0.0",
    description="Operational TickerStream AI API",
    docs_url=docs,
    redoc_url=redoc,
    )


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
async def startup_event():
    setup_database()
    # Start the background loop
    asyncio.create_task(run_trading_bot())
