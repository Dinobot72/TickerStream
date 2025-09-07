import yfinance as yf
from datetime import datetime, timedelta
import pandas as pd

def get_stock_data(ticker: str):
    stock = yf.Ticker(ticker)

    hist_data = stock.history(period="7d", interval="1m")

    formatted_data = []
    for index, row in hist_data.iterrows():
        formatted_data.append({
            "timestamp": index.timestamp(),
            "open": row['Open'],
            "high": row['High'],
            "low": row['Low'],
            "close": row['Close'],
            "volume": row['Volume']
        })
    return formatted_data

def get_stock_metrics(ticker: str):
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