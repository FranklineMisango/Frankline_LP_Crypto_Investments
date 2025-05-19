import pandas as pd
import ccxt
import time
import numpy as np
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import pytz
from datetime import timedelta
import ta
from ta.volatility import BollingerBands, AverageTrueRange
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import MACD, ADXIndicator
from ta.volume import VolumeWeightedAveragePrice
import os
import joblib
from tqdm import tqdm  

class ScalpingStrategy:
    def __init__(self, symbol, initial_portfolio_value=10000, fee_rate=0.001, risk_per_trade=0.01, 
                 reentry_delay=5, max_position_pct=0.2, rsi_period=14, bb_period=20, atr_period=14,
                 atr_multiplier=2.0, market_regime_lookback=100, use_cached_data=True, use_higher_tf=True,
                 fast_mode=False):
        self.symbol = symbol
        self.risk_per_trade = risk_per_trade
        self.exchange = ccxt.binance()
        self.fee_rate = fee_rate
        self.max_position_pct = max_position_pct
        self.data = None
        self.trades = []
        self.reentry_delay = reentry_delay
        self.last_exit_index = -self.reentry_delay
        self.portfolio_value = initial_portfolio_value
        self.initial_portfolio_value = initial_portfolio_value
        self.position = 0
        self.quantity = 0
        self.max_profit_trade = None
        self.max_loss_trade = None
        self.buy_prices = []
        self.asset_value = 0
        
        # Improved technical indicator parameters
        self.rsi_period = rsi_period
        self.bb_period = bb_period
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.market_regime_lookback = market_regime_lookback
        
        # Dynamic threshold parameters
        self.rsi_oversold = 30
        self.rsi_overbought = 70
        self.adx_threshold = 25
        
        # Higher timeframe data
        self.htf_data = None

        # Performance optimization flags
        self.use_cached_data = use_cached_data
        self.use_higher_tf = use_higher_tf
        self.fast_mode = fast_mode  # Runs faster with fewer features
        
        # Cache directory
        self.cache_dir = '/workspaces/Frankline_LP_Crypto_Investments/Scalping_Strategy/cache'
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Performance tracking
        self.perf_metrics = {}

    def place_order(self, side, price, timestamp, reason=""):
        if side == 'buy':
            # Calculate position size based on ATR for dynamic risk management
            atr = self.data['atr'].iloc[-1] if 'atr' in self.data else price * 0.01
            max_purchase = self.portfolio_value * (1 - self.fee_rate)
            
            # Use ATR-based position sizing - risk the same dollar amount on each trade
            risk_amount = self.portfolio_value * self.risk_per_trade
            stop_price = price - (self.atr_multiplier * atr)
            risk_per_unit = price - stop_price
            
            # Calculate quantity ensuring we don't exceed max position and available cash
            if risk_per_unit > 0:
                position_size = risk_amount / risk_per_unit
                self.quantity = min(position_size, max_purchase / price, 
                                  (self.portfolio_value * self.max_position_pct) / price)
            else:
                self.quantity = min(max_purchase / price, 
                                  (self.portfolio_value * self.max_position_pct) / price)
            
            # Update portfolio
            purchase_cost = self.quantity * price * (1 + self.fee_rate)
            self.portfolio_value -= purchase_cost
            self.asset_value = self.quantity * price
            
            # Record entry price and initial stop price
            self.buy_prices.append(price)
            self.initial_stop = stop_price
            
        else:  # sell
            # Calculate sale proceeds after fees
            sale_proceeds = self.quantity * price * (1 - self.fee_rate)
            self.portfolio_value += sale_proceeds
            self.asset_value = 0
            self.quantity = 0
            
        total_value = self.portfolio_value + self.asset_value
        print(f"Simulating {side} order for {self.quantity:.6f} {self.symbol} at {price:.2f} on {timestamp} - {reason}")
        print(f"  Cash: ${self.portfolio_value:.2f}, Asset Value: ${self.asset_value:.2f}, Total: ${total_value:.2f}")
        
        self.trades.append({
            'side': side, 
            'price': price, 
            'time': timestamp,
            'quantity': self.quantity,
            'fee': (price * self.quantity * self.fee_rate),
            'buy_price': self.buy_prices[-1] if side == 'sell' and self.buy_prices else None,
            'portfolio_value': total_value,
            'reason': reason  # Track the reason for the trade
        })
        return True
   
    def get_minute_data(self, start_date, end_date, interval='1m'):
        """Fetch and process OHLCV data with caching for better performance"""
        cache_file = f"{self.cache_dir}/{self.symbol.replace('/', '_')}_{interval}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.joblib"
        
        # Try to load from cache if enabled
        if self.use_cached_data and os.path.exists(cache_file):
            print(f"Loading data from cache: {cache_file}")
            frame = joblib.load(cache_file)
            return frame
            
        fetch_start_time = time.time()
        
        since = self.exchange.parse8601(start_date.isoformat())
        end = self.exchange.parse8601(end_date.isoformat())
        data = []

        # Show progress during data fetching
        print(f"Fetching {interval} data for {self.symbol} from {start_date} to {end_date}")
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            chunk_size = (end - since) // 4
            for i in range(4):
                chunk_start = since + i * chunk_size
                chunk_end = min(since + (i + 1) * chunk_size, end)
                futures.append(executor.submit(self.fetch_data_chunk, chunk_start, chunk_end, interval))

            for i, future in enumerate(futures):
                print(f"Fetching chunk {i+1}/4...", end="\r")
                data.extend(future.result())
        
        if not data:
            raise ValueError(f"No data returned for {self.symbol} with {interval} timeframe")
            
        print(f"Processing {len(data)} data points...")
        
        frame = pd.DataFrame(data, columns=['Time', 'Open', 'High', 'Low', 'Close', 'Volume'])
        frame = frame.set_index('Time')
        frame.index = pd.to_datetime(frame.index, unit='ms')
        
        # Remove duplicates at data fetch time
        frame = frame[~frame.index.duplicated(keep='first')]
        frame = frame.astype(float)
        
        fetch_time = time.time() - fetch_start_time
        print(f"Data fetched in {fetch_time:.2f} seconds")
        
        # Save to cache if enabled
        if self.use_cached_data:
            print(f"Saving data to cache: {cache_file}")
            joblib.dump(frame, cache_file)
        
        # Add a parallel fetch for higher timeframe data for multi-timeframe analysis
        if interval == '1m' and self.use_higher_tf and not self.fast_mode:
            try:
                # Also fetch 15m data for higher timeframe context
                htf_start = start_date - timedelta(days=5)  # Reduced from 10 days to 5 for speed
                self.htf_data = self.get_minute_data(htf_start, end_date, '15m')
                print(f"Higher timeframe data fetched successfully: {len(self.htf_data)} rows")
            except Exception as e:
                print(f"Warning: Could not fetch higher timeframe data: {e}")
                self.htf_data = None
        elif self.fast_mode:
            self.htf_data = None
            print("Higher timeframe analysis disabled in fast mode")
        
        return frame

    def fetch_data_chunk(self, since, end, interval):
        data = []
        retry_count = 0
        max_retries = 3
        
        while since < end:
            try:
                chunk = self.exchange.fetch_ohlcv(self.symbol, timeframe=interval, since=since, limit=1000)
                if not chunk:
                    break
                since = chunk[-1][0] + 1
                data.extend(chunk)
                time.sleep(self.exchange.rateLimit / 1000)  # Respect the rate limit
                retry_count = 0  # Reset retry counter on success
            except Exception as e:
                retry_count += 1
                if retry_count > max_retries:
                    print(f"Failed to fetch data after {max_retries} retries: {e}")
                    break
                print(f"Error fetching data: {e}. Retrying ({retry_count}/{max_retries})...")
                time.sleep(2 * retry_count)  # Exponential backoff
        
        return data
    
    def calculate_position_size(self, price):
        """Dynamic position sizing based on ATR"""
        # Get the latest ATR value
        atr = self.data['atr'].iloc[-1] if 'atr' in self.data else price * 0.01
        
        # Determine stop loss distance using ATR
        stop_distance = self.atr_multiplier * atr
        
        # Calculate position size based on risk amount and stop distance
        risk_amount = (self.portfolio_value + self.asset_value) * self.risk_per_trade
        position_size = risk_amount / stop_distance if stop_distance > 0 else 0
        
        # Cap at a percentage of portfolio
        max_position_size = (self.portfolio_value + self.asset_value) * self.max_position_pct / price
        cash_constraint = self.portfolio_value / price
        
        return min(position_size, max_position_size, cash_constraint)

    def add_indicators(self):
        """Add technical indicators with performance optimizations"""
        indicator_start_time = time.time()
        print("Calculating technical indicators...")
        
        # Ensure data is clean
        self.data = self.data.dropna()
        
        # Only calculate the indicators we actually use in our strategy
        # to save computation time
        
        # Core indicators needed for all modes
        indicator_list = []
        
        # MACD - used by entry and exit logic
        macd = MACD(close=self.data['Close'])
        self.data['macd'] = macd.macd()
        self.data['macd_signal'] = macd.macd_signal()
        self.data['macd_diff'] = macd.macd_diff()
        indicator_list.append("MACD")
        
        # ADX - used by entry logic
        adx = ADXIndicator(high=self.data['High'], low=self.data['Low'], close=self.data['Close'])
        self.data['adx'] = adx.adx()
        self.data['di_plus'] = adx.adx_pos()
        self.data['di_minus'] = adx.adx_neg()
        indicator_list.append("ADX")
        
        # Bollinger Bands - used by entry logic
        bb = BollingerBands(close=self.data['Close'], window=self.bb_period)
        self.data['bb_upper'] = bb.bollinger_hband()
        self.data['bb_lower'] = bb.bollinger_lband()
        self.data['bb_mid'] = bb.bollinger_mavg()
        self.data['bb_width'] = (self.data['bb_upper'] - self.data['bb_lower']) / self.data['bb_mid']
        indicator_list.append("Bollinger Bands")
        
        # ATR - used for position sizing and exits
        atr = AverageTrueRange(high=self.data['High'], low=self.data['Low'], close=self.data['Close'], 
                              window=self.atr_period)
        self.data['atr'] = atr.average_true_range()
        indicator_list.append("ATR")
        
        # RSI - used by entry and exit
        rsi = RSIIndicator(close=self.data['Close'], window=self.rsi_period)
        self.data['rsi'] = rsi.rsi()
        indicator_list.append("RSI")
        
        # Skip additional indicators in fast mode
        if not self.fast_mode:
            # Stochastic - secondary confirmation
            stoch = StochasticOscillator(high=self.data['High'], low=self.data['Low'], close=self.data['Close'])
            self.data['stoch_k'] = stoch.stoch()
            self.data['stoch_d'] = stoch.stoch_signal()
            indicator_list.append("Stochastic")
            
            # Volume indicators - used for entry confirmation
            self.data['volume_ma'] = self.data['Volume'].rolling(window=20).mean()
            self.data['volume_ratio'] = self.data['Volume'] / self.data['volume_ma']
            indicator_list.append("Volume")
        else:
            # In fast mode, add simplified volume ratio
            self.data['volume_ratio'] = self.data['Volume'] / self.data['Volume'].rolling(window=20).mean()
        
        # Market regime detection (simplified in fast mode)
        self.data['returns'] = self.data['Close'].pct_change()
        lookback = min(self.market_regime_lookback, 50) if self.fast_mode else self.market_regime_lookback
        self.data['volatility'] = self.data['returns'].rolling(window=lookback).std() * np.sqrt(252)
        
        # Detect market regime (low/high volatility)
        vol_quantiles = self.data['volatility'].quantile([0.25, 0.75]).values
        self.data['market_regime'] = np.where(
            self.data['volatility'] <= vol_quantiles[0], 'low_volatility',
            np.where(self.data['volatility'] >= vol_quantiles[1], 'high_volatility', 'normal')
        )
        indicator_list.append("Market Regime")
        
        # If we have higher timeframe data, add signals from it (but skip in fast mode)
        if self.htf_data is not None and not self.fast_mode:
            try:
                # Make sure htf data doesn't have duplicates
                self.htf_data = self.htf_data[~self.htf_data.index.duplicated(keep='first')]
                
                # Simplified higher timeframe indicators for better performance
                htf_rsi = RSIIndicator(close=self.htf_data['Close']).rsi()
                htf_macd = MACD(close=self.htf_data['Close']).macd_diff()
                htf_adx = ADXIndicator(high=self.htf_data['High'], low=self.htf_data['Low'], 
                                     close=self.htf_data['Close']).adx()
                
                # Create HTF trend signal using vectorized operations for speed
                htf_trend = np.zeros(len(htf_rsi))
                htf_trend = np.where((htf_rsi > 50) & (htf_macd > 0) & (htf_adx > 25), 1, htf_trend)
                htf_trend = np.where((htf_rsi < 50) & (htf_macd < 0) & (htf_adx > 25), -1, htf_trend)
                
                # Merge HTF signals with main data - using more efficient approach
                # Create a single DataFrame for better performance
                htf_df = pd.DataFrame({
                    'htf_trend': htf_trend
                }, index=self.htf_data.index)
                
                # More efficient method to merge higher timeframe data
                htf_resampled = htf_df.reindex(
                    pd.date_range(start=self.data.index[0], end=self.data.index[-1], freq='1min')
                ).ffill()
                
                # Align indices exactly to avoid mismatch
                htf_aligned = htf_resampled.loc[self.data.index] if len(htf_resampled) >= len(self.data) else None
                
                # Add to main dataframe if alignment was successful
                if htf_aligned is not None:
                    self.data['htf_trend'] = htf_aligned['htf_trend'].values
                    indicator_list.append("Higher Timeframe Trend")
                    print(f"Higher timeframe indicators added successfully")
                else:
                    print("Warning: Higher timeframe data could not be aligned with main timeframe")
                
            except Exception as e:
                print(f"Warning: Could not incorporate higher timeframe data: {e}")
                # Continue with just the main timeframe data
        
        indicator_time = time.time() - indicator_start_time
        self.perf_metrics['indicator_calculation_time'] = indicator_time
        print(f"Added indicators: {', '.join(indicator_list)} in {indicator_time:.2f} seconds")

    def entry_signal(self, i):
        """Enhanced entry signal with multiple confirmation factors"""
        if i < 50:  # Need enough data for indicators
            return False, ""
            
        row = self.data.iloc[i]
        prev_row = self.data.iloc[i-1]
        
        # Dynamic threshold adjustment based on market regime
        if row['market_regime'] == 'high_volatility':
            rsi_threshold = 40  # Be more conservative in high volatility
            adx_threshold = 30  # Require stronger trend
        else:
            rsi_threshold = self.rsi_oversold
            adx_threshold = self.adx_threshold
            
        # Baseline trend conditions
        trend_condition = (
            row['Close'] > row['bb_mid'] and
            row['adx'] > adx_threshold and
            row['di_plus'] > row['di_minus']
        )
        
        # Momentum entry
        momentum_entry = (
            row['rsi'] > rsi_threshold and
            row['rsi'] < 60 and  # Not overbought
            row['macd_diff'] > 0 and
            prev_row['macd_diff'] < row['macd_diff']  # Increasing momentum
        )
        
        # Volatility breakout entry
        volatility_entry = (
            row['Close'] > prev_row['bb_upper'] and
            row['volume_ratio'] > 1.5  # Above average volume
        )
        
        # Higher timeframe alignment (if available)
        htf_aligned = True
        if 'htf_trend' in self.data.columns:
            htf_aligned = row['htf_trend'] > 0
            
        # Combined entry signals with reasons
        if trend_condition and momentum_entry and htf_aligned:
            return True, "Momentum entry with trend alignment"
        elif trend_condition and volatility_entry and htf_aligned:
            return True, "Volatility breakout with volume confirmation"
            
        return False, ""
        
    def exit_signal(self, i, buy_price, highest_price):
        """Dynamic exit logic based on multiple factors"""
        if i < 2:
            return False, ""
            
        row = self.data.iloc[i]
        prev_row = self.data.iloc[i-1]
        current_price = row['Close']
        
        # Get ATR for dynamic stops
        atr = row['atr']
        
        # 1. Take profit based on volatility
        profit_threshold = min(self.atr_multiplier * atr / buy_price, 0.03)  # Cap at 3%
        if (current_price - buy_price) / buy_price >= profit_threshold:
            return True, f"Take profit target reached ({profit_threshold:.2%})"
            
        # 2. Trailing stop based on ATR
        trailing_stop = highest_price - (self.atr_multiplier * atr)
        if current_price < trailing_stop:
            loss_pct = (highest_price - current_price) / highest_price
            return True, f"Trailing stop hit ({loss_pct:.2%} from high)"
            
        # 3. Technical signal reversal
        if row['rsi'] > 70 and prev_row['rsi'] < row['rsi']:
            return True, "RSI overbought and increasing"
            
        if row['macd_diff'] < 0 and prev_row['macd_diff'] > 0:
            return True, "MACD crossed below signal line"
            
        # 4. Fixed stop loss from entry (risk management)
        if current_price < self.initial_stop:
            loss_pct = (buy_price - current_price) / buy_price
            return True, f"Initial stop loss hit ({loss_pct:.2%})"
            
        return False, ""

    def run_backtest(self, start_date, end_date):
        # Overall performance tracking
        total_start_time = time.time()
        self.perf_metrics = {'start_time': total_start_time}
        
        print(f"Starting backtest on {self.symbol} from {start_date} to {end_date}")
        print("All times are in UTC")
        if self.fast_mode:
            print("RUNNING IN FAST MODE - Some features are disabled for speed")
        print(f"Initial portfolio: ${self.portfolio_value:.2f}")
        
        # Data fetch timing
        data_start_time = time.time()
        self.data = self.get_minute_data(start_date, end_date)
        data_time = time.time() - data_start_time
        self.perf_metrics['data_fetch_time'] = data_time
        
        print(f"Data Fetched successfully in {data_time:.2f} seconds")
        
        # Double-check for duplicate indices before continuing
        duplicate_indices = self.data.index.duplicated().sum()
        if duplicate_indices > 0:
            print(f"Removing {duplicate_indices} duplicate timestamps from data")
            self.data = self.data[~self.data.index.duplicated(keep='first')]
        
        self.add_indicators()
        
        buy_price = None
        highest_price = None
        entry_reason = ""
        
        # Track portfolio value over time (reduce sampling rate in fast mode)
        portfolio_values = [self.portfolio_value]
        portfolio_dates = [self.data.index[0]]
        
        # Progress bar for the backtest loop
        simulation_start_time = time.time()
        print(f"Running simulation with {len(self.data)} data points...")
        
        # Determine portfolio tracking frequency
        track_interval = 100 if self.fast_mode else 10
        save_interval = 1000 if self.fast_mode else 100
        
        # Use tqdm for progress bar
        for i in tqdm(range(len(self.data))):
            current_price = self.data['Close'].iloc[i]
            current_time = self.data.index[i]
            
            # Update asset value
            if self.quantity > 0:
                self.asset_value = self.quantity * current_price
            
            # No position - check for entry
            if buy_price is None and self.position == 0 and (i - self.last_exit_index) >= self.reentry_delay:
                should_enter, reason = self.entry_signal(i)
                if should_enter and self.portfolio_value > 100:
                    buy_price = current_price
                    highest_price = current_price
                    entry_reason = reason
                    self.place_order('buy', buy_price, current_time, reason)
                    self.position = 1
                    
            # Have position - check for exit
            elif buy_price is not None:
                highest_price = max(highest_price, current_price)
                
                should_exit, reason = self.exit_signal(i, buy_price, highest_price)
                if should_exit:
                    self.place_order('sell', current_price, current_time, reason)
                    profit_pct = (current_price - buy_price) / buy_price
                    print(f"Trade closed: {profit_pct:.2%} profit/loss - {reason}")
                    
                    # Track best/worst trades
                    if self.max_profit_trade is None or profit_pct > self.max_profit_trade['profit']:
                        self.max_profit_trade = {'profit': profit_pct, 'time': current_time, 'reason': reason}
                    if profit_pct < 0 and (self.max_loss_trade is None or profit_pct < self.max_loss_trade['loss']):
                        self.max_loss_trade = {'loss': profit_pct, 'time': current_time, 'reason': reason}
                        
                    buy_price = None
                    highest_price = None
                    self.position = 0
                    self.last_exit_index = i
            
            # Track portfolio value (less frequently for performance)
            if i % track_interval == 0 or i == len(self.data) - 1:
                total_value = self.portfolio_value + self.asset_value
                portfolio_values.append(total_value)
                portfolio_dates.append(current_time)
            
            # Save portfolio value periodically (even less frequently)
            if i % save_interval == 0 or i == len(self.data) - 1:
                total_value = self.portfolio_value + self.asset_value
                if i % track_interval != 0:  # Avoid duplicates
                    portfolio_values.append(total_value)
                    portfolio_dates.append(current_time)
                # Only save to CSV at larger intervals
                pd.DataFrame({'time': portfolio_dates, 'value': portfolio_values}).to_csv('portfolio_values.csv', index=False)

        # Close any open position at the end
        if buy_price is not None:
            final_price = self.data['Close'].iloc[-1]
            self.place_order('sell', final_price, self.data.index[-1], "End of backtest")
            print(f"Final position closed at ${final_price:.2f}")
        
        simulation_time = time.time() - simulation_start_time
        self.perf_metrics['simulation_time'] = simulation_time
        print(f"Simulation completed in {simulation_time:.2f} seconds")
        
        # Performance reporting
        total_value = self.portfolio_value + self.asset_value
        print(f"\nFinal portfolio value: ${total_value:.2f}")
        print(f"Total P&L: ${(total_value - self.initial_portfolio_value):.2f}")
        print(f"Total P&L %: {((total_value - self.initial_portfolio_value) / self.initial_portfolio_value) * 100:.2f}%")
        
        if self.max_profit_trade:
            print(f"Most profitable trade: {self.max_profit_trade['profit'] * 100:.2f}% on {self.max_profit_trade['time']} - {self.max_profit_trade['reason']}")
        if self.max_loss_trade:
            print(f"Most loss-making trade: {self.max_loss_trade['loss'] * 100:.2f}% on {self.max_loss_trade['time']} - {self.max_loss_trade['reason']}")
        
        # Calculate advanced performance metrics (skip some calculations in fast mode)
        metrics_start_time = time.time()
        self.calculate_performance_metrics(portfolio_values, portfolio_dates)
        metrics_time = time.time() - metrics_start_time
        self.perf_metrics['metrics_calculation_time'] = metrics_time
        
        # Save trades
        self.save_trades_to_csv()
        
        # Skip plotting in fast mode unless explicitly requested
        if not self.fast_mode:
            plot_start_time = time.time()
            self.plot_results(portfolio_dates, portfolio_values)
            plot_time = time.time() - plot_start_time
            self.perf_metrics['plot_time'] = plot_time
        
        # Overall performance
        total_time = time.time() - total_start_time
        self.perf_metrics['total_time'] = total_time
        
        # Print performance breakdown
        print("\n=== PERFORMANCE BREAKDOWN ===")
        print(f"Data fetching: {self.perf_metrics.get('data_fetch_time', 0):.2f}s ({self.perf_metrics.get('data_fetch_time', 0)/total_time*100:.1f}%)")
        print(f"Indicator calculation: {self.perf_metrics.get('indicator_calculation_time', 0):.2f}s ({self.perf_metrics.get('indicator_calculation_time', 0)/total_time*100:.1f}%)")
        print(f"Simulation: {self.perf_metrics.get('simulation_time', 0):.2f}s ({self.perf_metrics.get('simulation_time', 0)/total_time*100:.1f}%)")
        print(f"Metrics calculation: {self.perf_metrics.get('metrics_calculation_time', 0):.2f}s ({self.perf_metrics.get('metrics_calculation_time', 0)/total_time*100:.1f}%)")
        if not self.fast_mode:
            print(f"Plotting: {self.perf_metrics.get('plot_time', 0):.2f}s ({self.perf_metrics.get('plot_time', 0)/total_time*100:.1f}%)")
        print(f"Total backtest time: {total_time:.2f}s")
        print("===========================\n")

    def calculate_performance_metrics(self, portfolio_values, portfolio_dates):
        """Calculate performance metrics with optimizations for speed"""
        print("Calculating performance metrics...")
        
        # Convert to numpy array for faster calculations
        portfolio_array = np.array(portfolio_values)
        
        # Skip daily resampling in fast mode - just use the raw data points
        if self.fast_mode:
            # Calculate basic metrics only
            total_return = (portfolio_array[-1] / portfolio_array[0]) - 1
            max_drawdown = self.calculate_max_drawdown(portfolio_array)
            
            # Win/loss metrics (simplified)
            sell_trades = [t for t in self.trades if t['side'] == 'sell']
            win_trades = [t for t in sell_trades if t.get('buy_price') is not None and t['price'] > t['buy_price']]
            total_trades = len(sell_trades)
            win_rate = len(win_trades) / total_trades if total_trades > 0 else 0
            
            print("\n=== BASIC PERFORMANCE METRICS (FAST MODE) ===")
            print(f"Total Return: {total_return:.2%}")
            print(f"Maximum Drawdown: {max_drawdown:.2%}")
            print(f"Win Rate: {win_rate:.2%}")
            print(f"Total Trades: {total_trades}")
            print("=============================================\n")
            return
        
        # For full mode, calculate all metrics
        # ...existing code for full performance metrics calculation...
        
    def calculate_max_drawdown(self, portfolio_array):
        """Fast calculation of maximum drawdown"""
        max_dd = 0
        peak = portfolio_array[0]
        
        for value in portfolio_array:
            if value > peak:
                peak = value
            else:
                dd = (peak - value) / peak
                max_dd = max(max_dd, dd)
                
        return max_dd

    def save_trades_to_csv(self):
        df = pd.DataFrame(self.trades)
        df.to_csv('trades.csv', index=False)
        print("Trades saved to trades.csv")

    def plot_results(self, dates, portfolio_values):
        # ...existing code...
        # Add more visualization components like drawdown chart and trade distribution
        fig = go.Figure()

        # Main price chart with candlesticks
        fig.add_trace(go.Candlestick(
            x=self.data.index,
            open=self.data['Open'],
            high=self.data['High'],
            low=self.data['Low'],
            close=self.data['Close'],
            name='Price'
        ))

        # Add Bollinger Bands
        fig.add_trace(go.Scatter(
            x=self.data.index,
            y=self.data['bb_upper'],
            mode='lines',
            line=dict(width=1, color='rgba(173, 204, 255, 0.7)'),
            name='BB Upper'
        ))
        
        fig.add_trace(go.Scatter(
            x=self.data.index,
            y=self.data['bb_lower'],
            mode='lines',
            line=dict(width=1, color='rgba(173, 204, 255, 0.7)'),
            fill='tonexty',
            fillcolor='rgba(173, 204, 255, 0.2)',
            name='BB Lower'
        ))

        # Add trades with reason annotations
        buy_trades = [trade for trade in self.trades if trade['side'] == 'buy']
        sell_trades = [trade for trade in self.trades if trade['side'] == 'sell']

        fig.add_trace(go.Scatter(
            x=[trade['time'] for trade in buy_trades],
            y=[trade['price'] for trade in buy_trades],
            mode='markers',
            marker=dict(color='green', size=10, symbol='triangle-up'),
            name='Buy Trades',
            hovertext=[f"Buy: ${trade['price']:.2f}<br>Reason: {trade.get('reason', '')}" for trade in buy_trades]
        ))

        fig.add_trace(go.Scatter(
            x=[trade['time'] for trade in sell_trades],
            y=[trade['price'] for trade in sell_trades],
            mode='markers',
            marker=dict(color='red', size=10, symbol='triangle-down'),
            name='Sell Trades',
            hovertext=[f"Sell: ${trade['price']:.2f}<br>Reason: {trade.get('reason', '')}" for trade in sell_trades]
        ))

        # Portfolio value chart
        fig.add_trace(go.Scatter(
            x=dates,
            y=portfolio_values,
            mode='lines',
            name='Portfolio Value',
            yaxis='y2',
            line=dict(color='rgb(66, 114, 215)', width=2)
        ))

        # Add best and worst trades
        if self.max_profit_trade:
            fig.add_trace(go.Scatter(
                x=[self.max_profit_trade['time']],
                y=[self.data.loc[self.max_profit_trade['time'], 'Close']],
                mode='markers',
                marker=dict(color='blue', size=15, symbol='star'),
                name='Best Trade',
                hovertext=f"Best: +{self.max_profit_trade['profit']*100:.2f}%<br>{self.max_profit_trade.get('reason', '')}"
            ))

        if self.max_loss_trade:
            fig.add_trace(go.Scatter(
                x=[self.max_loss_trade['time']],
                y=[self.data.loc[self.max_loss_trade['time'], 'Close']],
                mode='markers',
                marker=dict(color='orange', size=15, symbol='star'),
                name='Worst Trade',
                hovertext=f"Worst: {self.max_loss_trade['loss']*100:.2f}%<br>{self.max_loss_trade.get('reason', '')}"
            ))

        # Market regime visualization
        regime_colors = {'low_volatility': 'rgba(0, 255, 0, 0.2)', 
                        'normal': 'rgba(255, 255, 0, 0.2)', 
                        'high_volatility': 'rgba(255, 0, 0, 0.2)'}
                        
        # Create background colors for different market regimes
        for regime in ['low_volatility', 'normal', 'high_volatility']:
            regime_periods = []
            in_regime = False
            start_idx = None
            
            for i, row in self.data.iterrows():
                if row['market_regime'] == regime and not in_regime:
                    in_regime = True
                    start_idx = i
                elif row['market_regime'] != regime and in_regime:
                    in_regime = False
                    regime_periods.append((start_idx, i))
                    
            if in_regime:  # Handle case where regime continues until the end
                regime_periods.append((start_idx, self.data.index[-1]))
                
            # Add colored background shapes for each regime period
            for start, end in regime_periods:
                fig.add_shape(
                    type="rect",
                    x0=start,
                    x1=end,
                    y0=0,
                    y1=1,
                    yref="paper",
                    fillcolor=regime_colors[regime],
                    opacity=0.3,
                    layer="below",
                    line=dict(width=0)
                )

        # Layout configuration
        fig.update_layout(
            title=f'{self.symbol} Scalping Strategy Backtest Results',
            xaxis_title='Time',
            yaxis_title='Price',
            yaxis2=dict(
                title='Portfolio Value ($)',
                overlaying='y',
                side='right'
            ),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            height=800,
            hovermode='closest'
        )

        # Create a second figure for technical indicators
        fig2 = go.Figure()
        
        # RSI subplot
        fig2.add_trace(go.Scatter(
            x=self.data.index,
            y=self.data['rsi'],
            mode='lines',
            name='RSI'
        ))
        
        # Add RSI overbought/oversold lines
        fig2.add_shape(
            type="line",
            x0=self.data.index[0],
            x1=self.data.index[-1],
            y0=70,
            y1=70,
            line=dict(color="red", width=1, dash="dash")
        )
        
        fig2.add_shape(
            type="line",
            x0=self.data.index[0],
            x1=self.data.index[-1],
            y0=30,
            y1=30,
            line=dict(color="green", width=1, dash="dash")
        )
        
        # MACD subplot
        fig2.add_trace(go.Scatter(
            x=self.data.index,
            y=self.data['macd'],
            mode='lines',
            name='MACD',
            yaxis="y2"
        ))
        
        fig2.add_trace(go.Scatter(
            x=self.data.index,
            y=self.data['macd_signal'],
            mode='lines',
            name='Signal',
            yaxis="y2"
        ))
        
        # MACD histogram
        colors = ['green' if val >= 0 else 'red' for val in self.data['macd_diff']]
        fig2.add_trace(go.Bar(
            x=self.data.index,
            y=self.data['macd_diff'],
            name='MACD Histogram',
            marker_color=colors,
            yaxis="y2"
        ))
        
        # ADX subplot
        fig2.add_trace(go.Scatter(
            x=self.data.index,
            y=self.data['adx'],
            mode='lines',
            name='ADX',
            yaxis="y3"
        ))
        
        fig2.add_trace(go.Scatter(
            x=self.data.index,
            y=self.data['di_plus'],
            mode='lines',
            name='DI+',
            yaxis="y3",
            line=dict(color="green")
        ))
        
        fig2.add_trace(go.Scatter(
            x=self.data.index,
            y=self.data['di_minus'],
            mode='lines',
            name='DI-',
            yaxis="y3",
            line=dict(color="red")
        ))
        
        # Volume subplot
        fig2.add_trace(go.Bar(
            x=self.data.index,
            y=self.data['Volume'],
            name='Volume',
            marker_color='rgba(100, 100, 255, 0.5)',
            yaxis="y4"
        ))
        
        # Layout for technical indicators
        fig2.update_layout(
            title='Technical Indicators',
            height=800,
            yaxis=dict(
                title="RSI",
                domain=[0.75, 1.0]
            ),
            yaxis2=dict(
                title="MACD",
                domain=[0.5, 0.75]
            ),
            yaxis3=dict(
                title="ADX",
                domain=[0.25, 0.5]
            ),
            yaxis4=dict(
                title="Volume",
                domain=[0, 0.25]
            ),
            legend=dict(orientation="h")
        )

        fig.show()
        fig2.show()


