# Import libraries 
import json 
import requests 
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


# Get API keys from environment variables
api_key = os.getenv('Binance_API_KEY')
api_secret = os.getenv('Binance_secret_KEY')

# Initialize Binance client
client = Client(api_key, api_secret)


def fetch_volatile_tickers_for_last_hour():
    hkt = pytz.timezone('Asia/Hong_Kong')
    now = dt.now(hkt)
    since = int((now - timedelta(hours=1)).timestamp() * 1000)
    markets = client.get_all_tickers()
    volatile_tickers = []

    for market in markets:
        symbol = market['symbol']
        if 'USDT' in symbol:
            try:
                data = get_stock_data(symbol, since)
                if data is not None and not data.empty:
                    initial_price = data.iloc[0]['Open']  # Opening price an hour ago
                    current_price = data.iloc[-1]['Close']  # Closing price now
                    gain = (current_price - initial_price) / initial_price * 100
                    num_trades = data['Number of Trades'].sum()
                    volume = data['Volume'].sum()

                    if gain >= 2:
                        volatile_tickers.append({
                            'Crypto Symbol': symbol,
                            'initial_price': initial_price,
                            'current_price': current_price,
                            'Percentage Change': gain,
                            'num_trades': num_trades,
                            'Volume ': volume
                        })
            except Exception as e:
                print(f"Error fetching data for {symbol}: {e}")

    return volatile_tickers


def get_stock_data(ticker, since):
    klines = client.get_historical_klines(ticker, Client.KLINE_INTERVAL_1HOUR, since)
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
    all_volatile_tickers = []
    while True:
        print("Fetching volatile tickers for the last hour...")
        volatile_tickers = fetch_volatile_tickers_for_last_hour()
        all_volatile_tickers.extend(volatile_tickers)
        all_volatile_tickers.sort(key=lambda x: x['%change'], reverse=True)
        
        with open('volatile_tickers.csv', 'w') as f:
            writer = csv.writer(f)
            writer.writerow(['symbol', 'initial_price', 'current_price', '%change', 'num_trades'])
            for ticker in all_volatile_tickers:
                writer.writerow([ticker['symbol'], ticker['initial_price'], ticker['current_price'], ticker['%change'], ticker['num_trades']])
        
        print("Updated volatile tickers list.")
        time.sleep(3600)  # Wait for 1 hour before fetching again


# Example usage
if __name__ == "__main__":
    fetch_volatile_tickers_lively()