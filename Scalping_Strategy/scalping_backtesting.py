import pandas as pd
import ccxt
import time
import numpy as np
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import pytz
from datetime import timedelta

class ScalpingStrategy:
    def __init__(self, symbol, initial_portfolio_value=10000, profit_threshold=0.002, stop_loss_threshold=0.005, 
                 fee_rate=0.001, risk_per_trade=0.005, reentry_delay=15, max_position_pct=0.2,
                 short_ma=5, long_ma=20, min_volatility=0.001):
        self.symbol = symbol
        self.risk_per_trade = risk_per_trade  # Reduced to 0.5% from 2%
        self.profit_threshold = profit_threshold  # Increased to 0.2% from 0.1%
        self.stop_loss_threshold = stop_loss_threshold  # Increased to 0.5% from 0.1%
        self.fixed_stop_loss = 0.01  # Added 1% fixed stop loss from entry
        self.exchange = ccxt.binance()
        self.fee_rate = fee_rate
        self.max_position_pct = max_position_pct  # Maximum position size as % of portfolio
        self.data = None
        self.trades = []
        self.reentry_delay = reentry_delay  # Increased to 15 from 5
        self.last_exit_index = -self.reentry_delay  # Initialize to allow immediate entry
        self.portfolio_value = initial_portfolio_value
        self.initial_portfolio_value = initial_portfolio_value
        self.position = 0  # Track the current position (0 for no position, 1 for long, -1 for short)
        self.quantity = 0  # Track the quantity of the asset being traded
        self.max_profit_trade = None
        self.max_loss_trade = None
        self.buy_prices = []  # Track buy prices for performance metrics
        self.asset_value = 0  # Track the value of held assets
        self.short_ma = short_ma  # Short moving average window
        self.long_ma = long_ma    # Long moving average window
        self.min_volatility = min_volatility  # Minimum volatility filter

    def place_order(self, side, price, timestamp):
        if side == 'buy':
            # Calculate quantity based on position sizing while respecting fee
            max_purchase = self.portfolio_value * (1 - self.fee_rate)
            self.quantity = min(self.calculate_position_size(price), max_purchase / price)
            
            # Update portfolio (reduce cash by purchase amount including fees)
            purchase_cost = self.quantity * price * (1 + self.fee_rate)
            self.portfolio_value -= purchase_cost
            self.asset_value = self.quantity * price
            
            # Track buy price for performance metrics
            self.buy_prices.append(price)
        else:  # sell
            # Calculate sale proceeds after fees
            sale_proceeds = self.quantity * price * (1 - self.fee_rate)
            
            # Add proceeds to portfolio value
            self.portfolio_value += sale_proceeds
            self.asset_value = 0
            self.quantity = 0
            
        total_value = self.portfolio_value + self.asset_value
        print(f"Simulating {side} order for {self.quantity} {self.symbol} at {price} on {timestamp}")
        print(f"  Cash: ${self.portfolio_value:.2f}, Asset Value: ${self.asset_value:.2f}, Total: ${total_value:.2f}")
        
        self.trades.append({
            'side': side, 
            'price': price, 
            'time': timestamp,
            'quantity': self.quantity,
            'fee': (price * self.quantity * self.fee_rate),
            'buy_price': self.buy_prices[-1] if side == 'sell' and self.buy_prices else None,
            'portfolio_value': total_value  # Track total portfolio value after each trade
        })
        return True
   
    def get_minute_data(self, start_date, end_date, interval='1m'):
        since = self.exchange.parse8601(start_date.isoformat())
        end = self.exchange.parse8601(end_date.isoformat())
        data = []

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            chunk_size = (end - since) // 4
            for i in range(4):
                chunk_start = since + i * chunk_size
                chunk_end = min(since + (i + 1) * chunk_size, end)
                futures.append(executor.submit(self.fetch_data_chunk, chunk_start, chunk_end, interval))

            for future in futures:
                data.extend(future.result())

        frame = pd.DataFrame(data, columns=['Time', 'Open', 'High', 'Low', 'Close', 'Volume'])
        frame = frame.set_index('Time')
        frame.index = pd.to_datetime(frame.index, unit='ms')
        frame = frame.astype(float)
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
        """Calculate position size based on risk per trade with conservative limits"""
        # Calculate based on risk
        account_risk = (self.portfolio_value + self.asset_value) * self.risk_per_trade
        stop_loss_amount = price * self.stop_loss_threshold
        risk_based_size = account_risk / stop_loss_amount if stop_loss_amount > 0 else 0
        
        # Cap at a percentage of portfolio regardless of risk calculation
        max_position_size = (self.portfolio_value + self.asset_value) * self.max_position_pct / price
        
        # Available cash constraint
        cash_constraint = self.portfolio_value / price
        
        # Return the smallest of the three constraints
        return min(
            risk_based_size,    # Risk-based sizing
            max_position_size,  # Percentage-based cap
            cash_constraint     # Available cash constraint
        )

    def add_indicators(self):
        """Add moving averages and volatility filter to self.data"""
        self.data['short_ma'] = self.data['Close'].rolling(self.short_ma).mean()
        self.data['long_ma'] = self.data['Close'].rolling(self.long_ma).mean()
        self.data['returns'] = self.data['Close'].pct_change()
        self.data['volatility'] = self.data['returns'].rolling(self.long_ma).std()

    def entry_signal(self, i):
        """Entry signal: price above both MAs and volatility above threshold"""
        if i < self.long_ma:
            return False
        row = self.data.iloc[i]
        price = row['Close']
        if (
            price > row['short_ma'] > row['long_ma'] and
            row['volatility'] > self.min_volatility
        ):
            return True
        return False

    def run_backtest(self, start_date, end_date):
        start_time = time.time()
        print("Starting backtest")
        print("All times are in UTC")
        print(f"Initial portfolio: ${self.portfolio_value:.2f}")
        
        self.data = self.get_minute_data(start_date, end_date)
        print("Data Fetched successfully")
        self.data = self.data[~self.data.index.duplicated(keep='first')]
        self.add_indicators()  # Add indicators for entry/exit
        buy_price = None
        highest_price = None
        
        # Track portfolio value over time (cash + assets)
        portfolio_values = [self.portfolio_value]
        portfolio_dates = [self.data.index[0]]

        for i in range(len(self.data)):
            current_price = self.data['Close'].iloc[i]
            current_time = self.data.index[i]
            
            # Update asset value for portfolio tracking
            if self.quantity > 0:
                self.asset_value = self.quantity * current_price
            
            # Entry logic: use entry_signal instead of just time delay
            if buy_price is None and self.position == 0 and (i - self.last_exit_index) >= self.reentry_delay:
                # Only enter if we have sufficient portfolio value
                if self.portfolio_value > 100 and self.entry_signal(i):
                    buy_price = current_price
                    highest_price = current_price
                    self.place_order('buy', buy_price, current_time)
                    self.position = 1
            elif buy_price is not None:
                highest_price = max(highest_price, current_price)
                
                # Calculate trailing stop loss (relative to highest price seen)
                trailing_loss = (highest_price - current_price) / highest_price
                
                # Calculate fixed stop loss (relative to buy price)
                fixed_loss = (buy_price - current_price) / buy_price
                
                # Take profit condition
                if (current_price - buy_price) / buy_price >= self.profit_threshold:
                    self.place_order('sell', current_price, current_time)
                    print(f"Trade closed with profit: {(current_price - buy_price) / buy_price * 100:.2f}%")
                    if self.max_profit_trade is None or (current_price - buy_price) / buy_price > self.max_profit_trade['profit']:
                        self.max_profit_trade = {'profit': (current_price - buy_price) / buy_price, 'time': current_time}
                    buy_price = None
                    highest_price = None
                    self.position = 0
                    self.last_exit_index = i  # Update the last exit index
                
                # Stop loss condition - trigger on either trailing or fixed stop loss
                elif trailing_loss >= self.stop_loss_threshold or fixed_loss >= self.fixed_stop_loss:
                    self.place_order('sell', current_price, current_time)
                    loss_pct = max(trailing_loss, fixed_loss)
                    print(f"Trade closed with loss: {loss_pct * 100:.2f}%")
                    if self.max_loss_trade is None or loss_pct > self.max_loss_trade['loss']:
                        self.max_loss_trade = {'loss': loss_pct, 'time': current_time}
                    buy_price = None
                    highest_price = None
                    self.position = 0
                    self.last_exit_index = i  # Update the last exit index
            
            # Track portfolio value at each step
            total_value = self.portfolio_value + self.asset_value
            portfolio_values.append(total_value)
            portfolio_dates.append(current_time)
            # Save portfolio value for dashboard
            if i % 10 == 0 or i == len(self.data) - 1:
                pd.DataFrame({'time': portfolio_dates, 'value': portfolio_values}).to_csv('portfolio_values.csv', index=False)

        # Unload everything at the end_date
        if buy_price is not None:
            final_price = self.data['Close'].iloc[-1]
            self.place_order('sell', final_price, self.data.index[-1])
            print(f"Final position closed at ${final_price:.2f}")
        
        # Final portfolio calculation
        total_value = self.portfolio_value + self.asset_value
        
        print(f"\nFinal portfolio value: ${total_value:.2f}")
        print(f"Total P&L: ${(total_value - self.initial_portfolio_value):.2f}")
        print(f"Total P&L %: {((total_value - self.initial_portfolio_value) / self.initial_portfolio_value) * 100:.2f}%")
        
        if self.max_profit_trade:
            print(f"Most profitable trade: {self.max_profit_trade['profit'] * 100:.2f}% on {self.max_profit_trade['time']}")
        if self.max_loss_trade:
            print(f"Most loss-making trade: {self.max_loss_trade['loss'] * 100:.2f}% on {self.max_loss_trade['time']}")
        
        # Calculate performance metrics
        self.calculate_performance_metrics(portfolio_values)
        
        self.save_trades_to_csv()
        self.plot_results(portfolio_dates, portfolio_values)
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"Backtest completed in {elapsed_time:.2f} seconds")

    def calculate_performance_metrics(self, portfolio_values):
        """Calculate various trading performance metrics"""
        # Convert to numpy array for easier calculations
        portfolio_array = np.array(portfolio_values)
        
        # Calculate returns
        returns = np.diff(portfolio_array) / portfolio_array[:-1]
        
        # Sharpe ratio (assuming risk-free rate of 0)
        if len(returns) > 1 and np.std(returns) > 0:
            sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252)  # Annualized
        else:
            sharpe_ratio = 0
        
        # Maximum drawdown
        max_drawdown = 0
        peak = portfolio_array[0]
        for value in portfolio_array:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak
            max_drawdown = max(max_drawdown, drawdown)
        
        # Win/loss ratio with fee consideration
        sell_trades = [t for t in self.trades if t['side'] == 'sell']
        # A winning trade must exceed buy price plus fees
        wins = [t for t in sell_trades if t['price'] > (t.get('buy_price', 0) * (1 + self.fee_rate * 2))]
        losses = [t for t in sell_trades if t['price'] <= (t.get('buy_price', 0) * (1 + self.fee_rate * 2))]
        win_ratio = len(wins) / max(1, len(sell_trades))  # Avoid division by zero
        
        # Calculate average profit/loss per trade
        total_profit = sum([(t['price'] - t.get('buy_price', 0)) * t.get('quantity', 0) 
                          for t in sell_trades if t.get('buy_price') is not None])
        avg_profit_per_trade = total_profit / max(1, len(sell_trades))
        
        # Calculate expectancy (average R multiple)
        r_multiples = []
        for trade in sell_trades:
            if trade.get('buy_price') is not None:
                entry = trade.get('buy_price', 0)
                exit_price = trade['price']
                risk = entry * self.stop_loss_threshold  # Risk per share
                if risk > 0:
                    r = (exit_price - entry) / risk  # R multiple
                    r_multiples.append(r)
        
        expectancy = np.mean(r_multiples) if r_multiples else 0
        
        # Calculate profit factor
        gross_profit = sum([(t['price'] - t.get('buy_price', 0)) * t.get('quantity', 0) 
                          for t in wins if t.get('buy_price') is not None])
        gross_loss = abs(sum([(t['price'] - t.get('buy_price', 0)) * t.get('quantity', 0) 
                            for t in losses if t.get('buy_price') is not None]))
        profit_factor = gross_profit / max(1, gross_loss)  # Avoid division by zero
        
        print("\n=== PERFORMANCE METRICS ===")
        print(f"Sharpe Ratio: {sharpe_ratio:.4f}")
        print(f"Maximum Drawdown: {max_drawdown:.2%}")
        print(f"Win Ratio: {win_ratio:.2%}")
        print(f"Expectancy (Average R): {expectancy:.4f}")
        print(f"Profit Factor: {profit_factor:.4f}")
        print(f"Average Profit per Trade: ${avg_profit_per_trade:.2f}")
        print(f"Total Trades: {len(sell_trades)}")
        print("===========================\n")

    def save_trades_to_csv(self):
        df = pd.DataFrame(self.trades)
        df.to_csv('trades.csv', index=False)
        print("Trades saved to trades.csv")

    def plot_results(self, dates, portfolio_values):
        print("Generating Results Visual")
        # Create the main figure with market data and trades
        fig = go.Figure()

        fig.add_trace(go.Candlestick(
            x=self.data.index,
            open=self.data['Open'],
            high=self.data['High'],
            low=self.data['Low'],
            close=self.data['Close'],
            name='Market Data'
        ))

        buy_trades = [trade for trade in self.trades if trade['side'] == 'buy']
        sell_trades = [trade for trade in self.trades if trade['side'] == 'sell']

        fig.add_trace(go.Scatter(
            x=[trade['time'] for trade in buy_trades],
            y=[trade['price'] for trade in buy_trades],
            mode='markers',
            marker=dict(color='green', size=10),
            name='Buy Trades'
        ))

        fig.add_trace(go.Scatter(
            x=[trade['time'] for trade in sell_trades],
            y=[trade['price'] for trade in sell_trades],
            mode='markers',
            marker=dict(color='red', size=10),
            name='Sell Trades'
        ))

        # Plot portfolio value over time - using accurate tracking
        fig.add_trace(go.Scatter(
            x=dates,
            y=portfolio_values,
            mode='lines',
            name='Portfolio Value',
            yaxis='y2'
        ))

        # Highlight the most profitable and loss-making trades
        if self.max_profit_trade:
            fig.add_trace(go.Scatter(
                x=[self.max_profit_trade['time']],
                y=[self.data.loc[self.max_profit_trade['time'], 'Close']],
                mode='markers',
                marker=dict(color='blue', size=15, symbol='star'),
                name='Most Profitable Trade'
            ))

        if self.max_loss_trade:
            fig.add_trace(go.Scatter(
                x=[self.max_loss_trade['time']],
                y=[self.data.loc[self.max_loss_trade['time'], 'Close']],
                mode='markers',
                marker=dict(color='orange', size=15, symbol='star'),
                name='Most Loss-Making Trade'
            ))

        fig.update_layout(
            title='Scalping Strategy Backtest Results',
            xaxis_title='Time',
            yaxis_title='Price',
            yaxis2=dict(
                title='Portfolio Value',
                overlaying='y',
                side='right'
            ),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )

        fig.show()


if __name__ == "__main__":
    symbol = 'BTC/USDT'  
    hkt = pytz.timezone('Asia/Hong_Kong')
    utc = pytz.utc

    print(f"The code runs in your local time equivalent but all times are in UTC")
    start_date_hkt = datetime.now(hkt) - timedelta(days=136)
    start_date_utc = start_date_hkt.astimezone(utc)
    start_date_str = start_date_utc.strftime('%Y-%m-%d %H:%M')
    end_date_hkt = datetime.now(hkt)
    end_date_utc = end_date_hkt.astimezone(utc)
    end_date_str = end_date_utc.strftime('%Y-%m-%d %H:%M')
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d %H:%M')
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d %H:%M')
    
    strategy = ScalpingStrategy(
        symbol=symbol,
        initial_portfolio_value=10000,  # More reasonable default
        profit_threshold=0.002,
        stop_loss_threshold=0.005,
        fee_rate=0.001,
        risk_per_trade=0.005,
        reentry_delay=15,
        max_position_pct=0.2,
        short_ma=5,
        long_ma=20,
        min_volatility=0.001
    )
    strategy.run_backtest(start_date, end_date)