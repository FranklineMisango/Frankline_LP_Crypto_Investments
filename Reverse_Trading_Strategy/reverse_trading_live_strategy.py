from lumibot.entities import Asset, Order
from lumibot.strategies import Strategy
from lumibot.backtesting import CcxtBacktesting
import pandas as pd
import ccxt
import time
from datetime import datetime as dt, timedelta
from binance.client import Client
import os

api_key = os.getenv('Binance_API_KEY')
api_secret = os.getenv('Binance_secret_KEY')

# Initialize Binance client
client = Client(api_key, api_secret)

# Fetch current data from Binance and imploy the minute by minute strategy
def Fetch_current_data_binance(ticker, start, end):
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

# Calculate support and resistance levels
def calculate_support_resistance(df):
    df['support'] = df['Low'].rolling(window=14).min()
    df['resistance'] = df['High'].rolling(window=14).max()
    return df

# Identify reversal signals
def identify_reversal_signals(df):
    latest = df.iloc[-1]
    previous = df.iloc[-2]
    
    # Reversal from resistance (bearish)
    if latest['high'] >= latest['resistance'] and latest['close'] < previous['close']:
        return 'sell'
    
    # Reversal from support (bullish)
    if latest['low'] <= latest['support'] and latest['close'] > previous['close']:
        return 'buy'

    return 'none'

# Reverse trading strategy
def reverse_trading_strategy(exchange, symbol):
    # Fetch and process daily data
    daily_df = Fetch_current_data_binance(exchange, symbol, '1d', limit=100)
    daily_df = calculate_support_resistance(daily_df)

    # Identify reversal signals
    signal = identify_reversal_signals(daily_df)
    if signal == 'buy':
        print("Bullish reversal signal identified.")
        stop_loss = daily_df['low'].iloc[-1]
        entry_price = daily_df['close'].iloc[-1]
        target_price = entry_price + 2 * (entry_price - stop_loss)
        print(f"Entry Price: {entry_price}, Stop Loss: {stop_loss}, Target Price: {target_price}")
    elif signal == 'sell':
        print("Bearish reversal signal identified.")
        stop_loss = daily_df['high'].iloc[-1]
        entry_price = daily_df['close'].iloc[-1]
        target_price = entry_price - 2 * (stop_loss - entry_price)
        print(f"Entry Price: {entry_price}, Stop Loss: {stop_loss}, Target Price: {target_price}")
    else:
        print("No reversal signal identified.")


if __name__ == "__main__":
    #exchange = initialize_binance() # TODO - Fix the live exchange for the strategy and connect to binance websockeckts
    symbol = 'BTC/USDT'

    while True:
        try:
            print(f"Running strategy at {dt.now}...")
            reverse_trading_strategy(exchange, symbol)
            time.sleep(3600)  # Run hourly
        except Exception as e:
            print(f"Error: {e}")