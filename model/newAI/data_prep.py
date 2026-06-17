import pandas as pd
import numpy as np
import yfinance as yf

def fetch_historical(ticker: str, period: str = "10y", interval: str = "1d"):
    """
    Fetch historical OHLCV data for a ticker using yfinance.
    Returns a DataFrame with columns: Open, High, Low, Close, Volume.
    """
    df = yf.download(ticker, period=period, interval=interval, auto_adjust=True, progress=False)
    if df.empty:
        return pd.DataFrame()
    # Flatten MultiIndex if necessary
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    return df

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add common technical indicators to the DataFrame.
    Modifies in place and returns it for convenience.
    """
    # Make a copy to avoid SettingWithCopyWarning
    df = df.copy()

    # Simple Moving Averages
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    df['SMA_200'] = df['Close'].rolling(window=200).mean()

    # Exponential Moving Averages
    df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
    df['EMA_26'] = df['Close'].ewm(span=26, adjust=False).mean()

    # MACD
    df['MACD'] = df['EMA_12'] - df['EMA_26']
    df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_hist'] = df['MACD'] - df['MACD_signal']

    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # Bollinger Bands
    df['BB_middle'] = df['Close'].rolling(window=20).mean()
    bb_std = df['Close'].rolling(window=20).std()
    df['BB_upper'] = df['BB_middle'] + (bb_std * 2)
    df['BB_lower'] = df['BB_middle'] - (bb_std * 2)

    # ATR (Average True Range)
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(window=14).mean()

    # Volume indicators
    df['Volume_SMA'] = df['Volume'].rolling(window=20).mean()
    df['Volume_ratio'] = df['Volume'] / df['Volume_SMA']

    # Price relative to SMA (distance)
    df['Close_to_SMA50'] = (df['Close'] - df['SMA_50']) / df['SMA_50']
    df['Close_to_SMA200'] = (df['Close'] - df['SMA_200']) / df['SMA_200']

    return df

def prepare_ticker_data(ticker: str, period: str = "10y") -> pd.DataFrame:
    """
    Convenience function: fetch and add indicators in one call.
    """
    df = fetch_historical(ticker, period)
    if df.empty:
        return df
    df = add_indicators(df)
    # Drop NaN rows from indicator calculation
    df.dropna(inplace=True)
    return df

# Example usage
if __name__ == "__main__":
    df = prepare_ticker_data("AAPL", period="2y")
    print(df.tail())