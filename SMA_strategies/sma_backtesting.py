import ccxt
import pandas as pd
from datetime import datetime as dt
import plotly.graph_objects as go

# Initialize ccxt Binance client
exchange = ccxt.binance()

def get_stock_data(ticker, start, end):
    since = exchange.parse8601(start + 'T00:00:00Z')
    end = exchange.parse8601(end + 'T00:00:00Z')
    ohlcv = []
    while since < end:
        data = exchange.fetch_ohlcv(ticker, timeframe='1d', since=since, limit=1000)
        if len(data) == 0:
            break
        since = data[-1][0] + 86400000  # Move to the next day
        ohlcv += data

    df = pd.DataFrame(ohlcv, columns=['Open Time', 'Open', 'High', 'Low', 'Close', 'Volume'])
    df['Open Time'] = pd.to_datetime(df['Open Time'], unit='ms')
    df.set_index('Open Time', inplace=True)
    return df

def sma_trading_strategy(df, short_sma, long_sma):
    df[f"SMA_{short_sma}"] = df['Close'].rolling(window=short_sma).mean()
    df[f"SMA_{long_sma}"] = df['Close'].rolling(window=long_sma).mean()

    position = 0
    percent_change = []
    buy_signals = []
    sell_signals = []

    for i in df.index:
        close = df['Close'][i]
        SMA_short = df[f"SMA_{short_sma}"][i]
        SMA_long = df[f"SMA_{long_sma}"][i]

        if SMA_short > SMA_long and position == 0:
            buyP, position = close, 1
            buy_signals.append((i, buyP))
            print("Buy at the price:", buyP)
        elif SMA_short < SMA_long and position == 1:
            sellP, position = close, 0
            sell_signals.append((i, sellP))
            print("Sell at the price:", sellP)
            percent_change.append((sellP / buyP - 1) * 100)

    if position == 1:
        position = 0
        sellP = df['Close'].iloc[-1]
        sell_signals.append((df.index[-1], sellP))
        print("Sell at the price:", sellP)
        percent_change.append((sellP / buyP - 1) * 100)

    return percent_change, buy_signals, sell_signals

# Main script
print("SMA Trading Strategy Visualization and ccxt backtest")
stock = input("Enter a ticker symbol (e.g., BTC/USDT): ")
start = dt(2024, 1, 1)
end = dt.now()

# Convert datetime objects to strings
start_str = start.strftime('%Y-%m-%d')
end_str = end.strftime('%Y-%m-%d')
num_of_years = end.year - start.year

short_sma = int(input("Enter short SMA (min_value=1, value=20): "))
long_sma = int(input("Enter long SMA (min_value=1, value=50): "))

df = get_stock_data(stock, start_str, end_str)

# Print the columns of the DataFrame to verify
print(df.columns)

percent_change, buy_signals, sell_signals = sma_trading_strategy(df, short_sma, long_sma)

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

# Add buy and sell signals to the plot
buy_x = [signal[0] for signal in buy_signals]
buy_y = [signal[1] for signal in buy_signals]
sell_x = [signal[0] for signal in sell_signals]
sell_y = [signal[1] for signal in sell_signals]

fig.add_trace(go.Scatter(x=buy_x, y=buy_y, mode='markers', name='Buy Signal', marker=dict(color='blue', symbol='triangle-up', size=10)))
fig.add_trace(go.Scatter(x=sell_x, y=sell_y, mode='markers', name='Sell Signal', marker=dict(color='red', symbol='triangle-down', size=10)))

fig.update_layout(title=f"SMA Trading Strategy for {stock.upper()}", xaxis_title="Date", yaxis_title="Price", template='plotly_dark')
fig.show()

# Display strategy statistics
print(f"Results for {stock.upper()} going back to {num_of_years} years:")
print(f"Number of Trades: {numGains + numLosses}")
print(f"Total return: {totReturn}%")