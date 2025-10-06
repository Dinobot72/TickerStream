# train_model.py
import pandas as pd
from stable_baselines3 import PPO
from stable_baselines3.common.monitor import Monitor
from bot.trading_env import TradingEnv
from callbacks import TrainingCallback
import os 

# File Path
TICKER = [
        "AAPL", "MSFT", "AMZN", "GOOGL", "META",
        "TSLA", "NVDA", "JPM", "V", "JNJ",
        "WMT", "PG", "HD", "DIS", "BAC",
        "PFE", "NFLX", "KO", "PEP", "CSCO",
        "INTC", "XOM", "CVX", "ADBE", "NKE"
        ]

TENSORBOARD_LOG_DIR = "./tensorboard_logs/"

# Define training date Range
TRAIN_START_DATE = "2020-01-01"
TRAIN_END_DATE = "2022-12-31"





# if (input("do you want to save this model? y/n: ").upper() =="Y"):
#     model.save("./model/ppo_trading_bot")
#     print("Training complete. Model saved.")

# else:
#     print("Model not saved.")


def data_setup(ticker):
    # Data Preperation
    df = pd.read_csv(f'./model/data/{ticker}_historical_data.csv', header=None)

    # The correct column names are on the very first row
    header_row = df.iloc[0].tolist()
    # The 'Date' column is not in the header, so we add it manually
    columns = ['Date'] + header_row[1:]
    df.columns = columns

    # Now, drop the header rows from the DataFrame itself
    # The first three rows are headers
    df = df.iloc[3:].copy()

    # Set the 'Date' column as the index and convert it to datetime
    df.set_index('Date', inplace=True)
    df.index = pd.to_datetime(df.index)

    # Convert all other columns to numeric values
    df = df.apply(pd.to_numeric, errors='coerce')
    df.dropna(inplace=True)

    # Filter training date range
    df = df[(df.index >= TRAIN_START_DATE) & (df.index <= TRAIN_END_DATE)]

    # Final check of the columns
    print("Final DataFrame columns:", df.columns)
    print("Final DataFrame head:")
    print(df.head())
    return df


if __name__ == "__main__":
    # TensorBoardUrl command
    # tensorboard --logdir=./tensorboard_logs
    # run and follow to the localhost

    for ticker in TICKER:
        # Data Preperation
        df = data_setup(ticker)
        print(f'Training on {ticker} ticker')

        # Initialize the environment
        env = TradingEnv(df)

        # Initialize custom training output
        training_callback = TrainingCallback(log_freq=365)

        # Create and train the PPO model
        if not os.path.exists("./model/ppo_training_bot"):
            print('Creating Model')
            model = PPO('MlpPolicy', env, verbose=0, tensorboard_log=TENSORBOARD_LOG_DIR, learning_rate=0.003, device='cpu')
        else:
            print('Loading Model')
            model = PPO.load("./model/ppo_training_bot")

        model.learn(total_timesteps=500000, callback=training_callback, tb_log_name=f'ppo_stock_trader_{ticker}', progress_bar=True)

        model.save("./model/ppo_trading_bot")

        # proceed = input("Y/N: ")
        # if proceed.upper() == 'Y':
        #     continue
        # else:
        #     break