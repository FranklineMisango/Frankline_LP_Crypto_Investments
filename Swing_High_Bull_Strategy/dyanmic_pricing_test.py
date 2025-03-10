import ccxt
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime as dt
from datetime import timedelta
import csv
class data_fetcher():
    def __init__(self):
        self.exchange = ccxt.binance()
        self.initial_gains = {}
        self.data = {}

    def convert_timestamp_ms_to_human_readable(self, timestamp_ms):
        timestamp_s = timestamp_ms / 1000.0
        dt_object = dt.fromtimestamp(timestamp_s)
        return dt_object.strftime('%Y-%m-%d %H:%M:%S')

    # Fetch data for a given timeframe since a specific time
    def get_data(self, symbol, since, timeframe='1s'):
        data = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since)

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
user_defined_time_frame = int((dt.now() - timedelta(hours=1)).timestamp() * 1000)
fetched_data = data_fetcher.get_data(symbol, user_defined_time_frame, timeframe='1s')
print(fetched_data)