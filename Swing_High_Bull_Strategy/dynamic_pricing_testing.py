import ccxt
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime as dt
from datetime import timedelta
import csv
import timeit

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

        return data
    
    # Dynamic tracking of the seconds data from get_data and dynamically making it as the last price of that ticker
    def dynamic_pricing(self, symbol, since, timeframe='1s'):
        data = self.get_data(symbol, since, timeframe)
        
        if not data:
            human_readable_since = self.convert_timestamp_ms_to_human_readable(since)
            print(f"No data fetched for {symbol} since {human_readable_since}")
            return []

        # Fetch the last price for the previous second
        last_price_data = self.get_data(symbol, int(dt.now().timestamp() * 1000) - 2000, timeframe)
        last_price = last_price_data[-1][4] if last_price_data else data[0][4]
        
        # Save a csv with an additional column named 'last_price' and the last price of the ticker
        with open('data.csv', 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'open', 'high', 'low', 'close', 'volume', 'last_price'])
            for row in data:
                row.append(last_price)
                writer.writerow(row)
                last_price = row[4]  # Update last price to current row's close price
                
        return data

# List of symbols to fetch data for

# Start the timer
start_time = timeit.default_timer()
symbol = "BTC/USDT"
fetcher = data_fetcher()
user_defined_time_frame = int((dt.now() - timedelta(hours=1)).timestamp() * 1000)
fetched_data = fetcher.dynamic_pricing(symbol, user_defined_time_frame, timeframe='1s')  
elapsed = timeit.default_timer() - start_time
print(f"Data Fetching completed in {elapsed:.2f} seconds.")