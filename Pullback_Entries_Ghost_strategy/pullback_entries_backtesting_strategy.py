import ccxt
import pandas as pd
import plotly.graph_objs as go
from datetime import datetime, timedelta
import csv

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
    # Count the number of bullish and bearish weeks
    bullish_weeks = weekly_df[(weekly_df['GV2_column'] == 'green') & (weekly_df['GV3_strength'] == 'green')].shape[0]
    bearish_weeks = weekly_df[(weekly_df['GV2_column'] == 'red') & (weekly_df['GV3_strength'] == 'red')].shape[0]
    
    # Determine the overall trend based on the majority
    total_weeks = len(weekly_df)
    print(f"Bullish Weeks: {bullish_weeks}, Bearish Weeks: {bearish_weeks}, Total Weeks: {total_weeks}")
    if bullish_weeks > bearish_weeks:
        return bullish_weeks, bearish_weeks, 'bull'
    elif bearish_weeks > bullish_weeks:
        return bullish_weeks, bearish_weeks, 'bear'
    else:
        return bullish_weeks, bearish_weeks, 'none'

# Pullback entry strategy for daily chart
def pullback_entry(daily_df):
    # Analyze the whole days of the defined period
    recent_data = daily_df
    
    # Conditions for buy and sell signals
    buy_conditions = (recent_data['close'] <= recent_data['GV1_value_zone']) & (recent_data['GV2_column'] == 'red') & (recent_data['RSI'] < 30)
    sell_conditions = (recent_data['close'] >= recent_data['GV1_value_zone']) & (recent_data['GV2_column'] == 'green') & (recent_data['RSI'] > 70)
    
    # Count buy and sell signals
    buy_signals = buy_conditions.sum()
    sell_signals = sell_conditions.sum()

    # Determine the action based on the signals
    if buy_signals > sell_signals:
        return 'buy'
    elif sell_signals > buy_signals:
        return 'sell'
    return 'none'

# Update visualization to show bullish, bearish, and mixed signals
def plot_signals(daily_df, weekly_df):
    fig = go.Figure()

    # Add daily candlesticks
    fig.add_trace(go.Candlestick(
        x=daily_df['timestamp'],
        open=daily_df['open'],
        high=daily_df['high'],
        low=daily_df['low'],
        close=daily_df['close'],
        name='Daily Candlesticks'
    ))

    # Add weekly close as a line
    fig.add_trace(go.Scatter(x=weekly_df['timestamp'], y=weekly_df['close'], mode='lines', name='Weekly Close'))

    # Highlight bullish weeks
    for index, row in weekly_df.iterrows():
        if row['GV2_column'] == 'green':
            fig.add_shape(type="rect",
                          x0=row['timestamp'] - pd.Timedelta(days=3),
                          x1=row['timestamp'] + pd.Timedelta(days=3),
                          y0=row['low'],
                          y1=row['high'],
                          fillcolor="green",
                          opacity=0.2,
                          layer="below",
                          line_width=0)

    # Highlight bearish weeks
    for index, row in weekly_df.iterrows():
        if row['GV2_column'] == 'red':
            fig.add_shape(type="rect",
                          x0=row['timestamp'] - pd.Timedelta(days=3),
                          x1=row['timestamp'] + pd.Timedelta(days=3),
                          y0=row['low'],
                          y1=row['high'],
                          fillcolor="red",
                          opacity=0.2,
                          layer="below",
                          line_width=0)

    fig.update_layout(title='Price Chart with Signals', xaxis_title='Date', yaxis_title='Price')
    fig.show()

