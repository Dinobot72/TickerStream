from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db_connection
from app.routers.auth import get_current_user
from app.services.market_data import get_stock_price, get_stock_metrics, get_historical_data, get_full_market_data, screen_stock_gainers, get_stock_info
from app.services.risk_manager import RiskManager
from app.core.bot_state import is_bot_active, set_bot_active


router = APIRouter()

class Trade(BaseModel):
    user_id: int
    ticker: str
    action: str
    quantity: int
    price: float
    is_bot_trade: bool = False

class PortfolioState(BaseModel):
    balance: float
    shares_held: int

# --- Helper Logic (Also used by Scheduler) ---
def process_trade(user_id: int, ticker: str, action: str, quantity: int, price: float, is_bot_trade: bool):
    # --- Risk Check ---
    risk_manager = RiskManager(user_id)
    allowed, message = risk_manager.can_trade(ticker, action, price, quantity)
    if not allowed:
        return {"error": message}
    
    # --- AI Prediction ---
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if quantity <= 0:
        conn.close()
        return {"error": "Quantity must be > 0"}

    # Balance Check
    if action.upper() == "BUY":
        cost = quantity * price
        cursor.execute("SELECT balance FROM portfolios WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row or row['balance'] < cost:
            conn.close()
            return {"error": "Insufficient funds"}
    
    # Record Trade
    cursor.execute("INSERT INTO trades (user_id, ticker, action, quantity, price, is_bot_trade) VALUES (?, ?, ?, ?, ?, ?)",
                   (user_id, ticker.upper(), action, quantity, price, is_bot_trade))

    # Update Portfolio
    if action.upper() == "BUY":
        cost = quantity * price
        cursor.execute("UPDATE portfolios SET balance = balance - ? WHERE user_id = ?", (cost, user_id))
        cursor.execute("INSERT INTO holdings (user_id, ticker, quantity, purchase_price) VALUES (?, ?, ?, ?) ON CONFLICT(user_id, ticker) DO UPDATE SET quantity = quantity + excluded.quantity", (user_id, ticker.upper(), quantity, price))
    elif action.upper() == "SELL":
        proceeds = quantity * price
        cursor.execute("UPDATE portfolios SET balance = balance + ? WHERE user_id = ?", (proceeds, user_id))
        cursor.execute("UPDATE holdings SET quantity = quantity - ? WHERE user_id = ? AND ticker = ?", (quantity, user_id, ticker.upper()))
        cursor.execute("DELETE FROM holdings WHERE user_id = ? AND ticker = ? AND quantity <= 0", (user_id, ticker.upper()))

    conn.commit()
    conn.close()
    return {"message": "Trade processed"}

# --- Routes ---
@router.post("/api/trade/")
def execute_trade(trade: Trade, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != trade.user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    result = process_trade(trade.user_id, trade.ticker, trade.action, trade.quantity, trade.price, trade.is_bot_trade)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.get("/api/stock/{ticker}")
def get_stock_chart(ticker: str):
    return get_stock_price(ticker.upper())

@router.get("/api/stock/{ticker}/history")
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

@router.get("/api/market/gainers")
def get_stock_gainers():
    return screen_stock_gainers("day_gainers")

@router.get("/api/market/losers")
def get_stock_losers():
    return screen_stock_gainers("day_losers")

@router.get("/api/metrics/{ticker}")
def get_metrics(ticker: str):
    return get_stock_metrics(ticker.upper())

@router.get("/api/change/{ticker}")
def get_change_info(ticker: str):
    stock_info = get_stock_info(ticker.upper())
    # Use .get() to prevent KeyErrors if yfinance returns an empty/incomplete dict
    info = {
        "change_pct": stock_info.get('regularMarketChangePercent', 0.0),
        "change_amt": stock_info.get('regularMarketChange', 0.0),
    }

    return info

# --- Bot Controls ---
@router.get("/api/bot/status")
def get_status(current_user: dict = Depends(get_current_user)):
    active = is_bot_active(current_user["user_id"])
    return {"status": "active" if active else "inactive"}

@router.post("/api/bot/start")
def start_bot(current_user: dict = Depends(get_current_user)):
    set_bot_active(current_user["user_id"], True)
    return {"status": "active", "message": "Bot started"}

@router.post("/api/bot/stop")
def stop_bot(current_user: dict = Depends(get_current_user)):
    set_bot_active(current_user["user_id"], False)
    return {"status": "inactive", "message": "Bot stopped"}