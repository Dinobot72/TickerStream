from fastapi import FastAPI, HTTPException, Depends, Response, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
from typing import List, Dict, Optional
import sys
import os
import sqlite3

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from model.bot.strategy_engine import get_bot_decision

from .database import get_db_connection, setup_database
from .services import get_stock_data, get_stock_metrics

# --- Security Configuration ---
SECRET_KEY = "***REMOVED_KEY***"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
COOKIE_NAME = "access_token"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class CookieBearer(HTTPBearer):
    async def __call__(self, request: Request) -> Optional[HTTPAuthorizationCredentials]:
        token = request.cookies.get(COOKIE_NAME)
        if token:
            return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        
        return await super().__call__(request)
    
cookie_bearer = CookieBearer(auto_error=False)

class PortfolioState( BaseModel ):
    balance: float
    shares_held: int

class Trade( BaseModel ):
    user_id: int
    ticker: str
    action: str
    quantity: int
    price: float
    is_bot_trade: bool = False

class User( BaseModel ):
    username: str
    password: str
    first_name: str
    last_name: str

class LoginCredentials( BaseModel ):
    username: str
    password: str

class Deposit( BaseModel ):
    amount: float

# --- FastApi Configuration
app = FastAPI()

origins = [
    "http://localhost:4200",
    "http://127.0.0.1:4200",
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
    print(f'verifying password: {plain_password} vs {hashed_password}')
    return pwd_context.verify( plain_password, hashed_password )

def get_password_hash( password ):
    return pwd_context.hash( password )

def create_access_token( data: dict ):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    print(f'Access Token Exprire: {expire}')
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def set_auth_cookie(response: Response, token: str):
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=False, # Set to true in production
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
        domain=None,
    )

# --- Dependency for getting current user ---
async def get_current_user( 
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(cookie_bearer)
):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate Credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    print(f"All cookies in request: {request.cookies}")

    # Get token
    token = request.cookies.get(COOKIE_NAME)
    print(f"Looking for cookie: {COOKIE_NAME}")
    print(f"Token found: {token is not None}")

    if not token and credentials:
        token = credentials.credentials
        print(f"Token found: {token is not None}")


    if not token:
        print("No token found in Request")
        raise credentials_exception

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        user_id: int = payload.get("id")

        print(f"Decoded token - username: {username}, user_id: {user_id}")

        if username is None or user_id is None:
            raise credentials_exception.detail("Could not validate Credentials, Username is none")
        
    except JWTError as e:
        print(f"--- JWT DECODE ERROR: {e} ---")
        raise credentials_exception
    
    return {"username": username, "user_id": user_id}

@app.on_event("startup")
def on_startup():
    setup_database()

# --- FastApi Endpoints ---
@app.post("/api/register")
def register_user( user: User):
    hashed_password = get_password_hash( user.password )
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password, first_name, last_name) VALUES (?, ?, ?, ?)",
                       (user.username, hashed_password, user.first_name, user.last_name))
        user_id = cursor.lastrowid

        cursor.execute("INSERT INTO portfolios (user_id, balance) VALUES (?, ?)", (user_id, 0.00))
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException( status_code=400, detail="Username already exists" )
    finally:
        conn.close()
    return {"message": "User registered succesfully"}

@app.post("/api/login")
def login_for_access_token( response: Response, credentials: LoginCredentials ):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, password FROM users WHERE username = ?", (credentials.username,))
    user = cursor.fetchone()
    conn.close()

    if user is None or not verify_password(credentials.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    print(f"Setting cookie for user: {credentials.username}")
    access_token = create_access_token(data={"sub": credentials.username, "id": user["user_id"]})

    set_auth_cookie(response, access_token)

    return {"message": "Login successful",
            "access_token": access_token,
            "token_type": "bearer",
            "user_id": user["user_id"]}

@app.post("/api/logout")
def logout( response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"message": "Logged out succesfully"}

@app.get("/api/auth/status")
def check_auth_status( current_user: Dict = Depends(get_current_user)):
    return {"authenticated": True, "user": current_user}

@app.get("/api/user/{user_id}")
def get_user_info( user_id: int, current_user: dict = Depends(get_current_user)):
    print('current_user:', current_user['user_id'], 'user_id:', user_id)
    if current_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail=f'not authorized {current_user["user_id"]} != {user_id}')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT u.user_id, u.username, u.first_name, u.last_name, p.balance "
        "FROM users u JOIN portfolios p ON u.user_id = p.user_id "
        "WHERE u.user_id = ?", 
        (user_id,)
    )
    user = cursor.fetchone()
    conn.close()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return dict(user)

