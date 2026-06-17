import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.database import get_db_connection
from app.core.config import bot_state, BOT_USER_ID
from app.services.market_data import get_full_market_data
from app.routers.trading import process_trade
from app.services.screener import run_market_scan 
from app.services.portfolio_manager import PortfolioManager

# How often the main loop runs (seconds). 300 = every 5 minutes.
BOT_LOOP_INTERVAL = 300
# How often to refresh the market scan (minutes)
SCAN_REFRESH_INTERVAL_MINUTES = 60

async def run_trading_bot():
    """
    Infinite loop for the bot.
    """
    
    print("--- Background Trading Bot Initialized ---")

    portfolio_mgr = PortfolioManager(
        user_id=BOT_USER_ID, 
        model_path="../model/logs/best_model/best_model",
        db_path="./tickerstream.db"
    )
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
            if not bot_state.is_active:
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
            
            # 3. Refresh the watchlist every SCAN_REFRESH_INTERVAL_MINUTES
            if now.hour != last_scan_hour and now.minute < 5:
                print("Refreshing market scan...")
                run_market_scan()
                last_scan_hour = now.hour

            # 4. Generate and execute trade plan
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
                
                print(f"🤖 BOT: {action} {qty} {ticker} @ ${price:.2f}  |  {trade['reason']}")
                result = process_trade(BOT_USER_ID, ticker, action, qty, price, is_bot_trade=True)
                if "error" in result:
                    print(f"   ❌ Trade rejected: {result['error']}")
                await asyncio.sleep(2)  # Avoid hammering the DB between trades

        except Exception as e:
            print(f"Bot Loop Error: {e}")
        
        await asyncio.sleep(BOT_LOOP_INTERVAL)