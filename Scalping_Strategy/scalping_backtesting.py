import pandas as pd
import ccxt
import time
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import pytz
from datetime import timedelta

class ScalpingStrategy:
    def __init__(self, symbol, initial_portfolio_value=10, profit_threshold=0.001, stop_loss_threshold=0.001):
        self.symbol = symbol
        self.profit_threshold = profit_threshold
        self.stop_loss_threshold = stop_loss_threshold
        self.exchange = ccxt.binance()
        self.data = None
        self.trades = []
        self.portfolio_value = initial_portfolio_value
        self.initial_portfolio_value = initial_portfolio_value
        self.position = 0  # Track the current position (0 for no position, 1 for long, -1 for short)
        self.quantity = 0  # Track the quantity of the asset being traded
        self.max_profit_trade = None
        self.max_loss_trade = None

    def place_order(self, side, price, timestamp):
        print(f"Simulating {side} order for {self.quantity} {self.symbol} at {price} on {timestamp}")
        self.trades.append({'side': side, 'price': price, 'time': timestamp})
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
        while since < end:
            chunk = self.exchange.fetch_ohlcv(self.symbol, timeframe=interval, since=since, limit=1000)
            if not chunk:
                break
            since = chunk[-1][0] + 1
            data.extend(chunk)
            time.sleep(self.exchange.rateLimit / 1000)  # Respect the rate limit
        return data

    def run_backtest(self, start_date, end_date):
        start_time = time.time()
        print("Starting backtest")
        print("All times are in UTC")
        self.data = self.get_minute_data(start_date, end_date)
        print("Data Fetched successfully")
        buy_price = None
        highest_price = None
        portfolio_values = [self.portfolio_value]  # Track portfolio value over time
        
        # Remove duplicate labels
        self.data = self.data[~self.data.index.duplicated(keep='first')]

        for i in range(len(self.data)):
            current_price = self.data['Close'].iloc[i]
            current_time = self.data.index[i]
            
            if buy_price is None:
                buy_price = current_price
                highest_price = current_price
                self.quantity = self.portfolio_value / buy_price
                self.place_order('buy', buy_price, current_time)
                self.position = 1
            else:
                highest_price = max(highest_price, current_price)
                loss = (highest_price - current_price) / highest_price
                
                if loss >= self.stop_loss_threshold:
                    self.place_order('sell', current_price, current_time)
                    self.portfolio_value = self.quantity * current_price
                    portfolio_values.append(self.portfolio_value)  # Update portfolio value
                    print(f"Trade closed with loss: {loss * 100:.2f}%")
                    if self.max_loss_trade is None or loss > self.max_loss_trade['loss']:
                        self.max_loss_trade = {'loss': loss, 'time': current_time}
                    buy_price = None
                    highest_price = None
                    self.position = 0
                elif (current_price - buy_price) / buy_price >= self.profit_threshold:
                    highest_price = current_price  # Update highest price to current price
                elif (current_price - buy_price) / buy_price < self.profit_threshold:
                    self.place_order('sell', current_price, current_time)
                    self.portfolio_value = self.quantity * current_price
                    portfolio_values.append(self.portfolio_value)  # Update portfolio value
                    print(f"Trade closed with profit: {(current_price - buy_price) / buy_price * 100:.2f}%")
                    if self.max_profit_trade is None or (current_price - buy_price) / buy_price > self.max_profit_trade['profit']:
                        self.max_profit_trade = {'profit': (current_price - buy_price) / buy_price, 'time': current_time}
                    buy_price = None
                    highest_price = None
                    self.position = 0

        # Unload everything at the end_date
        if buy_price is not None:
            self.place_order('sell', self.data['Close'].iloc[-1], self.data.index[-1])
            self.portfolio_value = self.quantity * self.data['Close'].iloc[-1]
            portfolio_values.append(self.portfolio_value)  # Update portfolio value
        
        print(f"Final portfolio value: ${self.portfolio_value:.2f}")
        print(f"Total P&L: ${(self.portfolio_value - self.initial_portfolio_value):.2f}")
        
        if self.max_profit_trade:
            print(f"Most profitable trade: {self.max_profit_trade['profit'] * 100:.2f}% on {self.max_profit_trade['time']}")
        if self.max_loss_trade:
            print(f"Most loss-making trade: {self.max_loss_trade['loss'] * 100:.2f}% on {self.max_loss_trade['time']}")
        
        self.save_trades_to_csv()
        self.plot_results(portfolio_values)
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"Backtest completed in {elapsed_time:.2f} seconds")


    def save_trades_to_csv(self):
        df = pd.DataFrame(self.trades)
        df.to_csv('trades.csv', index=False)
        print("Trades saved to trades.csv")

    def plot_results(self, portfolio_values):
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

        fig.update_layout(title='Scalping Strategy Backtest for the symbol', xaxis_title='Time', yaxis_title='Price')

        fig.show()


if __name__ == "__main__":
    symbol = 'BTC/USDT'
    hkt = pytz.timezone('Asia/Hong_Kong')
    utc = pytz.utc

    print(f"The code runs in your local time equivalent but all times are in UTC")
    # Start date is 1 hour before the current time in HKT
    #Change the hours below to your desired start time and even chage hours to days
    start_date_hkt = datetime.now(hkt) - timedelta(days=365)
    start_date_utc = start_date_hkt.astimezone(utc)
    start_date_str = start_date_utc.strftime('%Y-%m-%d %H:%M')
    end_date_hkt = datetime.now(hkt)
    end_date_utc = end_date_hkt.astimezone(utc)
    end_date_str = end_date_utc.strftime('%Y-%m-%d %H:%M')
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d %H:%M')
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d %H:%M')
    strategy = ScalpingStrategy(symbol)
    strategy.run_backtest(start_date, end_date)