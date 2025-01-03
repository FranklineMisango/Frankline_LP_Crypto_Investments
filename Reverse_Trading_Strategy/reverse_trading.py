import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta

# Initialize Binance client
def initialize_binance():
    return ccxt.binance({
        'rateLimit': 1200,
        'enableRateLimit': True,
    })

# Fetch historical data from Binance
def fetch_historical_data(exchange, symbol, timeframe, limit=100):
    since = exchange.parse8601((datetime.utcnow() - timedelta(days=limit * 7 if timeframe == '1w' else limit)).isoformat())
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

# Calculate support and resistance levels
def calculate_support_resistance(df):
    df['support'] = df['low'].rolling(window=14).min()
    df['resistance'] = df['high'].rolling(window=14).max()
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
    daily_df = fetch_historical_data(exchange, symbol, '1d', limit=100)
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
    exchange = initialize_binance()
    symbol = 'BTC/USDT'

    while True:
        try:
            print(f"Running strategy at {datetime.utcnow()}...")
            reverse_trading_strategy(exchange, symbol)
            time.sleep(3600)  # Run hourly
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(60)
