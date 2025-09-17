# train_model.py
import pandas as pd
from stable_baselines3 import PPO
from stable_baselines3.common.monitor import Monitor
from bot.trading_env import TradingEnv
from model.callbacks import TrainingCallback

# File Path
DATA_FILE = './model/data/AAPL_historical_data.csv'
TENSORBOARD_LOG_DIR = "./tensorboard_logs/"

# Define training date Range
TRAIN_START_DATE = "2020-01-01"
TRAIN_END_DATE = "2022-12-31"

# Data Preperation
df = pd.read_csv(DATA_FILE, header=None)

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

# Final check of the columns
print("Final DataFrame columns:", df.columns)
print("Final DataFrame head:")
print(df.head())

# Initialize the environment
env = TradingEnv(df)

# env = Monitor(env)

training_callback = TrainingCallback(1000)

# Create and train the PPO model
model = PPO('MlpPolicy', env, verbose=0, tensorboard_log=TENSORBOARD_LOG_DIR)


model.learn(total_timesteps=50000, callback=training_callback, tb_log_name="ppo_stock_trader")


if (input("do you want to save this model? y/n: ").upper() =="Y"):
    model.save("./model/ppo_trading_bot")
    print("Training complete. Model saved.")

else:
    print("Model not saved.")
