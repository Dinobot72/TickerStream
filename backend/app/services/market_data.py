import yfinance as yf
from yfinance import EquityQuery

def get_stock_price(ticker: str):
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
    """Fetch OHLC data for the AI Model."""
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

def get_stock_metrics(ticker: str):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        metrics = {
            "market_cap":     info.get('marketCap',          0),
            "pe_ratio":       info.get('trailingPE',         0),
            "dividend_yield": info.get('dividendYield',      0),
            "volume":         info.get('volume',             0),
            "52_week_high":   info.get('fiftyTwoWeekHigh',   0),
            "52_week_low":    info.get('fiftyTwoWeekLow',    0),
            "shortName":      info.get('shortName',          ''),
        }
        return metrics
    except Exception as e:
        print(f"Error fetching metrics for {ticker}: {e}")
        return {}

def get_historical_data(ticker: str, period: str):
    """Fetch history for charts."""
    interval_map = {
        "1d": "5m",   # 1 Day -> 5 minute intervals
        "5d": "15m",  # 1 Week -> 15 minute intervals
        "1mo": "1d",  # 1 Month -> Daily
        "6mo": "1d",
        "1y": "1wk",  # 1 Year -> Weekly
        "5y": "1mo",  # 5 Years -> Monthly
        "max": "1mo"
    }
    interval = interval_map.get(period, "1d")

    try:
        stock = yf.Ticker(ticker)

        hist = stock.history(period=period, interval=interval)

        data = []

        for index, row in hist.iterrows():
            price = row['Close']
            # Skip NaN rows — they cause json.dumps to raise ValueError
            if price != price:  # fastest NaN check (NaN != NaN is always True)
                continue
            data.append({"timestamp": index.isoformat(), "price": float(price)})
        return data
    except Exception as e:
        print(f"Error fetching history for {ticker}: {e}")
        return []
    
def screen_stock_gainers(query: str):
    results = yf.screen(query, size=5)
    gainers = []
    for stock in results['quotes'][:5]:  # Print the top 5
        gainers.append({
            "ticker": stock['symbol'],
            "price": stock['regularMarketPrice'],
            "changePct": stock['regularMarketChangePercent']
        })

    return gainers

def get_stock_info(stock: str):
    try:
        stock = yf.Ticker(stock)
        info = stock.info
        
        return info
    except Exception as e:
        print(f"Error fetching data for {stock}: {e}")
        return {}

if __name__ == "__main__":
    get_stock_info("AAPL")
    
