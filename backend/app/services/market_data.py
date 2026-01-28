import yfinance as yf

def get_stock_data(ticker: str):
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

def get_full_market_data(ticker: str):
    """
    Fetches the latest OHLC data for the bot's strategy engine.
    """
    try:
        stock = yf.Ticker(ticker)
        # Fetch 1 day of data to ensure we get the latest candle
        hist = stock.history(period="1d", interval="1d") 
        if not hist.empty:
            latest = hist.iloc[-1]
            return {
                "Open": float(latest['Open']),
                "High": float(latest['High']),
                "Low": float(latest['Low']),
                "Close": float(latest['Close'])
            }
        return None
    except Exception as e:
        print(f"Error fetching full market data for {ticker}: {e}")
        return None