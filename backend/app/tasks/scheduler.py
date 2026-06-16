import asyncio
import math
from datetime import datetime, time
from zoneinfo import ZoneInfo
from app.core.database import get_db_connection
from app.core.config import bot_state
from app.services.market_data import get_full_market_data
# Import process_trade. 
# Note: In a larger app, we'd move process_trade to a 'services' file to avoid importing from 'routers'
from app.routers.trading import process_trade
from app.services.screener import run_market_scan 
from app.services.portfolio_manager import PortfolioManager

async def run_trading_bot():
    """
    Infinite loop for the bot.
    """
    
    print("--- Background Trading Bot Initialized ---")

    BOT_USER_ID = 11
    portfolio_mgr = PortfolioManager(
        user_id=BOT_USER_ID, 
        model_path="../model/logs/best_model/best_model",
        db_path="./tickerstream.db"
    )
    # Time Zone Configuration
    NY_TZ = ZoneInfo("America/New_York")

    # Run Initial Scan on Startup
    active_tickers = run_market_scan()

    while True:
        try:
            # 1. Check Global Switch
            if not bot_state.is_active:
                await asyncio.sleep(5)
                continue

            # 2. Check Market Hours (Simplified)
            now = datetime.now(NY_TZ)
            if not (9 <= now.hour < 16 and now.weekday() < 5):
                print("Market Closed. Sleeping...")
                await asyncio.sleep(300)
                continue
            
            # Refresh scan every 60 minutes
            if datetime.now().minute == 0:
               active_tickers = run_market_scan()

            # 3. Build Watchlist
            # conn = get_db_connection()
            # cursor = conn.cursor()
            # cursor.execute("SELECT DISTINCT ticker FROM holdings WHERE user_id = ?", (BOT_USER_ID,))
            # held = [r['ticker'] for r in cursor.fetchall()]
            # conn.close()
            trades = portfolio_mgr.generate_trade_plan(
                max_positions=5,
                min_buy_confidence=0.65,
                min_sell_confidence=0.60
            )

            # active_tickers = list(active_tickers + held)

            # 4. Execute each trade
            for trade in trades:
                ticker = trade['ticker']
                action = trade['action']
                qty = trade['quantity']
                price = trade['price']
                
                print(f"🤖 BOT: {action} {qty} {ticker} @ ${price:.2f}")
                print(f"    Reason: {trade['reason']}")
                
                process_trade(BOT_USER_ID, ticker, action, qty, price, True)
                await asyncio.sleep(2)  # Rate limiting

        except Exception as e:
            print(f"Bot Loop Error: {e}")
        
        await asyncio.sleep(300) # Run every minute