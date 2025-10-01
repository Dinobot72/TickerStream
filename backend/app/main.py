# File: backend/app/main.py
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import List, Dict
import sys
import os
import sqlite3

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from model.bot.strategy_engine import get_bot_decision

from .database import get_db_connection, setup_database
from .services import get_stock_data, get_stock_metrics

# --- Security Configuration ---
SECRET_KEY = "42qswyub43s5dytiu"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

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

# --- FastApi Configuration
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

# --- JWT ---
def verify_password( plain_password, hashed_password ):
    return pwd_context.verify( plain_password, hashed_password )

def get_password_hash( password ):
    return pwd_context.hash( password )

def create_access_token( data: dict ):
    to_encode = data.copy()
    expire = datetime.now() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# --- Dependency for getting current user ---
def get_current_user( token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate Credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        user_id: int = payload.get("id")
        if username is None or user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    return {"username": username, "user_id": user_id}

@app.on_event("startup")
def on_startup():
    setup_database()


# --- FastApi Endpoints
@app.post("/api/register")
def register_user( user: User):
    hashed_password = get_password_hash( user.password )
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password, first_name, last_name) VALUES (?, ?, ?, ?)",
                       (user.username, hashed_password, user.first_name, user.last_name))
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException( status_code=400, detail="Username already exists" )
    finally:
        conn.close()
    return {"mesage": "User registered succesfully"}

@app.post("/api/login")
def login_for_access_token( credentials: LoginCredentials ):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, password FROM users WHERE username = ?", (credentials.username,))
    user = cursor.fetchone()
    conn.close()
    if user is None or not verify_password(credentials.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    access_token = create_access_token(data={"sub": credentials.username, "id": user["user_id"]})

    return {"message": "Login successful", "access_token": access_token, "token_type": "bearer", "user_id": user["user_id"]}

@app.get("/api/user/{user_id}")
def get_user_info( user_id: int, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this user's data")
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
 

