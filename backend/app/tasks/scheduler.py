import asyncio
import math
from datetime import datetime, time
from zoneinfo import ZoneInfo
from app.core.database import get_db_connection
from app.core.config import bot_state
from app.services.market_data import get_full_market_data
from app.services.ai_bridge import predict_action
# Import process_trade. 
# Note: In a larger app, we'd move process_trade to a 'services' file to avoid importing from 'routers'
from app.routers.trading import process_trade
from app.services.screener import run_market_scan 

async def run_trading_bot():
    """
    Infinite loop for the bot.
    """
    
    print("--- Background Trading Bot Initialized ---")

    BOT_USER_ID = 11
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
            # now = datetime.now(NY_TZ)
            # if not (9 <= now.hour < 16 and now.weekday() < 5):
            #     print("Market Closed. Sleeping...")
            #     await asyncio.sleep(300)
            #     continue
            
            # Refresh scan every 60 minutes
            if datetime.now().minute == 0:
               active_tickers = run_market_scan()

            # 3. Build Watchlist
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT ticker FROM holdings WHERE user_id = ?", (BOT_USER_ID,))
            held = [r['ticker'] for r in cursor.fetchall()]
            conn.close()

            active_tickers = list(active_tickers + held)

            # 4. Trade Loop
            for ticker in active_tickers:
                data = get_full_market_data(ticker)
                if not data: continue

                # Get Balance
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT balance FROM portfolios WHERE user_id = ?", (BOT_USER_ID,))
                res = cursor.fetchone()
                balance = res['balance'] if res else 0
                
                cursor.execute("SELECT quantity FROM holdings WHERE user_id=? AND ticker=?", (BOT_USER_ID, ticker))
                h_res = cursor.fetchone()
                shares = h_res['quantity'] if h_res else 0
                conn.close()

                # AI Decision
                decision_result = predict_action(balance, shares, data)
                action = decision_result.get("decision")
                price = data['Close']
                
                qty = 0
                if action == "BUY":
                    invest_amt = balance * 0.50
                    qty = math.floor(invest_amt / price)
                    if qty == 0 and balance > price: qty = 1
                elif action == "SELL":
                    qty = shares
                
                if qty > 0:
                    print(f"BOT EXECUTE: {action} {qty} {ticker}")
                    process_trade(BOT_USER_ID, ticker, action, qty, price, True)

                await asyncio.sleep(2) # Pace the api calls

        except Exception as e:
            print(f"Bot Loop Error: {e}")
        
        await asyncio.sleep(60) # Run every minute