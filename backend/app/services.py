import yfinance as yf
from datetime import datetime, timedelta
import pandas as pd

def get_stock_data(ticker: str):
    # stock = yf.Ticker(ticker)

    # hist_data = stock.history(period="7d", interval="1m")

    # formatted_data = []
    # for index, row in hist_data.iterrows():
    #     formatted_data.append({
    #         "timestamp": index.timestamp(),
    #         "open": row['Open'],
    #         "high": row['High'],
    #         "low": row['Low'],
    #         "close": row['Close'],
    #         "volume": row['Volume']
    #     })
    # return formatted_data
    """
    Fetches historical stock data for the given ticker from Yahoo Finance.
    """
    try:
        stock = yf.Ticker(ticker)
        # Get historical market data for the last day to get the latest close price
        hist = stock.history(period="1d")
        if not hist.empty:
            # Return the latest close price
            return {"latestPrice": hist['Close'].iloc[-1]}
        return {}
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return {}

def get_stock_metrics(ticker: str):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        metrics = {
            "market_cap": info.get('marketCap'),
            "pe_ratio": info.get('trailingPE'),
            "dividend_yield": info.get('dividendYield'),
            "volume": info.get('volume'),
            "52_week_high": info.get('fiftyTwoWeekHigh'),
            "52_week_low": info.get('fiftyTwoWeekLow'),
        }
        return metrics
    except Exception as e:
        print(f"Error fetching metrics for {ticker}: {e}")
        return {}