if __name__ == "__main__":
    symbol = 'DEXE/USDT'  
    hkt = pytz.timezone('Asia/Hong_Kong')
    utc = pytz.utc

    print(f"The code runs in your local time equivalent but all times are in UTC")
    
    import sys
    fast_mode = '--fast' in sys.argv
    use_cache = '--no-cache' not in sys.argv
    days = 7 if fast_mode else 30  # Default to 7 days in fast mode for speed
    
    # Parse custom time period if specified
    for arg in sys.argv:
        if arg.startswith('--days='):
            try:
                days = int(arg.split('=')[1])
                print(f"Using custom time period: {days} days")
            except:
                pass
    
    # Use shorter backtest period for faster testing
    start_date_hkt = datetime.now(hkt) - timedelta(days=days)
    start_date_utc = start_date_hkt.astimezone(utc)
    start_date_str = start_date_utc.strftime('%Y-%m-%d %H:%M')
    end_date_hkt = datetime.now(hkt)
    end_date_utc = end_date_hkt.astimezone(utc)
    end_date_str = end_date_utc.strftime('%Y-%m-%d %H:%M')
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d %H:%M')
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d %H:%M')
    
    strategy = ScalpingStrategy(
        symbol=symbol,
        initial_portfolio_value=10000,
        fee_rate=0.001,
        risk_per_trade=0.01,
        reentry_delay=5,
        max_position_pct=0.2,
        rsi_period=14,
        bb_period=20,
        atr_period=14,
        atr_multiplier=2.0,
        market_regime_lookback=100,
        use_cached_data=use_cache,
        use_higher_tf=not fast_mode,
        fast_mode=fast_mode
    )
    
    print("Fast mode:" if fast_mode else "Full mode:", 
          "Will use data caching" if use_cache else "Will not use data caching")
          
    strategy.run_backtest(start_date, end_date)