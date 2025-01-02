from binance.client import Client
import pandas as pd
import datetime
import os
from dotenv import load_dotenv
import plotly.graph_objects as go

# Load environment variables
load_dotenv()

# Get API keys from environment variables
api_key = os.getenv('Binance_API_KEY')
api_secret = os.getenv('Binance_secret_KEY')

# Initialize Binance client
client = Client(api_key, api_secret)

# Define the time range for fetching data
start_time = datetime.datetime(2024, 3, 15, 0, 0, 0)
end_time = datetime.datetime(2025, 1, 1, 0, 0, 0)

# Define the symbol and fetch historical klines data
symbol = "USUALUSDT"
klines = client.get_historical_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_1MINUTE, start_str=str(start_time), end_str=str(end_time))

# Convert the data into a pandas dataframe for easier manipulation
df_M = pd.DataFrame(klines, columns=['Open Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close Time', 'Quote Asset Volume', 'Number of Trades', 'Taker Buy Base Asset Volume', 'Taker Buy Quote Asset Volume', 'Ignore'])

# Convert necessary columns to float
columns_to_convert = ['Open', 'High', 'Low', 'Close', 'Volume', 'Quote Asset Volume', 'Number of Trades', 'Taker Buy Base Asset Volume', 'Taker Buy Quote Asset Volume']
for col in columns_to_convert:
    df_M[col] = df_M[col].astype(float)

# Convert 'Open Time' to datetime
df_M['Open Time'] = pd.to_datetime(df_M['Open Time'], unit='ms')

# Create a candlestick chart using Plotly
fig = go.Figure(data=[go.Candlestick(x=df_M['Open Time'],
                                     open=df_M['Open'],
                                     high=df_M['High'],
                                     low=df_M['Low'],
                                     close=df_M['Close'])])

# Update layout for better visualization
fig.update_layout(title=f'Candlestick chart for {symbol}',
                  xaxis_title='Date',
                  yaxis_title='Price (USDT)',
                  xaxis_rangeslider_visible=False)

# Show the chart
fig.show()