@app.post("/api/user/{user_id}/deposit")
def deposit_funds( user_id: int, deposit: Deposit, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail=f'not authorized {current_user["user_id"]} != {user_id}')
    if deposit.amount < 0:
        raise HTTPException(status_code=400, detail="Deposit amount must be non positive")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE portfolios SET balance = balance + ?  WHERE user_id = ?", (deposit.amount, user_id))
    conn.commit()

    cursor.execute("SELECT balance FROM portfolios WHERE user_id = ?", (user_id,))
    new_balance = cursor.fetchone()['balance']

    conn.close()
    return {"message": "Deposit succesful", "new_balance": new_balance}

@app.get("/api/stock/{ticker}")
def get_stock_chart( ticker: str ):
    return get_stock_data(ticker.upper())

@app.get("/api/metrics/{ticker}")
def get_metrics(ticker: str):
    return get_stock_metrics(ticker.upper())

@app.get("/api/holdings/{user_id}", response_model=List[Dict])
def get_holdings(user_id: int, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail=f'not authorized {current_user["user_id"]} != {user_id}')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ticker, quantity, purchase_price FROM holdings WHERE user_id=?", (user_id,))
    holdings = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return holdings

@app.post("/api/trade/")
def record_trade(trade: Trade, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != trade.user_id:
        raise HTTPException(status_code=403, detail=f'not authorized {current_user["user_id"]} != {trade.user_id}')
    
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO trades (user_id, ticker, action, quantity, price, is_bot_trade) VALUES (?, ?, ?, ?, ?, ?)",
        (trade.user_id, trade.ticker.upper(), trade.action, trade.quantity, trade.price, trade.is_bot_trade)
    )

    if trade.action.upper() == "BUY":
        cost = trade.quantity * trade.price
        cursor.execute("UPDATE portfolios SET balance = balance - ? WHERE user_id = ?", (cost, trade.user_id))
        cursor.execute(
            "INSERT INTO holdings (user_id, ticker, quantity, purchase_price) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id, ticker) DO UPDATE SET quantity = quantity + excluded.quantity",
            (trade.user_id, trade.ticker.upper(), trade.quantity, trade.price)
        )
    elif trade.action.upper() == "SELL":
        proceeds = trade.quantity * trade.price
        cursor.execute("UPDATE portfolios SET balance = balance + ? WHERE user_id = ?", (proceeds, trade.user_id))
        cursor.execute("UPDATE holdings SET quantity = quantity - ? WHERE user_id = ? AND ticker = ?",
                       (trade.quantity, trade.user_id, trade.ticker.upper()))
        cursor.execute("DELETE FROM holdings WHERE user_id = ? AND ticker = ? AND quantity <= 0",
                       (trade.user_id, trade.ticker.upper()))

    conn.commit()
    conn.close()
    return {"message": "Trade recorded successfully."}

@app.get("/api/activity/{user_id}")
def get_activity(user_id: int, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail=f'not authorized {current_user["user_id"]} != {user_id}')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT action, ticker, quantity, price, is_bot_trade FROM trades WHERE user_id = ? ORDER BY timestamp DESC LIMIT 5", (user_id,))
    activities = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return activities

@app.post("/api/bot/decision")
def make_decision(state: PortfolioState, current_user: dict = Depends(get_current_user)):
    try:
        decision_result = get_bot_decision(state.balance, state.shares_held)
        if "error" in decision_result:
            raise HTTPException(status_code=500, detail=decision_result["error"])
        return decision_result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
 