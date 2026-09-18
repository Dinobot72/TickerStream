from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db_connection
from app.routers.auth import get_current_user
from app.services.market_data import get_stock_price, get_stock_metrics, get_historical_data, get_full_market_data, screen_stock_gainers, get_stock_info
from app.services.risk_manager import RiskManager
from app.services.broker import (
    BrokerError,
    BrokerRejected,
    get_broker_for_user,
    sync_portfolio_from_broker,
)
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
    """Execute one trade for a user.

    Two execution paths share this entry point so callers (the manual /api/trade/
    endpoint and the bot scheduler) do not need to know which is in play:

      1. BROKER  — the user has an enabled Alpaca link. The order goes to Alpaca
                   and the local `trades` row records the broker's order id and
                   real fill price. Local `portfolios`/`holdings` are then
                   re-synced from Alpaca, which is authoritative.

      2. SIMULATED — no linked account. The original local-ledger behaviour,
                   preserved so users who never link a brokerage are unaffected.

    `price` is the app's quote at decision time. For broker orders it is only an
    estimate used for pre-trade risk checks; the recorded price is whatever
    Alpaca actually fills at.
    """
    action = action.upper()
    ticker = ticker.upper()

    if quantity <= 0:
        return {"error": "Quantity must be > 0"}

    # --- Risk Check (applies to both paths) ---
    risk_manager = RiskManager(user_id)
    allowed, message = risk_manager.can_trade(ticker, action, price, quantity)
    if not allowed:
        return {"error": message}

    # --- Path selection ---
    # A raised BrokerError here means the user HAS a link that cannot be used
    # right now. That is surfaced as an error rather than silently simulated:
    # executing a fake trade while the user believes it is real is the single
    # worst outcome this module can produce.
    try:
        broker = get_broker_for_user(user_id, is_bot_trade=is_bot_trade)
    except BrokerError as exc:
        return {"error": str(exc)}

    if broker is not None:
        return _process_broker_trade(broker, user_id, ticker, action, quantity, price, is_bot_trade)

    return _process_simulated_trade(user_id, ticker, action, quantity, price, is_bot_trade)


def _process_broker_trade(broker, user_id, ticker, action, quantity, price, is_bot_trade):
    """Submit to Alpaca, record the resulting trade, then re-sync local state."""
    mode = "live" if not broker.paper else "paper"

    try:
        result = broker.submit_order(ticker=ticker, action=action, quantity=quantity)
    except BrokerRejected as exc:
        # Includes the oversell case: Alpaca knows the true position and refuses.
        return {"error": f"Order rejected by broker: {exc}"}
    except BrokerError as exc:
        return {"error": str(exc)}

    if result.status == "REJECTED":
        return {"error": f"Order rejected by broker (status: {result.raw_status})"}

    # Record the broker's real fill price, but only once shares have actually
    # filled. A working order has no meaningful execution price, so the row keeps
    # the decision-time quote as a placeholder until reconcile_open_orders()
    # overwrites it — that way the price column is never NULL and never shows a
    # fill that has not happened.
    has_fill = result.filled_qty > 0 and result.filled_avg_price is not None
    recorded_price = result.filled_avg_price if has_fill else price
    recorded_qty = result.filled_qty if result.filled_qty else quantity

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO trades
                (user_id, ticker, action, quantity, price, is_bot_trade,
                 broker_order_id, status, mode, filled_qty, filled_avg_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, ticker, action, recorded_qty, recorded_price, is_bot_trade,
                result.broker_order_id, result.status, mode,
                result.filled_qty, result.filled_avg_price,
            ),
        )
        conn.commit()
        trade_id = cursor.lastrowid
    finally:
        conn.close()

    # Alpaca owns the truth about cash and positions — pull it back down so the
    # portfolio UI and the model's next observation see real numbers.
    sync_error = None
    if result.status in ("FILLED", "PARTIAL"):
        try:
            sync_portfolio_from_broker(user_id)
        except BrokerError as exc:
            # The order went through; only the cache refresh failed. Report it
            # without pretending the trade itself failed.
            sync_error = str(exc)

    response = {
        "message": f"Order {result.status.lower()} via broker ({mode})",
        "trade_id": trade_id,
        "status": result.status,
        "mode": mode,
        "broker_order_id": result.broker_order_id,
        "filled_qty": result.filled_qty,
        "filled_avg_price": result.filled_avg_price,
    }
    if result.status == "PENDING":
        response["message"] = (
            f"Order accepted by broker ({mode}) and is working. "
            "It will be reconciled once it fills — typically at the next market open."
        )
    if sync_error:
        response["warning"] = f"Order placed, but portfolio sync failed: {sync_error}"

    return response


def _process_simulated_trade(user_id, ticker, action, quantity, price, is_bot_trade):
    """Original local-ledger execution, for users with no linked brokerage."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        if action == "BUY":
            cost = quantity * price
            cursor.execute("SELECT balance FROM portfolios WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row or row["balance"] < cost:
                return {"error": "Insufficient funds"}

        elif action == "SELL":
            # Verify the position exists and is large enough BEFORE crediting cash.
            # Without this the ledger would credit proceeds for shares the user
            # never held and drive `holdings.quantity` negative — i.e. a bad signal
            # could mint money in the simulated account. The broker path gets this
            # for free because Alpaca rejects the oversell itself.
            cursor.execute(
                "SELECT quantity FROM holdings WHERE user_id = ? AND ticker = ?",
                (user_id, ticker),
            )
            holding = cursor.fetchone()
            held = holding["quantity"] if holding else 0
            if held < quantity:
                return {
                    "error": f"Insufficient shares: holding {held} {ticker}, tried to sell {quantity}"
                }

        cursor.execute(
            """
            INSERT INTO trades
                (user_id, ticker, action, quantity, price, is_bot_trade, status, mode)
            VALUES (?, ?, ?, ?, ?, ?, 'FILLED', 'simulated')
            """,
            (user_id, ticker, action, quantity, price, is_bot_trade),
        )
        trade_id = cursor.lastrowid

        if action == "BUY":
            cost = quantity * price
            cursor.execute(
                "UPDATE portfolios SET balance = balance - ? WHERE user_id = ?", (cost, user_id)
            )
            cursor.execute(
                "INSERT INTO holdings (user_id, ticker, quantity, purchase_price) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(user_id, ticker) DO UPDATE SET "
                "quantity = quantity + excluded.quantity",
                (user_id, ticker, quantity, price),
            )
        elif action == "SELL":
            proceeds = quantity * price
            cursor.execute(
                "UPDATE portfolios SET balance = balance + ? WHERE user_id = ?", (proceeds, user_id)
            )
            cursor.execute(
                "UPDATE holdings SET quantity = quantity - ? WHERE user_id = ? AND ticker = ?",
                (quantity, user_id, ticker),
            )
            cursor.execute(
                "DELETE FROM holdings WHERE user_id = ? AND ticker = ? AND quantity <= 0",
                (user_id, ticker),
            )

        conn.commit()
    finally:
        conn.close()

    return {
        "message": "Trade processed",
        "trade_id": trade_id,
        "status": "FILLED",
        "mode": "simulated",
    }

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
    run_market_scan()  # Ensure the bot has a fresh scan before starting
    return {"status": "active", "message": "Bot started"}

@router.post("/api/bot/stop")
def stop_bot(current_user: dict = Depends(get_current_user)):
    set_bot_active(current_user["user_id"], False)
    return {"status": "inactive", "message": "Bot stopped"}