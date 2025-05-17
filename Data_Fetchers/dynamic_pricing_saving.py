import ccxt
from datetime import datetime as dt
from datetime import timedelta
import pandas as pd
import timeit
from concurrent.futures import ThreadPoolExecutor, as_completed

class data_fetcher():

    def __init__(self):
        self.exchange = ccxt.binance()
        self.initial_gains = {}
        self.data = {}

    def convert_timestamp_ms_to_human_readable(self, timestamp_ms):
        timestamp_s = timestamp_ms / 1000.0
        dt_object = dt.fromtimestamp(timestamp_s)
        return dt_object.strftime('%Y-%m-%d %H:%M:%S')

    # Fetch data for a given timeframe since a specific time with pagination
    def get_data(self, symbol, since, timeframe='1s', limit=1000):
        all_data = []
        while True:
            data = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
            if not data:
                break
            all_data.extend(data)
            since = data[-1][0] + 1  # Move to the next timestamp
            if len(data) < limit:
                break

        # Convert timestamps to human-readable format
        for row in all_data:
            row[0] = self.convert_timestamp_ms_to_human_readable(row[0])

        return all_data

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

        # Add an additional column named 'last_price' with the last price of the ticker
        for row in data:
            row.append(last_price)
            last_price = row[4]  # Update last price to current row's close price

        return data

def fetch_and_save_data(symbol, fetcher, writer):
    user_defined_time_frame = int((dt.now() - timedelta(hours=24)).timestamp() * 1000)
    fetched_data = fetcher.dynamic_pricing(symbol, user_defined_time_frame, timeframe='1s')

    # Convert the fetched data to a DataFrame
    df = pd.DataFrame(fetched_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'last_price'])

    # Write the DataFrame to a sheet named after the symbol
    df.to_excel(writer, sheet_name=symbol.replace('/', '_'), index=False)

# List of symbols to fetch data for

# Start the timer
start_time = timeit.default_timer()
Fetch_top_tickers = FindTopGainers()
top_gainers_list = Fetch_top_tickers.find_top_gainers()

# Create a Pandas Excel writer using openpyxl as the engine
with pd.ExcelWriter('/content/drive/MyDrive/Data_Fetching_Pipeline/data.xlsx', engine='openpyxl') as writer:
    fetcher = data_fetcher()
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_and_save_data, symbol, fetcher, writer) for symbol in top_gainers_list if '/USDT' in symbol]
        for future in as_completed(futures):
            future.result()  # Wait for all futures to complete

    elapsed = timeit.default_timer() - start_time
    print(f"Data Fetching completed in {elapsed:.2f} seconds.")