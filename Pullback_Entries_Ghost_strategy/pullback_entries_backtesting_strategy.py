import ccxt
import pandas as pd
import plotly.graph_objs as go
from datetime import datetime, timedelta

# Initialize Binance client using ccxt
def initialize_binance():
    return ccxt.binance({
        'rateLimit': 2000,
        'enableRateLimit': True,
    })

# Fetch historical data from Binance using ccxt
def fetch_historical_data(exchange, symbol, timeframe, since=None, limit=None):
    try:
        if since:
            since = exchange.parse8601(since)
        else:
            since = exchange.parse8601((datetime.utcnow() - timedelta(days=limit * 7 if timeframe == '1w' else limit)).isoformat())
        
        all_ohlcv = []
        while True:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since)
            if not ohlcv:
                break
            all_ohlcv.extend(ohlcv)
            since = ohlcv[-1][0] + 1  # Move to the next time period
            if len(all_ohlcv) >= 1000:  # Limit to 1000 candles for performance
                break
        
        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"Error fetching historical data: {e}")
        return pd.DataFrame()

# Apply GhostVision indicators and additional indicators
def apply_indicators(df, rolling_window=14, rsi_period=14):
    # GhostVision Indicators
    df['GV1_value_zone'] = df['close'].rolling(window=rolling_window).mean()
    df['GV2_column'] = df['close'].diff().apply(lambda x: 'green' if x > 0 else 'red')
    
    rolling_mean = df['close'].rolling(window=rolling_window).mean()
    df['GV3_strength'] = df.apply(lambda row: 'green' if row['close'] > rolling_mean.loc[row.name] else 'red', axis=1)
    
    # Additional Indicators
    df['RSI'] = calculate_rsi(df['close'], rsi_period)
    df['Bollinger_Upper'], df['Bollinger_Lower'] = calculate_bollinger_bands(df['close'], rolling_window)
    
    return df

# Calculate RSI
def calculate_rsi(series, period):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# Calculate Bollinger Bands
def calculate_bollinger_bands(series, period):
    rolling_mean = series.rolling(window=period).mean()
    rolling_std = series.rolling(window=period).std()
    upper_band = rolling_mean + (2 * rolling_std)
    lower_band = rolling_mean - (2 * rolling_std)
    return upper_band, lower_band

# Identify trend from weekly chart
def identify_trend(weekly_df):
    latest = weekly_df.iloc[-1]
    print(f"Latest Weekly Data: {latest}")  # Debugging output
    if latest['GV2_column'] == 'green' and latest['GV3_strength'] == 'green':
        return 'bull'
    elif latest['GV2_column'] == 'red' and latest['GV3_strength'] == 'red':
        return 'bear'
    return 'none'

# Pullback entry strategy for daily chart
def pullback_entry(daily_df):
    latest = daily_df.iloc[-1]
    print(f"Latest Daily Data: {latest}")  # Debugging output
    if latest['close'] <= latest['GV1_value_zone'] and latest['GV2_column'] == 'red' and latest['RSI'] < 30:
        return 'buy'
    elif latest['close'] >= latest['GV1_value_zone'] and latest['GV2_column'] == 'green' and latest['RSI'] > 70:
        return 'sell'
    return 'none'

# Backtest strategy
def backtest_strategy(exchange, symbol, start_date, end_date, account_balance=10000, risk_per_trade=0.01):
    try:
        # Convert dates to timestamps
        start_timestamp = exchange.parse8601(start_date)
        end_timestamp = exchange.parse8601(end_date)

        start_timestamp = pd.to_datetime(start_timestamp, unit='ms')
        end_timestamp = pd.to_datetime(end_timestamp, unit='ms')

        # Fetch weekly and daily data
        weekly_df = fetch_historical_data(exchange, symbol, '1w', since=start_date)
        daily_df = fetch_historical_data(exchange, symbol, '1d', since=start_date)

        # Filter data within the specified date range
        weekly_df = weekly_df[(weekly_df['timestamp'] >= start_timestamp) & (weekly_df['timestamp'] <= end_timestamp)]
        daily_df = daily_df[(daily_df['timestamp'] >= start_timestamp) & (daily_df['timestamp'] <= end_timestamp)]

        print(f"Weekly Data Range: {weekly_df['timestamp'].min()} to {weekly_df['timestamp'].max()}")  # Debugging output
        print(f"Daily Data Range: {daily_df['timestamp'].min()} to {daily_df['timestamp'].max()}")      # Debugging output

        # Apply indicators
        weekly_df = apply_indicators(weekly_df)
        daily_df = apply_indicators(daily_df)

        # Identify trend
        trend = identify_trend(weekly_df)
        if trend == 'none':
            print("No clear trend identified. Skipping trade.")
            return

        # Look for pullback entry
        signal = pullback_entry(daily_df)
        if signal == 'buy' or signal == 'sell':
            print(f"{signal.capitalize()} signal identified.")
            stop_loss = daily_df['low'].iloc[-1] if signal == 'buy' else daily_df['high'].iloc[-1]
            entry_price = daily_df['close'].iloc[-1]
            target_price = entry_price + 2 * (entry_price - stop_loss) if signal == 'buy' else entry_price - 2 * (stop_loss - entry_price)

            # Position sizing
            risk_amount = account_balance * risk_per_trade
            position_size = risk_amount / abs(entry_price - stop_loss)

            print(f"Entry Price: {entry_price}, Stop Loss: {stop_loss}, Target Price: {target_price}")
            print(f"Position Size: {position_size:.2f} units")

        # Plot interactive graph
        fig = go.Figure()

        # Add weekly close as a line
        fig.add_trace(go.Scatter(x=weekly_df['timestamp'], y=weekly_df['close'], mode='lines', name='Weekly Close'))

        # Add daily candlesticks
        fig.add_trace(go.Candlestick(
            x=daily_df['timestamp'],
            open=daily_df['open'],
            high=daily_df['high'],
            low=daily_df['low'],
            close=daily_df['close'],
            name='Daily Candlesticks'
        ))

        # Add Bollinger Bands
        fig.add_trace(go.Scatter(x=daily_df['timestamp'], y=daily_df['Bollinger_Upper'], mode='lines', name='Bollinger Upper'))
        fig.add_trace(go.Scatter(x=daily_df['timestamp'], y=daily_df['Bollinger_Lower'], mode='lines', name='Bollinger Lower'))

        fig.update_layout(title=f'{symbol} Price Chart', xaxis_title='Date', yaxis_title='Price')
        fig.show()

    except Exception as e:
        print(f"Error during backtesting: {e}")

if __name__ == "__main__":
    exchange = initialize_binance()
    symbol = 'BTC/USDT'

    # Define your custom start and end dates for backtesting
    start_date = '2024-01-01T00:00:00Z'  # Extended start date
    end_date = '2025-01-30T00:00:00Z'    # End date

    print(f"Running backtest from {start_date} to {end_date}...")
    backtest_strategy(exchange, symbol, start_date, end_date)