def add_signals_to_chart(fig, daily_df, signal, entry_price, stop_loss, target_price):
    # Add entry signal
    fig.add_trace(go.Scatter(
        x=[daily_df['timestamp'].iloc[-1]],
        y=[entry_price],
        mode='markers+text',
        marker=dict(symbol='triangle-up' if signal == 'buy' else 'triangle-down', size=10, color='green' if signal == 'buy' else 'red'),
        text=[f"{signal.capitalize()} Entry"],
        textposition="top center",
        name=f"{signal.capitalize()} Signal"
    ))

    # Add stop loss
    fig.add_trace(go.Scatter(
        x=[daily_df['timestamp'].iloc[-1]],
        y=[stop_loss],
        mode='markers+text',
        marker=dict(symbol='x', size=10, color='blue'),
        text=["Stop Loss"],
        textposition="bottom center",
        name="Stop Loss"
    ))

    # Add target price
    fig.add_trace(go.Scatter(
        x=[daily_df['timestamp'].iloc[-1]],
        y=[target_price],
        mode='markers+text',
        marker=dict(symbol='circle', size=10, color='purple'),
        text=["Target Price"],
        textposition="top center",
        name="Target Price"
    ))

def backtest_strategy(exchange, symbol, start_date, end_date, account_balance=100, risk_per_trade=0.01):
    try:
        # Convert dates to timestamps
        start_timestamp = exchange.parse8601(start_date)
        end_timestamp = exchange.parse8601(end_date)

        # Fetch weekly and daily data
        weekly_df = fetch_historical_data(exchange, symbol, '1w', since=start_date)
        daily_df = fetch_historical_data(exchange, symbol, '1d', since=start_date)

        # Convert timestamps to datetime
        start_datetime = pd.to_datetime(start_timestamp, unit='ms')
        end_datetime = pd.to_datetime(end_timestamp, unit='ms')

        # Filter data within the specified date range
        weekly_df = weekly_df[(weekly_df['timestamp'] >= start_datetime) & (weekly_df['timestamp'] <= end_datetime)]
        daily_df = daily_df[(daily_df['timestamp'] >= start_datetime) & (daily_df['timestamp'] <= end_datetime)]

        # Apply indicators
        weekly_df = apply_indicators(weekly_df)
        daily_df = apply_indicators(daily_df)

        # Identify trend
        bullish_weeks, bearish_weeks, trend = identify_trend(weekly_df)
        print(f"Overall Trend: {trend.capitalize()}")

        initial_balance = account_balance
        total_profit = 0

        # Iterate through the entire DataFrame
        for index in range(len(daily_df)):
            signal = pullback_entry(daily_df.iloc[:index+1])
            if signal == 'buy' or signal == 'sell':
                print(f"{signal.capitalize()} signal identified.")
                stop_loss = daily_df['low'].iloc[index] if signal == 'buy' else daily_df['high'].iloc[index]
                entry_price = daily_df['close'].iloc[index]
                target_price = entry_price + 2 * (entry_price - stop_loss) if signal == 'buy' else entry_price - 2 * (stop_loss - entry_price)

                # Position sizing
                risk_amount = account_balance * risk_per_trade
                position_size = risk_amount / abs(entry_price - stop_loss)

                print(f"Entry Price: {entry_price}, Stop Loss: {stop_loss}, Target Price: {target_price}")
                print(f"Position Size: {position_size:.2f} units")

                # Calculate profit or loss
                if signal == 'buy':
                    profit = (target_price - entry_price) * position_size
                else:
                    profit = (entry_price - target_price) * position_size

                total_profit += profit
                account_balance += profit

                # Save to CSV
                with open('pullback_entries.csv', mode='a', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow([daily_df['timestamp'].iloc[index], signal, entry_price, stop_loss, target_price, position_size, profit])

        # Calculate percentage profit
        percentage_profit = (total_profit / initial_balance) * 100

        print(f"Total Profit: {total_profit:.2f}")
        print(f"Percentage Profit: {percentage_profit:.2f}%")

        print("All entry signals have been saved to pullback_entries.csv")

        # Plot signals
        plot_signals(daily_df, weekly_df)

    except Exception as e:
        print(f"Error during backtesting: {e}")

if __name__ == "__main__":
    exchange = initialize_binance()
    symbol = 'BTC/USDT'
    start_date = '2024-01-01T00:00:00Z'  
    end_date = '2025-01-30T00:00:00Z'    
    print(f"Running backtest from {start_date} to {end_date}...")
    backtest_strategy(exchange, symbol, start_date, end_date)