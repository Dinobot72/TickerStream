from apscheduler.schedulers.background import BackgroundScheduler
from backend.app.services.screener import run_market_scan
from app.services.ai_bridge import predict_action
from app.core.database import get_db_connection

def automated_trading_job():
    print("Trading Agent Activated")

    # Screen Market
    tickers = run_market_scan()

    # Loop and Trade
    for t in tickers:
        # Predict actions
        predict_action(t)

        # execute SQL queries

        pass


def start_scheduler():
    scheduler = BackgroundScheduler()
    # Run automated_trading_job every 60 minutes
    scheduler.add_job(automated_trading_job, 'interval', minutes=60)
    scheduler.start()
