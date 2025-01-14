from datetime import datetime
from lumibot.entities import Asset, Order
from lumibot.strategies import Strategy
from lumibot.backtesting import CcxtBacktesting
from pandas import DataFrame
import pandas as pd
import ccxt
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
load_dotenv()

from datetime import datetime as dt
from datetime import timedelta


# TODO - Work on dynamic holding and just dropping once it falls to 0.95% of the initial gain"
class SwingHigh(Strategy):
    '''This strategy is based on the Swing High pattern. It buys when the last 3 candles are higher than the previous one and sells when the price drops by 0.5% or increases by 1.5%.'''
    '''The goal is to identify the stocks with high momentum and trade on the trend before selling back and make some money from an initial portfolio value.'''
    def __init__(self):
        self.exchange = ccxt.binance()
        self.initial_gains = {}

    def fetch_the_volatile_cryptocurrencies(self):
        now = dt.now()
        since = int((now - timedelta(hours=1)).timestamp() * 1000)
        markets = self.exchange.load_markets()
        volatile_tickers = []

        for symbol in markets:
            if '/USDT' in symbol:
                try:
                    data = self.get_minute_data(symbol, since)
                    if data:
                        initial_price = data[0][1]  # Opening price 1 hour ago
                        current_price = data[-1][4]  # Closing price now
                        gain = (current_price - initial_price) / initial_price * 100

                        if gain >= 2:
                            volatile_tickers.append(symbol)
                            self.initial_gains[symbol] = gain
                        elif symbol in self.initial_gains and gain < self.initial_gains[symbol] * 0.95:
                            volatile_tickers.remove(symbol)
                            del self.initial_gains[symbol]
                except ccxt.BaseError as e:
                    print(f"Error fetching data for {symbol}: {e}")

        return volatile_tickers

    def get_minute_data(self, symbol, since):
        ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe='1m', since=since)
        return ohlcv
    
    def fetch_the_volatile_cryptocurrencies(self):
        now = datetime.datetime.now()
        since = int((now - datetime.timedelta(hours=1)).timestamp() * 1000)
        markets = self.exchange.load_markets()
        volatile_tickers = []

        for symbol in markets:
            if '/USDT' in symbol:
                data = self.get_minute_data(symbol, since)
                if data:
                    initial_price = data[0][1]  # Opening price 1 hour ago
                    current_price = data[-1][4]  # Closing price now
                    gain = (current_price - initial_price) / initial_price * 100

                    if gain >= 2:
                        volatile_tickers.append(symbol)
                    elif gain < 1.95:
                        volatile_tickers.remove(symbol)

        print(volatile_tickers)
        return volatile_tickers
    
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
    
    def calculate_crypto_positions():
        pass
    
    def on_trading_iteration(self):
        for symbol in self.symbols:
            if symbol not in self.data:
                self.data[symbol] = []

            entry_price = self.get_last_price(symbol)
            if entry_price is None:
                self.log_message(f"No price data for {symbol}, skipping.")
                continue

            self.log_message(f"Position for {symbol}: {self.get_position(symbol)}")
            self.data[symbol].append(entry_price)

            if len(self.data[symbol]) > 3:
                temp = self.data[symbol][-3:]
                if None not in temp and temp[-1] > temp[1] > temp[0]:
                    self.log_message(f"Last 3 prints for {symbol}: {temp}")
                    order = self.create_order(symbol, quantity=self.shares_per_ticker[symbol], side="buy")
                    self.submit_order(order)
                    if symbol not in self.order_numbers:
                        self.order_numbers[symbol] = 0
                    self.order_numbers[symbol] += 1
                    if self.order_numbers[symbol] == 1:
                        self.log_message(f"Entry price for {symbol}: {temp[-1]}")
                        entry_price = temp[-1]  # filled price
                
                if self.get_position(symbol) and self.data[symbol][-1] < entry_price * 0.995:
                    self.sell_all(symbol)
                    self.order_numbers[symbol] = 0
                elif self.get_position(symbol) and self.data[symbol][-1] >= entry_price * 1.015:
                    self.sell_all(symbol)
                    self.order_numbers[symbol] = 0

    def before_market_closes(self):
        for symbol in self.symbols:
            self.sell_all(symbol)



''''
if __name__ == "__main__":
    start_date = datetime(2024, 12, 11)
    end_date = datetime(2025, 1, 12)
    strategy = SwingHigh
    strategy.run_backtest(start_date, end_date)
'''