import ccxt
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime as dt
from datetime import timedelta
import pandas as pd
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
            return pd.DataFrame()

        # Fetch the last price for the previous second
        last_price_data = self.get_data(symbol, int(dt.now().timestamp() * 1000) - 2000, timeframe)
        last_price = last_price_data[-1][4] if last_price_data else data[0][4]
        
        # Create a DataFrame with an additional column named 'last_price' and the last price of the ticker
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['last_price'] = last_price
        
        return df

# Start the timer
start_time = timeit.default_timer()
fetcher = data_fetcher()
#markets = fetcher.exchange.load_markets()
markets = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "ADA/USDT", "SOL/USDT", "DOT/USDT", "DOGE/USDT", "UNI/USDT", "LUNA/USDT", "LINK/USDT"]
symbols_to_fetch = [symbol for symbol in markets if '/USDT' in symbol]

# Create a dictionary to hold DataFrames for each symbol
data_frames = {}

for symbol in symbols_to_fetch:
    user_defined_time_frame = int((dt.now() - timedelta(hours=1)).timestamp() * 1000)
    df = fetcher.dynamic_pricing(symbol, user_defined_time_frame, timeframe='1s')
    if not df.empty:
        data_frames[symbol] = df

# Save all DataFrames to an Excel file with multiple sheets
with pd.ExcelWriter('data.xlsx') as writer:
    for symbol, df in data_frames.items():
        sheet_name = symbol.replace("/", "_")
        df.to_excel(writer, sheet_name=sheet_name, index=False)


elapsed = timeit.default_timer() - start_time
print(f"Data Fetching for {symbol} completed in {elapsed:.2f} seconds.")
