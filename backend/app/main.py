# File: backend/app/main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .database import get_db_connection, setup_database
from .services import get_stock_data, get_stock_metrics
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from model.bot.strategy_engine import get_bot_decision
from pydantic import BaseModel
from typing import List, Dict

class PortfolioState(BaseModel):
    balance: float
    shares_held: int

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
    return {
        "message": "Hello from the Backend!\n",
        "stock": get_stock_chart('AAPL'),
        "metrics": get_metrics('AAPL'),
        "portfolio": get_portfolio("temp_user") ,
    }

@app.get("/api/stock/{ticker}")
def get_stock_chart(ticker: str):
    return get_stock_data(ticker.upper())

@app.get("/api/metrics/{ticker}")
def get_metrics(ticker: str):
    return get_stock_metrics(ticker.upper())

@app.get("/api/portfolio/{user_id}", response_model=List[Dict])
def get_portfolio(user_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ticker, quantity, purchase_price FROM portfolio WHERE user_id=?", (user_id,))
    holdings = [dict(row) for row in cursor.fetchall()]
    conn.close()

    current_value = 0.0
    previous_close_value = 0.0

    for holding in holdings:
        ticker = holding["ticker"]
        quantity = holding["quantity"]
        purchase_price = holding["purchase_price"]

        stock_data = get_stock_data(ticker)

        if stock_data and "latestPrice" in stock_data:
            current_price = stock_data["latestPrice"]
            current_value = quantity * current_price
            previous_close_value = quantity * purchase_price
        else: 
            current_value = quantity * purchase_price
            previous_close_value = quantity * purchase_price

    return {"currentValue": current_value, "previousClose": previous_close_value}

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

@app.post("/api/bot/decision")
def make_decision(state: PortfolioState):
    try:
        decision_result = get_bot_decision(state.balance, state.shares_held)
        if "error" in decision_result:
            raise HTTPException(status_code=500, detail=decision_result["error"])
        return decision_result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
 

