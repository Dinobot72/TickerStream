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
    order_type: str = 'MARKET'
    limit_price: Optional[float] = None

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

class PortfolioUpdate( BaseModel ):
    first_name: str
    last_name: str

class PasswordChange( BaseModel ):
    current_password: str
    new_password: str

class WatchlistAdd( BaseModel ):
    ticker: str

class BotStatus(BaseModel):
    status: str 
    message: Optional[str] = None

# Placeholder for actual bot state management
bot_state: Dict[int, BotStatus] = {}

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

@app.post("/api/user/{user_id}/change-password")
def change_user_password(user_id: int, password_data: PasswordChange, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM users WHERE user_id = ?", (user_id,))
    user_record = cursor.fetchone()

    if user_record is None:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(password_data.current_password, user_record["password"]):
        conn.close()
        raise HTTPException(status_code=400, detail="Incorrect current password")

    new_hashed_password = get_password_hash(password_data.new_password)
    try:
        cursor.execute("UPDATE users SET password = ? WHERE user_id = ?", (new_hashed_password, user_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error changing password: {e}")
        raise HTTPException(status_code=500, detail="Could not change password.")
    finally:
        conn.close()
    
    return {"message": "Password updated successfully"}

@app.get("/api/stock/{ticker}")
def get_stock_chart( ticker: str ):
    return get_stock_data(ticker.upper())

@app.get("/api/metrics/{ticker}")
def get_metrics(ticker: str):
    metrics = get_stock_metrics(ticker.upper())
    if not metrics:
         raise HTTPException(status_code=404, detail=f"Could not retrieve metrics for ticker {ticker.upper()}")
    metrics["dividend_yield"] = metrics.get("dividend_yield") or 0.0
    metrics["pe_ratio"] = metrics.get("pe_ratio") or "N/A"
    return metrics

@app.get("/api/holdings/{user_id}", response_model=List[Dict])
def get_holdings(user_id: int, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail=f'Not authorized {current_user["user_id"]} != {user_id}')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ticker, quantity, purchase_price FROM holdings WHERE user_id=? AND quantity > 0", (user_id,))
    holdings = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return holdings

@app.post("/api/trade/")
def record_trade(trade: Trade, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != trade.user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Basic validation before DB operations
    if trade.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be positive.")
    if trade.price <= 0:
         raise HTTPException(status_code=400, detail="Price must be positive.")
    if trade.action.upper() not in ["BUY", "SELL"]:
        raise HTTPException(status_code=400, detail="Action must be BUY or SELL.")

    # Get current balance
    cursor.execute("SELECT balance FROM portfolios WHERE user_id = ?", (trade.user_id,))
    portfolio = cursor.fetchone()
    if portfolio is None:
        raise HTTPException(status_code=404, detail="User portfolio not found.")
    current_balance = portfolio['balance']

    # Get current holding quantity (if selling)
    current_quantity = 0
    if trade.action.upper() == "SELL":
        cursor.execute("SELECT quantity FROM holdings WHERE user_id = ? AND ticker = ?", 
                       (trade.user_id, trade.ticker.upper()))
        holding = cursor.fetchone()
        if holding:
            current_quantity = holding['quantity']
        if trade.quantity > current_quantity:
            raise HTTPException(status_code=400, detail="Insufficient shares to sell.")

    # Calculate cost/proceeds
    trade_value = trade.quantity * trade.price
    transaction_fee = trade_value * 0.001 # Example fee

    try:
        # Record the trade first
        cursor.execute(
            "INSERT INTO trades (user_id, ticker, action, quantity, price, is_bot_trade) VALUES (?, ?, ?, ?, ?, ?)",
            (trade.user_id, trade.ticker.upper(), trade.action.upper(), trade.quantity, trade.price, trade.is_bot_trade)
        )

        if trade.action.upper() == "BUY":
            total_cost = trade_value + transaction_fee
            if total_cost > current_balance:
                 raise HTTPException(status_code=400, detail="Insufficient balance.")
            
            # Update balance
            cursor.execute("UPDATE portfolios SET balance = balance - ? WHERE user_id = ?", (total_cost, trade.user_id))
            
            # Update holdings (using average cost - more complex logic needed for true average)
            # This simplified version just updates quantity. For avg cost, fetch existing holding first.
            cursor.execute(
                "INSERT INTO holdings (user_id, ticker, quantity, purchase_price) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(user_id, ticker) DO UPDATE SET quantity = quantity + excluded.quantity", 
                # Ideally, update purchase_price based on weighted average
                (trade.user_id, trade.ticker.upper(), trade.quantity, trade.price) 
            )

        elif trade.action.upper() == "SELL":
            total_proceeds = trade_value - transaction_fee
            
            # Update balance
            cursor.execute("UPDATE portfolios SET balance = balance + ? WHERE user_id = ?", (total_proceeds, trade.user_id))
            
            # Update holdings
            cursor.execute("UPDATE holdings SET quantity = quantity - ? WHERE user_id = ? AND ticker = ?",
                           (trade.quantity, trade.user_id, trade.ticker.upper()))
            # Remove holding if quantity reaches zero
            cursor.execute("DELETE FROM holdings WHERE user_id = ? AND ticker = ? AND quantity <= 0",
                           (trade.user_id, trade.ticker.upper()))

        conn.commit()
    except HTTPException as http_exc: # Re-raise known validation errors
        conn.rollback()
        raise http_exc
    except Exception as e:
        conn.rollback()
        print(f"Error recording trade: {e}")
        raise HTTPException(status_code=500, detail="Could not record trade.")
    finally:
        conn.close()
        
    return {"message": "Trade recorded successfully."}

@app.get("/api/activity/{user_id}")
def get_activity(user_id: int, limit: int = 10, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail=f'not authorized {current_user["user_id"]} != {user_id}')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT action, ticker, quantity, price, is_bot_trade FROM trades WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?", (user_id, limit))
    activities = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return activities

# --- NEW: Watchlist Endpoints ---
@app.get("/api/watchlist/{user_id}", response_model=List[Dict])
def get_watchlist(user_id: int, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ticker, added_at FROM watchlist WHERE user_id=?", (user_id,))
    watchlist = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return watchlist

@app.post("/api/watchlist/{user_id}")
def add_to_watchlist(user_id: int, item: WatchlistAdd, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    ticker = item.ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker cannot be empty.")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check if it already exists to prevent duplicate errors showing as 500
        cursor.execute("SELECT 1 FROM watchlist WHERE user_id = ? AND ticker = ?", (user_id, ticker))
        exists = cursor.fetchone()
        if exists:
            # Optionally return a different status code like 200 or 204 if already exists
            return {"message": f"{ticker} is already in the watchlist."} 
        
        cursor.execute("INSERT INTO watchlist (user_id, ticker) VALUES (?, ?)", (user_id, ticker))
        conn.commit()
    except sqlite3.IntegrityError: # Should be caught by the check above, but as a fallback
        conn.rollback()
        raise HTTPException(status_code=409, detail=f"{ticker} already exists in watchlist.") # 409 Conflict
    except Exception as e:
        conn.rollback()
        print(f"Error adding to watchlist: {e}")
        raise HTTPException(status_code=500, detail="Could not add to watchlist.")
    finally:
        conn.close()
    return {"message": f"{ticker} added to watchlist successfully."}

@app.delete("/api/watchlist/{user_id}/{ticker}")
def remove_from_watchlist(user_id: int, ticker: str, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    ticker_upper = ticker.strip().upper()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (user_id, ticker_upper))
        conn.commit()
        if cursor.rowcount == 0:
             raise HTTPException(status_code=404, detail=f"{ticker_upper} not found in watchlist.")
    except Exception as e:
        conn.rollback()
        print(f"Error removing from watchlist: {e}")
        raise HTTPException(status_code=500, detail="Could not remove from watchlist.")
    finally:
        conn.close()
    return {"message": f"{ticker_upper} removed from watchlist successfully."}


# --- Bot Control Endpoints (Placeholders) ---
@app.post("/api/bot/start")
def start_bot(current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    # TODO: Implement actual logic to start the bot process for this user
    print(f"Placeholder: Starting bot for user {user_id}")
    bot_state[user_id] = BotStatus(status="active", message="Bot is starting...")
    # Simulate startup time
    # In a real app, this would involve background tasks/processes
    import time
    time.sleep(1) 
    bot_state[user_id] = BotStatus(status="active", message="Actively monitoring market...")
    return bot_state[user_id]

@app.post("/api/bot/stop")
def stop_bot(current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    # TODO: Implement actual logic to stop the bot process for this user
    print(f"Placeholder: Stopping bot for user {user_id}")
    bot_state[user_id] = BotStatus(status="inactive", message="Bot stopped by user.")
    return bot_state[user_id]

@app.get("/api/bot/status", response_model=BotStatus)
def get_bot_status(current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    # TODO: Implement logic to check the actual status of the bot process
    status = bot_state.get(user_id, BotStatus(status="inactive", message="Bot has not been started."))
    return status

# --- Bot Decision Endpoint ---
@app.post("/api/bot/decision")
def make_decision(state: PortfolioState, current_user: dict = Depends(get_current_user)):
    if get_bot_decision is None:
         raise HTTPException(status_code=501, detail="Strategy engine not loaded.")
    try:
        decision_result = get_bot_decision(state.balance, state.shares_held)
        if "error" in decision_result:
            raise HTTPException(status_code=500, detail=decision_result["error"])
        
        # Optionally: Automatically execute the trade based on the decision
        # Be very careful with auto-execution in a real application!
        # decision = decision_result.get("decision")
        # if decision in ["BUY", "SELL"]:
        #     # Fetch current price, determine quantity etc. then call record_trade
        #     pass 

        return decision_result
    except Exception as e:
        print(f"Error during bot decision: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred while getting bot decision: {str(e)}")
