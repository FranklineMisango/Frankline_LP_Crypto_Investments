import numpy as np
import pandas as pd
import yfinance as yf
import statsmodels.api as sm 

asset1 = 'AAPL'
asset2 = 'MSFT'
lookback_window = 252 
std_dev_multiples = np.arange(1.5, 3.1, 0.5)
use_cointegration = True 

# Fetch data
data1 = yf.download(asset1, start='2022-01-01', end='2024-01-01')
data2 = yf.download(asset2, start='2022-01-01', end='2024-01-01')

# Calculate spread
if use_cointegration:
    model = sm.OLS(data1['Close'], sm.add_constant(data2['Close'])).fit()
    hedge_ratio = model.params[1]
    spread = data1['Close'] - hedge_ratio * data2['Close']
else:
    spread = data1['Close'] - data2['Close']

spread_mean = spread.rolling(window=lookback_window).mean()
spread_std = spread.rolling(window=lookback_window).std()
z_score = (spread - spread_mean) / spread_std

# Backtesting function (same as before, but more concise)
def backtest_pairs_trading(z_score, std_dev_threshold, data1, data2):
    positions = pd.DataFrame(index=z_score.index)
    positions['asset1'] = np.select(
        [z_score < -std_dev_threshold, z_score > std_dev_threshold, abs(z_score) < 0.5],  # Include an exit
        [1, -1, 0],
        default=positions['asset1'].shift(1)
    )
    positions['asset2'] = np.select(
        [z_score < -std_dev_threshold, z_score > std_dev_threshold, abs(z_score) < 0.5],
        [-1, 1, 0],
        default=positions['asset1'].shift(1)
    )

    asset1_returns = data1['Close'].pct_change()
    asset2_returns = data2['Close'].pct_change()
    portfolio_returns = positions['asset1'].shift(1) * asset1_returns + positions['asset2'].shift(1) * asset2_returns
    cumulative_returns = (1 + portfolio_returns).cumprod()
    sharpe_ratio = portfolio_returns.mean() / portfolio_returns.std() * np.sqrt(252)
    return sharpe_ratio, cumulative_returns.iloc[-1]

# Optimization loop
results = []
for multiple in std_dev_multiples:
    sharpe, final_return = backtest_pairs_trading(z_score, multiple, data1, data2)
    results.append({'std_dev_multiple': multiple, 'sharpe_ratio': sharpe, 'final_return': final_return})

# Find optimal band
results_df = pd.DataFrame(results)
optimal_band = results_df.loc[results_df['sharpe_ratio'].idxmax()]

print("Optimization Results:")
print(results_df)
print("\nOptimal Band (std_dev_multiple):", optimal_band['std_dev_multiple'])
print("Optimal Sharpe Ratio:", optimal_band['sharpe_ratio'])