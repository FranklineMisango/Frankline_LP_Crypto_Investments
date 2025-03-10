import ccxt
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime as dt
from datetime import timedelta
import csv
import time
import timeit
import pytz

class data_fetcher():
    def __init__(self):
        self.exchange = ccxt.binance()
        self.initial_gains = {}
        self.data = {}
        self.order_numbers = {}
        self.shares_per_ticker = {}
        self.positions = {}
        self.portfolio_value = 1000  # Initial portfolio value
        self.fees = 0.1/100  # Binance trading fee (0.1%)

    def get_last_price(self, symbol):
        # Fetch the latest OHLCV data
        ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe='1m', limit=1)
        # Get the last price from the 'close' field of the latest candle
        last_price = ohlcv[-1][4]
        return last_price
    
    def convert_timestamp_ms_to_human_readable(self, timestamp_ms):
        timestamp_s = timestamp_ms / 1000.0
        dt_object = dt.fromtimestamp(timestamp_s)
        return dt_object.strftime('%Y-%m-%d %H:%M:%S')

    # Find the price at the previous minute
    def get_minute_data(self, symbol, since):
        data = self.exchange.fetch_ohlcv(symbol, timeframe='1s', since=since)

        # Convert timestamps to human-readable format
        for row in data:
            row[0] = self.convert_timestamp_ms_to_human_readable(row[0])

        # Save data as a csv file and format the columns properly
        with open('data.csv', 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            writer.writerows(data)
        
        return data

data_fetcher = data_fetcher()
symbol = 'BTC/USDT'
since = int((dt.now() - timedelta(minutes=1)).timestamp() * 1000)
data = data_fetcher.get_minute_data(symbol, since)
print(data_fetcher.get_last_price(symbol))
print(data)