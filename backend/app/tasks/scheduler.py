import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.database import get_db_connection
from app.services.market_data import get_full_market_data
from app.routers.trading import process_trade
from app.services.screener import run_market_scan 
from app.services.portfolio_manager import PortfolioManager
from app.core.bot_state import get_active_bot_user_ids
from app.services.ai_scorer import AIScorer

# How often the main loop runs (seconds). 300 = every 5 minutes.
BOT_LOOP_INTERVAL = 300
# How often to refresh the market scan (minutes)
SCAN_REFRESH_INTERVAL_MINUTES = 60
# Path to the shared RL model — loaded ONCE, not per user.
MODEL_PATH = "../model/logs/best_model/best_model"

async def run_trading_bot():
    """
    Infinite loop for the bot. Trades every user who currently has the bot
    switched on (see bot_state.get_active_bot_user_ids()) — not tied to any
    single hardcoded account, and independent of whether that user has an
    active browser session at the time.
    """
    
    print("--- Background Trading Bot Initialized ---")

    # Load the RL model ONCE and share it across every user's PortfolioManager.
    # Loading it per-user would be slow and wasteful since it's the same weights;
    # AIScorer keys its LSTM state internally so sharing it is safe.
    shared_scorer = AIScorer(MODEL_PATH)

    # One PortfolioManager per active user, created lazily and cached across
    # loop iterations. Dropped again once a user turns their bot off, so a
    # future re-enable starts with clean LSTM state instead of stale state.
    portfolio_managers: dict[int, PortfolioManager] = {}

    # Time Zone Configuration
    NY_TZ = ZoneInfo("America/New_York")
    last_scan_hour = -1  # Track the last hour we ran a market scan

    # Run initial scan on startup
    print("Running initial market scan...")
    run_market_scan()
    last_scan_hour = datetime.now(NY_TZ).hour

    while True:
        try:
            # 1. Check Global Switch
            active_user_ids = get_active_bot_user_ids()

            if not active_user_ids:
                await asyncio.sleep(5)
                continue

            # 2. Check Market Hours (Simplified)
            now = datetime.now(NY_TZ)
            market_open = (
                now.weekday() < 5
                and (now.hour > 9 or (now.hour == 9 and now.minute >= 30))
                and now.hour < 16
            )
            if not market_open:
                print(f"Market closed ({now.strftime('%H:%M ET')}). Sleeping 5 min...")
                await asyncio.sleep(300)
                continue
            
            # 3. Refresh the shared market scan every SCAN_REFRESH_INTERVAL_MINUTES.
            # This also re-syncs every active user's bot_watchlist (see screener.py).
            if now.hour != last_scan_hour and now.minute < 5:
                print("Refreshing market scan...")
                run_market_scan()
                last_scan_hour = now.hour

            # 4. Generate and execute trade plan
            # against their own portfolio and their own merged candidate list
            # (bot_watchlist + personal watchlist).
            for user_id in active_user_ids:
                if user_id not in portfolio_managers:
                    portfolio_managers[user_id] = PortfolioManager(
                        user_id=user_id,
                        db_path="./tickerstream.db",
                        scorer=shared_scorer,
                    )
                portfolio_mgr = portfolio_managers[user_id]

                
                trades = portfolio_mgr.generate_trade_plan(
                    max_positions=5,
                    min_buy_confidence=0.65,
                    min_sell_confidence=0.60,
                )

                # 5. Execute each trade
                for trade in trades:
                    ticker = trade['ticker']
                    action = trade['action']
                    qty = trade['quantity']
                    price = trade['price']
                    
                    print(f"🤖 BOT (user {user_id}): {action} {qty} {ticker} @ ${price:.2f}  |  {trade['reason']}")
                    result = process_trade(user_id, ticker, action, qty, price, is_bot_trade=True)
                    if "error" in result:
                        print(f"   ❌ Trade rejected: {result['error']}")
                    await asyncio.sleep(2)  # Avoid hammering the DB between trades

            # 6. Drop cached managers for users who turned the bot off since
            # the last cycle, so state doesn't linger forever in memory.
            for stale_user_id in [uid for uid in portfolio_managers if uid not in active_user_ids]:
                del portfolio_managers[stale_user_id]

        except Exception as e:
            print(f"Bot Loop Error: {e}")
        
        await asyncio.sleep(BOT_LOOP_INTERVAL)