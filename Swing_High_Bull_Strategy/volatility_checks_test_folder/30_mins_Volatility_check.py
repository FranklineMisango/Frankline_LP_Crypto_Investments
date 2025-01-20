import time
import csv
import pytz
import pandas as pd
from datetime import datetime as dt, timedelta
from binance.client import Client

client = Client(api_key='your_api_key', api_secret='your_api_secret')

hkt = pytz.timezone('Asia/Hong_Kong')

def fetch_volatile_tickers_for_last_30_minutes():
    hkt = pytz.timezone('Asia/Hong_Kong')
    now = dt.now(hkt)
    since = int((now - timedelta(minutes=30)).timestamp() * 1000)
    markets = client.get_all_tickers()
    volatile_tickers = {}

    for market in markets:
        symbol = market['symbol']
        if 'USDT' in symbol:
            try:
                data = get_stock_data(symbol, since)
                if data is not None and not data.empty:
                    initial_price = data.iloc[0]['Open']  # Opening price 30 minutes ago
                    current_price = data.iloc[-1]['Close']  # Closing price now
                    gain = (current_price - initial_price) / initial_price * 100
                    num_trades = data['Number of Trades'].sum()
                    volume = data['Volume'].sum()

                    if gain >= 2:
                        volatile_tickers[symbol] = {
                            'Crypto Symbol': symbol,
                            'initial_price': initial_price,
                            'current_price': current_price,
                            'Percentage Change': gain,
                            'num_trades': num_trades,
                            'Volume ': volume
                        }
            except Exception as e:
                print(f"Error fetching data for {symbol}: {e}")

    return volatile_tickers


def get_stock_data(ticker, since):
    klines = client.get_historical_klines(ticker, Client.KLINE_INTERVAL_5MINUTE, since)
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


def fetch_volatile_tickers_lively():
    all_volatile_tickers = {}
    while True:
        print("Fetching volatile tickers for the last 30 minutes...")
        volatile_tickers = fetch_volatile_tickers_for_last_30_minutes()
        all_volatile_tickers.update(volatile_tickers)
        
        with open('30_minutes_dynamic_updates_volatile_tickers.csv', 'w') as f:
            writer = csv.writer(f)
            writer.writerow(['Crypto Symbol', 'initial_price', 'current_price', 'Percentage Change (%)', 'num_trades', 'Volume'])
            for ticker in all_volatile_tickers.values():
                writer.writerow([ticker['Crypto Symbol'], ticker['initial_price'], ticker['current_price'], ticker['Percentage Change'], ticker['num_trades'], ticker['Volume ']])
        
        print("Updated volatile tickers list.")
        print("Waiting for 30 minutes before fetching again...")
        time.sleep(1800)  # Wait for 30 minutes before fetching again


# Example usage
if __name__ == "__main__":
    fetch_volatile_tickers_lively()