from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict
from pydantic import BaseModel

from app.core.database import get_db_connection
from app.routers.auth import get_current_user

router = APIRouter()

class Deposit(BaseModel):
    amount: float

class WatchlistAdd(BaseModel):
    ticker: str

@router.get("/api/user/{user_id}")
def get_user_info( user_id: int, current_user: dict = Depends(get_current_user)):
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
    return dict(user)

@router.post("/api/user/{user_id}/deposit")
def deposit(user_id: int, data: Deposit, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE portfolios SET balance = balance + ? WHERE user_id = ?", (data.amount, user_id))
    conn.commit()
    
    cursor.execute("SELECT balance FROM portfolios WHERE user_id = ?", (user_id,))
    new_bal = cursor.fetchone()['balance']
    conn.close()
    return {"message": "Deposit successful", "new_balance": new_bal}

@router.get("/api/holdings/{user_id}")
def get_holdings(user_id: int, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ticker, quantity, purchase_price FROM holdings WHERE user_id=? AND quantity > 0", (user_id,))
    data = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return data

@router.get("/api/activity/{user_id}")
def get_activity(user_id: int, limit: int = 10, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT action, ticker, quantity, price, timestamp, is_bot_trade FROM trades WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?", (user_id, limit))
    data = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return data

@router.get("/api/watchlist/{user_id}")
def get_watchlist(user_id: int, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ticker, added_at FROM watchlist WHERE user_id=?", (user_id,))
    data = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return data

@router.post("/api/watchlist/{user_id}")
def add_watchlist(user_id: int, item: WatchlistAdd, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    ticker = item.ticker.upper()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO watchlist (user_id, ticker) VALUES (?, ?)", (user_id, ticker))
        conn.commit()
    except:
        conn.close()
        return {"message": "Already in watchlist"}
    conn.close()
    return {"message": "Added to watchlist"}

@router.delete("/api/watchlist/{user_id}/{ticker}")
def remove_watchlist(user_id: int, ticker: str, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (user_id, ticker.upper()))
    conn.commit()
    conn.close()
    return {"message": "Removed from watchlist"}

@router.get("/api/user/{user_id}/portfolio")
def get_portfolio_balance(user_id: int, current_user: dict = Depends(get_current_user)):
    '''
    Returns the current balance of the user's portfolio.

    Parameters:
    user_id (int): the id of the user to get the portfolio balance for
    current_user (dict): the current user using the app

    Returns:
    balance (float): the current balance of the user's portfolio
    '''
    if current_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM portfolios WHERE user_id = ?", (user_id,))
    balance = cursor.fetchone()['balance']
    conn.commit()
    conn.close()
    return {"balance": balance}