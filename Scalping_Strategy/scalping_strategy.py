import os
import time
import pandas as pd
from binance.client import Client
from binance.enums import *

# Get API keys from environment variables
api_key = os.getenv('Binance_API_KEY')
api_secret = os.getenv('Binance_secret_KEY')

# Initialize Binance client
client = Client(api_key, api_secret)

def get_minute_data(symbol, interval='1m', lookback='120'):
    frame = pd.DataFrame(client.get_historical_klines(symbol, interval, lookback + ' min ago UTC'))
    frame = frame.iloc[:, :6]
    frame.columns = ['Time', 'Open', 'High', 'Low', 'Close', 'Volume']
    frame = frame.set_index('Time')
    frame.index = pd.to_datetime(frame.index, unit='ms')
    frame = frame.astype(float)
    return frame

def place_order(symbol, side, quantity, order_type=ORDER_TYPE_MARKET):
    try:
        print(f"Placing {side} order for {quantity} {symbol}")
        order = client.create_order(symbol=symbol, side=side, type=order_type, quantity=quantity)
        print(order)
    except Exception as e:
        print(f"An error occurred: {e}")
        return False
    return True

def scalping_strategy(symbol, quantity, profit_threshold=0.001, stop_loss_threshold=0.001):
    data = get_minute_data(symbol)
    last_close = data['Close'].iloc[-1]
    buy_price = last_close
    place_order(symbol, SIDE_BUY, quantity)
    
    while True:
        data = get_minute_data(symbol)
        current_price = data['Close'].iloc[-1]
        profit = (current_price - buy_price) / buy_price
        loss = (buy_price - current_price) / buy_price
        
        if profit >= profit_threshold:
            place_order(symbol, SIDE_SELL, quantity)
            print(f"Trade closed with profit: {profit * 100:.2f}%")
            break
        elif loss >= stop_loss_threshold:
            place_order(symbol, SIDE_SELL, quantity)
            print(f"Trade closed with loss: {loss * 100:.2f}%")
            break
        
        time.sleep(1)

if __name__ == "__main__":
    symbol = 'BTCUSDT'
    quantity = 0.001  # Adjust the quantity as needed
    scalping_strategy(symbol, quantity)