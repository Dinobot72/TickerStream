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

def get_stock_metrics(ticker: str):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        metrics = {
            "market_cap": f"{info.get('marketCap'):,.2f}",
            "pe_ratio": f"{info.get('trailingPE'):,.2f}",
            "dividend_yield": f"{info.get('dividendYield'):,}",
            "volume": f"{info.get('volume'):,.2f}",
            "52_week_high": info.get('fiftyTwoWeekHigh'),
            "52_week_low": info.get('fiftyTwoWeekLow'),
        }
        return metrics
    except Exception as e:
        print(f"Error fetching metrics for {ticker}: {e}")
        return {}