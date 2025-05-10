import alpaca_trade_api as tradeapi
import ccxt
import numpy as np
import pandas as pd
from datetime import datetime

# Pairs Trading Parameters
ASSET1 = "AAPL"
ASSET2 = "MSFT"
LOOKBACK_WINDOW = 20  # Number of days to calculate the moving average and std dev
STD_DEV_THRESHOLD = 2.0  # Number of standard deviations to trigger a trade
TRADE_QUANTITY = 10  # Number of shares to trade

# Function to fetch historical data using ccxt (for backtesting)
def fetch_historical_data_ccxt(exchange_name, symbol, timeframe, limit, since):
    exchange = getattr(ccxt, exchange_name)({'enableRateLimit': True})
    data = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

# Function to calculate the spread and z-score
def calculate_spread_and_zscore(data1, data2):
    spread = data1['close'] - data2['close']  # Simple spread
    spread_mean = spread.rolling(window=LOOKBACK_WINDOW).mean()
    spread_std = spread.rolling(window=LOOKBACK_WINDOW).std()
    z_score = (spread - spread_mean) / spread_std
    return spread, z_score

# Function to execute trades (Alpaca API)
def execute_trade_alpaca(api, symbol, quantity, side):
    try:
        api.submit_order(
            symbol=symbol,
            qty=quantity,
            side=side,
            type='market',
            time_in_force='day',
        )
        print(f"Successfully opened {side} order for {quantity} shares of {symbol}")
    except Exception as e:
        print(f"Error opening order for {symbol}: {e}")

# Pairs Trading Strategy Function
def pairs_trading_strategy(data1, data2, api=None, backtest=False):
    spread, z_score = calculate_spread_and_zscore(data1, data2)

    if backtest:
        signals = pd.DataFrame({'z_score': z_score, 'datetime': data1['datetime']})
        signals['long_entry'] = (signals['z_score'] < -STD_DEV_THRESHOLD)
        signals['short_entry'] = (signals['z_score'] > STD_DEV_THRESHOLD)
        signals['long_exit'] = (signals['z_score'] > 0)
        signals['short_exit'] = (signals['z_score'] < 0)

        positions = pd.DataFrame(index=signals.index)
        positions['long_aapl'] = 0
        positions['short_msft'] = 0
        
        for i in range(1, len(signals)):
          if signals['long_entry'][i]:
            positions['long_aapl'][i] = TRADE_QUANTITY
            positions['short_msft'][i] = -TRADE_QUANTITY
          elif signals['short_entry'][i]:
            positions['long_aapl'][i] = -TRADE_QUANTITY
            positions['short_msft'][i] = TRADE_QUANTITY
          elif signals['long_exit'][i] or signals['short_exit'][i]:
            positions['long_aapl'][i] = -positions['long_aapl'][i-1]
            positions['short_msft'][i] = -positions['short_msft'][i-1]
          else:
            positions['long_aapl'][i] = positions['long_aapl'][i-1]
            positions['short_msft'][i] = positions['short_msft'][i-1]

        # Calculate PnL (simplified - no commissions, slippage)
        aapl_returns = data1['close'].pct_change()
        msft_returns = data2['close'].pct_change()
        positions['aapl_returns'] = positions['long_aapl'].shift(1) * aapl_returns
        positions['msft_returns'] = positions['short_msft'].shift(1) * msft_returns
        positions['total_returns'] = positions['aapl_returns'] + positions['msft_returns']
        cumulative_returns = (1 + positions['total_returns']).cumprod()[-1]
        print(f"Backtest Cumulative Returns: {cumulative_returns}")


# Backtesting
exchange_name = 'binance'  # You can change this to any exchange supported by ccxt
symbol1 = 'AAPL/USDT'  # Adjust symbol format as needed for the exchange
symbol2 = 'MSFT/USDT'
timeframe = '1d'  # 1-day timeframe
limit = 100  # Number of data points to fetch
end_time = datetime.now()
start_time = end_time - pd.Timedelta(days=365)  # 1 year of data
since = int(start_time.timestamp() * 1000)  # ccxt 'since' needs milliseconds

data1_ccxt = fetch_historical_data_ccxt(exchange_name, symbol1, timeframe, limit, since)
data2_ccxt = fetch_historical_data_ccxt(exchange_name, symbol2, timeframe, limit, since)

if data1_ccxt is not None and data2_ccxt is not None:
    pairs_trading_strategy(data1_ccxt, data2_ccxt, backtest=True)
else:
    print("Could not retrieve data for backtesting.")
