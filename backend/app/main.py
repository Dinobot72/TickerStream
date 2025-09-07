# File: backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import get_db_connection, setup_database
from .services import get_stock_data, get_stock_metrics

from pydantic import BaseModel
from typing import List, Dict

class PortfolioItem(BaseModel):
    ticker: str
    quantity: int
    purchase_price: float

class Trade(BaseModel):
    ticker: int
    action: str
    quantity: int
    price: float

app = FastAPI()

origins = [
    "http://localhost:4200",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    setup_database()

@app.get("/")
def read_root():
    return {"message": "Hello from the Backend!\n"}

@app.get("/api/stock/{ticker}")
def get_stock_chart(ticker: str):
    return get_stock_data(ticker.upper())

@app.get("/api/metics/{ticker}")
def get_metrics(ticker: str):
    return get_stock_metrics(ticker.upper())

@app.get("api/portfolio/{user_id}", response_model=List[Dict])
def get_portfolio(user_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ticker, quantity, purchase_price FROM portfolio WHERE user_id=?", (user_id,))
    portfolio = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return portfolio

@app.post("/api/trade/")
def record_trade(trade: Trade):
    conn = get_db_connection()
    cursor = conn.cursor()

    if trade.action == "BUY":
        cursor.execute("EXECUTE OR REPLACE INTO portfolio (user_id, ticker, quantity, purchase_price) VALUES (?, ?, ?, ?)",
                       {"test_user", trade.ticker.upper(), trade.quantity, trade.price})
        
    conn.commit()
    conn.close()
    return {"mesage": "Trade recorded successfully."}

