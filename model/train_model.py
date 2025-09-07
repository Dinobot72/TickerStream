# train_model.py
import pandas as pd
from stable_baselines3 import PPO
from bot.trading_env import TradingEnv

# Corrected file path
DATA_FILE = './model/data/AAPL_historical_data.csv'
print(f"Attempting to load data from {DATA_FILE}")

# Load the historical data from the CSV file
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

# Create and train the PPO model
model = PPO('MlpPolicy', env, verbose=1)
model.learn(total_timesteps=25000)
model.save("ppo_trading_bot")

print("Training complete. Model saved.")