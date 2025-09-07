import yfinance as yf
import pandas as pd

def download_and_save_stock_data(ticker: str, start_date: str, end_date: str, output_path: str):
    """
    Downloads historical stock data and saves it to a CSV file.
    
    Args:
        ticker (str): The stock ticker symbol (e.g., 'AAPL').
        start_date (str): The start date for the data in 'YYYY-MM-DD' format.
        end_date (str): The end date for the data in 'YYYY-MM-DD' format.
        output_path (str): The path to save the CSV file.
    """
    try:
        print(f"Downloading data for {ticker} from {start_date} to {end_date}...")
        
        # Download historical data
        df = yf.download(ticker, start=start_date, end=end_date, auto_adjust=True)
        
        # Save the DataFrame to a CSV file
        df.to_csv(output_path)
        
        print(f"Successfully downloaded and saved data to {output_path}")
        
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    # --- Example Usage ---
    # Pick a stock and a time range
    TICKER = 'AAPL'
    START_DATE = '2020-01-01'
    END_DATE = '2024-01-01'
    OUTPUT_FILE = f'./model/data/{TICKER}_historical_data.csv'
    
    download_and_save_stock_data(TICKER, START_DATE, END_DATE, OUTPUT_FILE)