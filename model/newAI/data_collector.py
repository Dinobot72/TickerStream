import os
import time
import pandas as pd
import requests
import yfinance as yf
from data_prep import prepare_ticker_data  # we already wrote this

# Configuration
UNIVERSE_FILE = "model/universe.csv"
DATA_DIR = "model/data/train"
MACRO_DIR = os.path.join(DATA_DIR, "macro")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(MACRO_DIR, exist_ok=True)

MACRO_TICKERS = ["SPY", "QQQ", "IWM", "VIX"]

def load_universe():
    """Load ticker list from CSV. If missing, fetch S&P 500 from Wikipedia with proper headers."""
    if os.path.exists(UNIVERSE_FILE):
        df = pd.read_csv(UNIVERSE_FILE)
        return df['ticker'].tolist()
    else:
        print("Universe file not found. Fetching current S&P 500 tickers from Wikipedia...")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            tables = pd.read_html(response.text)
            sp500 = tables[0]  # first table is the company list
            tickers = sp500['Symbol'].tolist()
            # yfinance uses dashes instead of dots (e.g., BRK.B -> BRK-B)
            tickers = [t.replace('.', '-') for t in tickers]
            # Save to CSV for future runs
            pd.DataFrame({'ticker': tickers}).to_csv(UNIVERSE_FILE, index=False)
            print(f"Saved {len(tickers)} tickers to {UNIVERSE_FILE}")
            return tickers
        except Exception as e:
            print(f"Error fetching Wikipedia: {e}")
            # Fallback to a small default list
            print("Using fallback ticker list.")
            return ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "JPM", "V", "JNJ"]

def collect_ticker_data(ticker):
    """Fetch and save data for a single ticker."""
    print(f"Processing {ticker}...")
    try:
        df = prepare_ticker_data(ticker, period="10y")
        if df.empty:
            print(f"No data for {ticker}, skipping.")
            return
        # Save to parquet
        df.to_parquet(os.path.join(DATA_DIR, f"{ticker}.parquet"))
        print(f"Saved {ticker} with {len(df)} rows.")
    except Exception as e:
        print(f"Error with {ticker}: {e}")

def collect_macro_data():
    """Fetch macro tickers (SPY, VIX) and save."""
    for ticker in MACRO_TICKERS:
        print(f"Processing macro {ticker}...")
        try:
            df = prepare_ticker_data(ticker, period="10y")
            if df.empty:
                continue
            df.to_parquet(os.path.join(MACRO_DIR, f"{ticker}.parquet"))
            print(f"Saved macro {ticker}.")
        except Exception as e:
            print(f"Error with macro {ticker}: {e}")

if __name__ == "__main__":
    universe = load_universe()
    print(f"Universe size: {len(universe)} tickers")
    # For testing, you may limit the number of tickers:
    # universe = universe[:20]
    for i, ticker in enumerate(universe):
        collect_ticker_data(ticker)
        # Be nice to Yahoo's servers
        time.sleep(0.5)
        # Optional: print progress every 50 tickers
        if (i+1) % 50 == 0:
            print(f"Progress: {i+1}/{len(universe)} tickers processed")

    collect_macro_data()
    print("Data collection complete.")