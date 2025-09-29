# File: backend/app/main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .database import get_db_connection, setup_database
from .services import get_stock_data, get_stock_metrics
import sys
import os
import sqlite3

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from model.bot.strategy_engine import get_bot_decision
from pydantic import BaseModel
from typing import List, Dict

class PortfolioState(BaseModel):
    balance: float
    shares_held: int

class Trade(BaseModel):
    user_id: int
    ticker: int
    action: str
    quantity: int
    price: float

class User(BaseModel):
    username: str
    password: str
    first_name: str
    last_name: str

class LoginCredentials( BaseModel ):
    username: str
    password: str

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

@app.post("/api/register")
def register_user( user: User):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password, first_name, last_name) VALUES (?, ?, ?, ?)",
                       (user.username, user.password, user.first_name, user.last_name))
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already exists")
    finally:
        conn.close()
    return {"mesage": "User registered succesfully"}

@app.post("/api/login")
def login_user( credentials: LoginCredentials ):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, password FROM users WHERE username = ?", (credentials.username,))
    user = cursor.fetchone()
    conn.close()
    if user is None or not user["password"] == credentials.password:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {"message": "Login successful", "user_id": user["user_id"]}

@app.get("/api/user/{user_id}")
def get_user_info( user_id: int ):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, first_name, last_name FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return dict(user)


@app.get("/")
def read_root():
    return {
        "message": "Hello from the Backend!\n",
        "stock": get_stock_chart('AAPL'),
        "metrics": get_metrics('AAPL'),
        "portfolio": get_portfolio("1") ,
    }

@app.get("/api/stock/{ticker}")
def get_stock_chart( ticker: str ):
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
        cursor.execute("INSERT OR REPLACE INTO portfolio (user_id, ticker, quantity, purchase_price) VALUES (?, ?, ?, ?)",
                       {trade.user_id, trade.ticker.upper(), trade.quantity, trade.price})
        
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
 

