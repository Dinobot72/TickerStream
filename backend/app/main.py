
from fastapi import FastAPI, HTTPException, Depends, Response, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from jwt.exceptions import PyJWTError
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo
from pydantic import BaseModel
from typing import List, Dict, Optional
import asyncio
import sqlite3
import json
import math
import sys
import jwt
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from model.bot.strategy_engine import get_bot_decision

from .database import get_db_connection, setup_database
from .services import get_stock_data, get_stock_metrics, get_historical_data, get_full_market_data

# --- Security Configuration ---
SECRET_KEY = os.getenv("SECRET_KEY","***REMOVED_KEY***")
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

# --- Global Bot State ---
# This variable controls the background loop
BOT_ACTIVE = False

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
origins_env = os.getenv("ALLOWED_ORIGINS")
if origins_env:
    origins = json.loads(origins_env)
else:
    origins = [
        "https://ticker-stream.com",       # Production frontend
        "https://auth.ticker-stream.com",  # Production backend
        "http://localhost:4200",           # Local development
        "http://127.0.0.1:4200",           # Local development loopback
        "http://100.85.77.37",             # Tailscale IP
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
        
    except PyJWTError as e:
        print(f"--- JWT DECODE ERROR: {e} ---")
        raise credentials_exception
    
    return {"username": username, "user_id": user_id}

# --- 1. Helper function to execute trades (Logic moved out of API endpoint) ---
def process_trade(user_id: int, ticker: str, action: str, quantity: int, price: float, is_bot_trade: bool):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Validation: Don't process empty trades
    if quantity <= 0:
        conn.close()
        return {"error": "Quantity must be greater than 0"}
    
    # Check balance for BUY
    if action.upper() == "BUY":
        cost = quantity * price
        cursor.execute("SELECT balance FROM portfolios WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row or row['balance'] < cost:
            conn.close()
            return {"error": "Insufficient funds"}

    # Record the trade
    cursor.execute(
        "INSERT INTO trades (user_id, ticker, action, quantity, price, is_bot_trade) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, ticker.upper(), action, quantity, price, is_bot_trade)
    )

    # Update Portfolio
    if action.upper() == "BUY":
        cost = quantity * price
        cursor.execute("UPDATE portfolios SET balance = balance - ? WHERE user_id = ?", (cost, user_id))
        cursor.execute(
            "INSERT INTO holdings (user_id, ticker, quantity, purchase_price) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id, ticker) DO UPDATE SET quantity = quantity + excluded.quantity",
            (user_id, ticker.upper(), quantity, price)
        )
    elif action.upper() == "SELL":
        proceeds = quantity * price
        cursor.execute("UPDATE portfolios SET balance = balance + ? WHERE user_id = ?", (proceeds, user_id))
        cursor.execute("UPDATE holdings SET quantity = quantity - ? WHERE user_id = ? AND ticker = ?",
                       (quantity, user_id, ticker.upper()))
        cursor.execute("DELETE FROM holdings WHERE user_id = ? AND ticker = ? AND quantity <= 0",
                       (user_id, ticker.upper()))

    conn.commit()
    conn.close()
    return {"message": "Trade processed successfully"}

# --- 2. The Background Loop ---
async def run_trading_bot():
    """
    Infinite loop that acts as the bot.
    """
    BOT_USER_ID = 11  # The user ID the bot trades for
    await asyncio.sleep(5)  # Wait for DB to initialize
    print("--- Trading Bot Activated ---")

    MARKET_OPEN = time(9, 30)
    MARKET_CLOSE = time(16, 0)
    NY_TZ = ZoneInfo("America/New_York")

    
    
    # 1. Start with your hardcoded or config defaults
    WATCHLIST = ["AAPL", "MSFT", "GOOG", "TSLA", "NVDA"]

    # 2. FETCH ADDITIONAL TICKERS FROM DB (e.g. from Holdings)
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Example: Get all tickers currently in your holdings
    cursor.execute("SELECT DISTINCT ticker FROM holdings WHERE user_id = ?", (BOT_USER_ID,))
    rows = cursor.fetchall()
    
    # --- THE FIX IS HERE ---
    # Extract the 'ticker' string from each row object
    held_tickers = [row['ticker'] for row in rows]
    
    conn.close()

    # 3. Merge lists and remove duplicates
    # set() removes duplicates, list() converts it back to a clean array
    FULL_WATCHLIST = list(set(WATCHLIST + held_tickers))

    print(f"Bot Watchlist: {FULL_WATCHLIST}") 
    # Output will now be: ['AAPL', 'MSFT', 'DG', 'RCL']

    ALLOCATION_PCT = 0.50
    TRADE_QTY = 1

    while True:
        try:
           # 1. Check the Switch
            if not BOT_ACTIVE:
                # If off, sleep and check again later
                await asyncio.sleep(5) 
                continue

            # 2. Check Market Hours
            now = datetime.now(NY_TZ)
            is_weekday = now.weekday() < 5 # 0=Mon, 4=Fri
            is_market_open = MARKET_OPEN <= now.time() <= MARKET_CLOSE

            if not (is_weekday and is_market_open):
                print(f"Bot: Market closed ({now.strftime('%H:%M')}). Sleeping...")
                # Sleep for 5 minutes instead of 1 minute to save resources
                await asyncio.sleep(300) 
                continue

            # Iterate through each stock in the watchlist
            for ticker in FULL_WATCHLIST:
                print(f"Bot: Analyzing {ticker}...")

                # 1. Get Market Data
                market_data = get_full_market_data(ticker)
                if not market_data:
                    print(f"Bot: No data for {ticker}. Skipping.")
                    continue
                
                # 2. Get User State
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT balance FROM portfolios WHERE user_id = ?", (BOT_USER_ID,))
                portfolio = cursor.fetchone()
                
                cursor.execute("SELECT quantity FROM holdings WHERE user_id = ? AND ticker = ?", (BOT_USER_ID, ticker))
                holding = cursor.fetchone()
                conn.close()

                balance = portfolio['balance'] if portfolio else 0.0
                shares_held = holding['quantity'] if holding else 0
                current_price = market_data['Close']

                # 3. Get AI Decision
                decision_result = get_bot_decision(balance, shares_held, market_data)
                decision = decision_result.get("decision")
                
                # 4. Calculate Quantity (The "How Much" Logic)
                trade_qty = 0

                if decision == "BUY":
                    # Simple Logic: Use ALLOCATION_PCT of available cash
                    investable_amount = balance * ALLOCATION_PCT
                    trade_qty = math.floor(investable_amount / current_price)
                    
                    # If we can't afford allocation but have *some* money, try to buy 1 share
                    if trade_qty == 0 and balance > current_price:
                        trade_qty = 1
                        
                elif decision == "SELL":
                    # Logic: Sell EVERYTHING we hold
                    trade_qty = shares_held

                print(f"Bot: {ticker} -> {decision} | Shares: {shares_held} | Qty to Trade: {trade_qty}")

                # 5. Execute Trade
                if trade_qty > 0:
                    result = process_trade(BOT_USER_ID, ticker, decision, trade_qty, current_price, True)
                    if "error" in result:
                        print(f"Bot Trade Error ({ticker}): {result['error']}")
                    else:
                        print(f"Bot Trade Executed: {result['message']}")
                
                # Small delay between tickers to be polite to the API
                await asyncio.sleep(2)
            
        except Exception as e:
            print(f"Bot Error: {e}")
        
        # Sleep for 150 seconds before next check
        await asyncio.sleep(150)

@app.on_event("startup")
def on_startup():
    setup_database()
    asyncio.create_task(run_trading_bot())

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

@app.get("/api/stock/{ticker}/history")
def get_stock_history(ticker: str, period: str):
    period_map = {
        "1D": "1d",
        "1W": "5d",
        "1M": "1mo",
        "1Y": "1y",
        "5Y": "5y",
        "ALL": "max"
    }

    yf_period = period_map.get(period, "1mo")
    return get_historical_data(ticker.upper(), yf_period)


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


# --- Bot Control Endpoints (Connected to BotStatusService) ---

@app.get("/api/bot/status")
def get_bot_status(current_user: dict = Depends(get_current_user)):
    status_str = "active" if BOT_ACTIVE else "inactive"
    return {"status": status_str, "message": f"Bot is {status_str}"}

@app.post("/api/bot/start")
def start_bot(current_user: dict = Depends(get_current_user)):
    global BOT_ACTIVE
    BOT_ACTIVE = True
    print(f"Bot started by user {current_user['username']}")
    return {"status": "active", "message": "Bot started successfully"}

@app.post("/api/bot/stop")
def stop_bot(current_user: dict = Depends(get_current_user)):
    global BOT_ACTIVE
    BOT_ACTIVE = False
    print(f"Bot stopped by user {current_user['username']}")
    return {"status": "inactive", "message": "Bot stopped successfully"}

# Manual Trigger for Testing (Optional)
@app.post("/api/bot/decision")
def make_decision(state: PortfolioState, current_user: dict = Depends(get_current_user)):
    try:
        market_data = get_full_market_data("AAPL")
        decision_result = get_bot_decision(state.balance, state.shares_held, market_data)
        if "error" in decision_result:
            raise HTTPException(status_code=500, detail=decision_result["error"])
        return decision_result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")