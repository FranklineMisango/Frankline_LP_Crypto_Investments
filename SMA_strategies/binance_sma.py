from datetime import datetime as dt
from binance.client import Client
import pandas as pd
import datetime
import os
from dotenv import load_dotenv
import plotly.graph_objects as go

# Get API keys from environment variables
api_key = os.getenv('Binance_API_KEY')
api_secret = os.getenv('Binance_secret_KEY')

# Initialize Binance client
client = Client(api_key, api_secret)

def get_stock_data(ticker, start, end):
    klines = client.get_historical_klines(ticker, Client.KLINE_INTERVAL_1DAY, start, end)
    df = pd.DataFrame(klines, columns=['Open Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close Time', 'Quote Asset Volume', 'Number of Trades', 'Taker Buy Base Asset Volume', 'Taker Buy Quote Asset Volume', 'Ignore'])
    df['Open Time'] = pd.to_datetime(df['Open Time'], unit='ms')
    df['Close Time'] = pd.to_datetime(df['Close Time'], unit='ms')
    df['Open'] = df['Open'].astype(float)
    df['High'] = df['High'].astype(float)
    df['Low'] = df['Low'].astype(float)
    df['Close'] = df['Close'].astype(float)
    df['Volume'] = df['Volume'].astype(float)
    df['Quote Asset Volume'] = df['Quote Asset Volume'].astype(float)
    df['Number of Trades'] = df['Number of Trades'].astype(float)
    df['Taker Buy Base Asset Volume'] = df['Taker Buy Base Asset Volume'].astype(float)
    df['Taker Buy Quote Asset Volume'] = df['Taker Buy Quote Asset Volume'].astype(float)
    df.set_index('Open Time', inplace=True)  # Set the index to 'Open Time'
    return df


# Define the function for SMA Trading Strategy
def sma_trading_strategy(df, short_sma, long_sma):
    '''
    The content below is AI-gen : 

    The short and long Simple Moving Averages (SMAs) are used to identify trends and potential buy/sell signals in a trading strategy. Here are the key differences:

1. **Calculation Period**:
   - **Short SMA**: Calculated over a shorter period (e.g., 5, 10, or 20 days). It is more sensitive to recent price changes and reacts faster to price movements.
   - **Long SMA**: Calculated over a longer period (e.g., 50, 100, or 200 days). It is less sensitive to recent price changes and provides a smoother view of the overall trend.

2. **Sensitivity to Price Changes**:
   - **Short SMA**: More responsive to recent price changes, making it useful for identifying short-term trends and potential entry/exit points.
   - **Long SMA**: Less responsive to recent price changes, making it useful for identifying long-term trends and reducing the impact of short-term volatility.

3. **Usage in Trading Strategies**:
   - **Short SMA**: Often used to generate buy signals when it crosses above the long SMA (indicating a potential upward trend).
   - **Long SMA**: Often used to generate sell signals when the short SMA crosses below it (indicating a potential downward trend).

    '''
    df[f"SMA_{short_sma}"] = df['Close'].rolling(window=short_sma).mean()
    df[f"SMA_{long_sma}"] = df['Close'].rolling(window=long_sma).mean()

    position = 0
    percent_change = []
    for i in df.index:
        close = df['Close'][i]
        SMA_short = df[f"SMA_{short_sma}"][i]
        SMA_long = df[f"SMA_{long_sma}"][i]

        if SMA_short > SMA_long and position == 0:
            buyP, position = close, 1
            print("Buy at the price:", buyP)
        elif SMA_short < SMA_long and position == 1:
            sellP, position = close, 0
            print("Sell at the price:", sellP)
            percent_change.append((sellP / buyP - 1) * 100)

    if position == 1:
        position = 0
        sellP = df['Close'].iloc[-1]
        print("Sell at the price:", sellP)
        percent_change.append((sellP / buyP - 1) * 100)

    return percent_change

# Main script
print("SMA Trading Strategy Visualization and ccxt backtest")
stock = input("Enter a ticker symbol : ")
start = dt(2024, 11, 1)
end = dt.now()

# Convert datetime objects to strings
start_str = start.strftime('%Y-%m-%d')
end_str = end.strftime('%Y-%m-%d')
num_of_years = end.year - start.year

short_sma = int(input("Enter short SMA ( min_value=1, value=20) : "))
long_sma = int(input("Enter long SMA (min_value=1, value=50)) : "))

df = get_stock_data(stock, start_str, end_str)

# Print the columns of the DataFrame to verify
print(df.columns)

percent_change = sma_trading_strategy(df, short_sma, long_sma)

# Calculate strategy statistics
gains = 0
numGains = 0
losses = 0
numLosses = 0
totReturn = 1
for i in percent_change:
    if i > 0:
        gains += i
        numGains += 1
    else:
        losses += i
        numLosses += 1
    totReturn = totReturn * ((i / 100) + 1)
totReturn = round((totReturn - 1) * 100, 2)

# Plot SMA and Close
fig = go.Figure()
fig.add_trace(go.Scatter(x=df.index, y=df[f"SMA_{short_sma}"], mode='lines', name=f"SMA_{short_sma}"))
fig.add_trace(go.Scatter(x=df.index, y=df[f"SMA_{long_sma}"], mode='lines', name=f"SMA_{long_sma}"))
fig.add_trace(go.Scatter(x=df.index, y=df['Close'], mode='lines', name="Close", line=dict(color='green')))
fig.update_layout(title=f"SMA Trading Strategy for {stock.upper()}", xaxis_title="Date", yaxis_title="Price", template='plotly_dark')
fig.show()

# Display strategy statistics
print(f"Results for {stock.upper()} going back to {num_of_years} years:")
print(f"Number of Trades: {numGains + numLosses}")
print(f"Total return: {totReturn}%")