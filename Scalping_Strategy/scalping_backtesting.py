import pandas as pd
import ccxt
import time
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

class ScalpingStrategy:
    def __init__(self, symbol, initial_portfolio_value=1000, profit_threshold=0.001, stop_loss_threshold=0.001):
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
        print("Starting backtest")
        self.data = self.get_minute_data(start_date, end_date)
        print("Data Fetched successfully")
        buy_price = None
        
        for i in range(len(self.data)):
            current_price = self.data['Close'].iloc[i]
            current_time = self.data.index[i]
            
            if buy_price is None:
                buy_price = current_price
                self.quantity = self.portfolio_value / buy_price
                self.place_order('buy', buy_price, current_time)
                self.position = 1
            else:
                profit = (current_price - buy_price) / buy_price
                loss = (buy_price - current_price) / buy_price
                
                if profit >= self.profit_threshold:
                    self.place_order('sell', current_price, current_time)
                    self.portfolio_value = self.quantity * current_price
                    print(f"Trade closed with profit: {profit * 100:.2f}%")
                    if self.max_profit_trade is None or profit > self.max_profit_trade['profit']:
                        self.max_profit_trade = {'profit': profit, 'time': current_time}
                    buy_price = None
                    self.position = 0
                elif loss >= self.stop_loss_threshold:
                    self.place_order('sell', current_price, current_time)
                    self.portfolio_value = self.quantity * current_price
                    print(f"Trade closed with loss: {loss * 100:.2f}%")
                    if self.max_loss_trade is None or loss > self.max_loss_trade['loss']:
                        self.max_loss_trade = {'loss': loss, 'time': current_time}
                    buy_price = None
                    self.position = 0

        # Unload everything at the end_date
        if buy_price is not None:
            self.place_order('sell', self.data['Close'].iloc[-1], self.data.index[-1])
            self.portfolio_value = self.quantity * self.data['Close'].iloc[-1]
        
        print(f"Final portfolio value: ${self.portfolio_value:.2f}")
        print(f"Total P&L: ${(self.portfolio_value - self.initial_portfolio_value):.2f}")
        
        if self.max_profit_trade:
            print(f"Most profitable trade: {self.max_profit_trade['profit'] * 100:.2f}% on {self.max_profit_trade['time']}")
        if self.max_loss_trade:
            print(f"Most loss-making trade: {self.max_loss_trade['loss'] * 100:.2f}% on {self.max_loss_trade['time']}")
        
        self.plot_results()

    def plot_pnl(self):
        pnl = [0]
        for trade in self.trades:
            if trade['side'] == 'sell':
                pnl.append(pnl[-1] + (trade['price'] - self.trades[self.trades.index(trade) - 1]['price']) * self.quantity)
            else:
                pnl.append(pnl[-1])

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[trade['time'] for trade in self.trades], y=pnl, mode='lines', name='PnL'))
        fig.update_layout(title='Profit and Loss Over Time', xaxis_title='Time', yaxis_title='PnL')
        pio.write_html(fig, file='pnl_over_time.html', auto_open=False)

    def plot_results(self):
        # Create the main figure with market data and trades
        fig = make_subplots(rows=1, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.1, 
                            subplot_titles=('Market Data',),
                            row_heights=[1.0])

        fig.add_trace(go.Candlestick(
            x=self.data.index,
            open=self.data['Open'],
            high=self.data['High'],
            low=self.data['Low'],
            close=self.data['Close'],
            name='Market Data'
        ), row=1, col=1)

        buy_trades = [trade for trade in self.trades if trade['side'] == 'buy']
        sell_trades = [trade for trade in self.trades if trade['side'] == 'sell']

        fig.add_trace(go.Scatter(
            x=[trade['time'] for trade in buy_trades],
            y=[trade['price'] for trade in buy_trades],
            mode='markers',
            marker=dict(color='green', size=10),
            name='Buy Trades'
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=[trade['time'] for trade in sell_trades],
            y=[trade['price'] for trade in sell_trades],
            mode='markers',
            marker=dict(color='red', size=10),
            name='Sell Trades'
        ), row=1, col=1)

        # Highlight the most profitable and loss-making trades
        if self.max_profit_trade:
            fig.add_trace(go.Scatter(
                x=[self.max_profit_trade['time']],
                y=[self.data.loc[self.max_profit_trade['time'], 'Close']],
                mode='markers',
                marker=dict(color='blue', size=15, symbol='star'),
                name='Most Profitable Trade'
            ), row=1, col=1)

        if self.max_loss_trade:
            fig.add_trace(go.Scatter(
                x=[self.max_loss_trade['time']],
                y=[self.data.loc[self.max_loss_trade['time'], 'Close']],
                mode='markers',
                marker=dict(color='orange', size=15, symbol='star'),
                name='Most Loss-Making Trade'
            ), row=1, col=1)

        fig.update_layout(title='Scalping Strategy Backtest for the symbol', xaxis_title='Time', yaxis_title='Price')

        # Save the main figure as an HTML file
        pio.write_html(fig, file='scalping_strategy_backtest.html', auto_open=False)

        # Create a separate figure for the trade details table
        trade_details = go.Figure(data=[go.Table(
            header=dict(values=['Side', 'Price', 'Time'],
                        fill_color='paleturquoise',
                        align='left'),
            cells=dict(values=[
                [trade['side'] for trade in self.trades],
                [trade['price'] for trade in self.trades],
                [trade['time'].strftime('%Y-%m-%d %H:%M:%S') for trade in self.trades]
            ],
            fill_color='lavender',
            align='left')
        )])

        trade_details.update_layout(title='Trade Details')

        # Save the trade details table as an HTML file
        pio.write_html(trade_details, file='trade_details.html', auto_open=False)

        # Plot PnL over time
        self.plot_pnl()

if __name__ == "__main__":
    symbol = 'USUAL/USDT'
    start_date = datetime(2024, 1, 12)
    end_date = datetime(2025, 1, 6)
    strategy = ScalpingStrategy(symbol)
    strategy.run_backtest(start_date, end_date)