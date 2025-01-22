from dotenv import load_dotenv
load_dotenv()
from datetime import datetime as dt
from datetime import timedelta
import csv
import time
import pytz
from binance.client import Client
import pandas as pd
import os
import sys
from binance.spot import Spot
import threading
import math



client = Spot()
client = Spot(api_key=os.getenv('Binance_API_KEY'), api_secret=os.getenv('Binance_secret_KEY')) # Main Trader API
fetcher_client = Client(os.getenv('Binance_Fetcher_api'), os.getenv('Binance_Fetcher_secret')) #Main Data Fetcher API

class ScalpingStrategy:
    def __init__(self, symbol, initial_portfolio_value, profit_threshold=0.001, stop_loss_threshold=0.001):
        self.symbol = symbol
        self.profit_threshold = profit_threshold
        self.stop_loss_threshold = stop_loss_threshold
        self.data = None
        self.trades = []
        self.portfolio_value = initial_portfolio_value
        self.initial_portfolio_value = initial_portfolio_value
        self.position = 0  # Track the current position (0 for no position, 1 for long, -1 for short)
        self.quantity = 0  # Track the quantity of the asset being traded
        self.max_profit_trade = None
        self.max_loss_trade = None
        self.client = Spot(api_key=os.getenv('Binance_API_KEY'), api_secret=os.getenv('Binance_secret_KEY'))
        self.fetcher_client = Client(os.getenv('Binance_Fetcher_api'), os.getenv('Binance_Fetcher_secret'))
        self.lock = threading.Lock()

     def get_stock_data(self, ticker, since):
        klines = fetcher_client.get_historical_klines(ticker, Client.KLINE_INTERVAL_5MINUTE, since)
        df = pd.DataFrame(klines, columns=['Open Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close Time', 'Quote Asset Volume', 'Number of Trades', 'Taker Buy Base Asset Volume', 'Taker Buy Quote Asset Volume', 'Ignore'])
        df['Open Time'] = pd.to_datetime(df['Open Time'], unit='ms')
        df['Close Time'] = pd.to_datetime(df['Close Time'], unit='ms')
        df['Open'] = df['Open'].astype(float)
        df['High'] = df['High'].astype(float)
        df['Low'] = df['Low'].astype(float)
        df['Close'] = df['Close'].astype(float)
        df['Volume'] = df['Volume'].astype(float)
        df['Quote Asset Volume'] = df['Quote Asset Volume'].astype(float)
        df['Number of Trades'] = df['Number of Trades'].astype(float)
        df['Taker Buy Base Asset Volume'] = df['Taker Buy Base Asset Volume'].astype(float)
        df['Taker Buy Quote Asset Volume'] = df['Taker Buy Quote Asset Volume'].astype(float)
        df.set_index('Open Time', inplace=True)  # Set the index to 'Open Time'
        return df
    
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
        return data

    def fetch_data_chunk(self, since, end, interval):
        ohlcv = self.exchange.fetch_ohlcv(self.symbol, timeframe=interval, since=since, limit=1000)
        return ohlcv

    def get_last_price(self):
        try:
            ticker = self.fetcher_client.get_symbol_ticker(symbol=self.symbol)
            return float(ticker['price'])
        except Exception as e:
            print(f"Error fetching last price for {self.symbol}: {e}")
            return None

    def buy_order(self, quantity):
        try:
            order = self.client.new_order(symbol=self.symbol, side='BUY', type='MARKET', quantity=quantity)
            self.position = 1
            self.quantity = quantity
            print(f"Bought {quantity} of {self.symbol}")
        except Exception as e:
            print(f"Error placing buy order: {e}")

    def sell_order(self, quantity):
        try:
            order = self.client.new_order(symbol=self.symbol, side='SELL', type='MARKET', quantity=quantity)
            self.position = 0
            self.quantity = 0
            print(f"Sold {quantity} of {self.symbol}")
        except Exception as e:
            print(f"Error placing sell order: {e}")

    def run_live_trading(self, duration_minutes):
        print("Starting Scalping live trading strategy ...")
        account_info = self.client.account()['balances']
        for item in account_info:
            if item['asset'] == 'USDT':
                self.portfolio_value = float(item['free'])
                print(f"Starting with a portfolio value of : {self.portfolio_value} USDT")

        start_time = time.time()
        end_time = start_time + duration_minutes * 60

        while time.time() < end_time:
            last_price = self.get_last_price()
            if last_price is None:
                continue

            if self.position == 0:
                # Buy logic
                quantity = self.portfolio_value / last_price
                self.buy_order(quantity)
            elif self.position == 1:
                # Sell logic
                if last_price >= self.max_profit_trade or last_price <= self.max_loss_trade:
                    self.sell_order(self.quantity)

            print("Waiting for 1 minute before next check...")
            time.sleep(60)  # Wait for 1 minute before checking again

        # Sell all positions before ending the live trading
        if self.position == 1:
            self.sell_order(self.quantity)

        print(f"Final portfolio value: {self.portfolio_value}")
        print(f"Closing live trading at time {datetime.now()}")

if __name__ == "__main__":
    strategy = ScalpingStrategy(symbol='BTC/USDT')
    strategy.run_live_trading(duration_minutes=30)  # Run live trading for specified minutes