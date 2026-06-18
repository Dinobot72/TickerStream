import math
import yfinance as yf
from yfinance import EquityQuery


def _safe_float(value, fallback=0.0) -> float:
    """Return fallback if value is None, NaN, or infinite."""
    try:
        f = float(value)
        return fallback if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return fallback


def get_stock_price(ticker: str):
    try:
        hist = yf.Ticker(ticker).history(period="1d")
        if not hist.empty:
            price = hist['Close'].iloc[-1]
            return {"latestPrice": _safe_float(price)}
        return {}
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return {}


def get_full_market_data(ticker: str):
    """Fetch OHLC data for the AI Model."""
    try:
        hist = yf.Ticker(ticker).history(period="1d", interval="1d")
        if not hist.empty:
            latest = hist.iloc[-1]
            return {
                "Open":  _safe_float(latest['Open']),
                "High":  _safe_float(latest['High']),
                "Low":   _safe_float(latest['Low']),
                "Close": _safe_float(latest['Close']),
            }
        return None
    except Exception as e:
        print(f"Error fetching full market data for {ticker}: {e}")
        return None


def get_stock_metrics(ticker: str):
    """
    FIX: Use .get() for every field instead of hard key access.
    'trailingPE' and 'dividendYield' are absent for many stocks (ETFs, growth
    companies, etc.) and previously caused a KeyError that crashed the endpoint,
    returning an empty {} that broke the watchlist company-name and volume columns.
    Also adds 'shortName' which the watchlist component needs for the name column.
    """
    try:
        info = yf.Ticker(ticker).info
        return {
            "market_cap":     info.get('marketCap',        0) or 0,
            "pe_ratio":       info.get('trailingPE',        0) or 0,
            "dividend_yield": info.get('dividendYield',     0) or 0,
            "volume":         info.get('volume',            0) or 0,
            "52_week_high":   info.get('fiftyTwoWeekHigh',  0) or 0,
            "52_week_low":    info.get('fiftyTwoWeekLow',   0) or 0,
            "shortName":      info.get('shortName',        ticker),
        }
    except Exception as e:
        print(f"Error fetching metrics for {ticker}: {e}")
        return {"shortName": ticker}  # always return at least the ticker as name


def get_historical_data(ticker: str, period: str):
    """
    Fetch history for charts.
    FIX: Skip rows where Close is NaN — yfinance returns NaN for tickers with
    thin/missing data (e.g. recently delisted, pre-market gaps). Python's
    json.dumps raises ValueError on np.float64(nan), causing a 500.
    """
    interval_map = {
        "1d":  "5m",
        "5d":  "15m",
        "1mo": "1d",
        "6mo": "1d",
        "1y":  "1wk",
        "5y":  "1mo",
        "max": "1mo",
    }
    interval = interval_map.get(period, "1d")

    try:
        hist = yf.Ticker(ticker).history(period=period, interval=interval)
        data = []
        for index, row in hist.iterrows():
            price = row['Close']
            # NaN check: NaN != NaN is always True in IEEE 754
            if price != price:
                continue
            data.append({
                "timestamp": index.isoformat(),
                "price": float(price),
            })
        return data
    except Exception as e:
        print(f"Error fetching history for {ticker}: {e}")
        return []


def screen_stock_gainers(query: str):
    try:
        results = yf.screen(query, size=5)
        gainers = []
        for stock in results['quotes'][:5]:
            gainers.append({
                "ticker":    stock['symbol'],
                "price":     _safe_float(stock.get('regularMarketPrice', 0)),
                "changePct": _safe_float(stock.get('regularMarketChangePercent', 0)),
            })
        return gainers
    except Exception as e:
        print(f"Error fetching gainers for {query}: {e}")
        return []


def get_stock_info(stock: str):
    try:
        return yf.Ticker(stock).info
    except Exception as e:
        print(f"Error fetching data for {stock}: {e}")
        return {}