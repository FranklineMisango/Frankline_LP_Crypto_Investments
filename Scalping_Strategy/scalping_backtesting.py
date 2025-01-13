from datetime import datetime
import pandas as pd
import ccxt
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

class ScalpingStrategy:
    def __init__(self, symbol, quantity, profit_threshold=0.001, stop_loss_threshold=0.001):
        self.symbol = symbol
        self.quantity = quantity
        self.profit_threshold = profit_threshold
        self.stop_loss_threshold = stop_loss_threshold
        self.exchange = ccxt.binance()
        self.data = None
        self.trades = []

    # Fetch data using binance connectors
    def get_minute_data(self, start_date, end_date, interval='1m'):
        since = self.exchange.parse8601(start_date.isoformat())
        end = self.exchange.parse8601(end_date.isoformat())
        ohlcv = []
        while since < end:
            data = self.exchange.fetch_ohlcv(self.symbol, timeframe=interval, since=since, limit=1000)
            if not data:
                break
            since = data[-1][0] + 1
            ohlcv.extend(data)
        frame = pd.DataFrame(ohlcv, columns=['Time', 'Open', 'High', 'Low', 'Close', 'Volume'])
        frame = frame.set_index('Time')
        frame.index = pd.to_datetime(frame.index, unit='ms')
        frame = frame.astype(float)
        return frame

    def place_order(self, side, price, timestamp):
        print(f"Simulating {side} order for {self.quantity} {self.symbol} at {price}")
        self.trades.append({'side': side, 'price': price, 'time': timestamp})
        return True

    def run_backtest(self, start_date, end_date):
        print("Starting backtest")
        self.data = self.get_minute_data(start_date, end_date)
        print("Data loaded successfully")
        buy_price = None
        
        for i in range(len(self.data)):
            current_price = self.data['Close'].iloc[i]
            current_time = self.data.index[i]
            
            if buy_price is None:
                buy_price = current_price
                self.place_order('buy', buy_price, current_time)
            else:
                profit = (current_price - buy_price) / buy_price
                loss = (buy_price - current_price) / buy_price
                
                if profit >= self.profit_threshold:
                    self.place_order('sell', current_price, current_time)
                    print(f"Trade closed with profit: {profit * 100:.2f}%")
                    buy_price = None
                elif loss >= self.stop_loss_threshold:
                    self.place_order('sell', current_price, current_time)
                    print(f"Trade closed with loss: {loss * 100:.2f}%")
                    buy_price = None

        self.plot_results()

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

        fig.update_layout(title='Scalping Strategy Backtest for the symbol', xaxis_title='Time', yaxis_title='Price')

        # Save the main figure as an HTML file
        pio.write_html(fig, file='scalping_strategy_backtest.html', auto_open=True)

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
        pio.write_html(trade_details, file='trade_details.html', auto_open=True)

if __name__ == "__main__":
    symbol = 'AIXBT/USDT'
    quantity = 100  # Adjust the quantity as needed
    start_date = datetime(2025, 1, 1)
    end_date = datetime(2025, 1, 12)
    strategy = ScalpingStrategy(symbol, quantity)
    strategy.run_backtest(start_date, end_date)