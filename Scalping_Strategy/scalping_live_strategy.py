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
from concurrent.futures import ThreadPoolExecutor


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

    
    def get_lot_size(self, symbol):
        exchange_info = client.exchange_info()
        for s in exchange_info['symbols']:
            if s['symbol'] == symbol:
                for f in s['filters']:
                    if f['filterType'] == 'LOT_SIZE':
                        return float(f['stepSize'])
        return 1.0  # Default to 1.0 if not found

    def get_min_notional(self, symbol):
        exchange_info = client.exchange_info()
        for s in exchange_info['symbols']:
            if s['symbol'] == symbol:
                for f in s['filters']:
                    if f['filterType'] == 'MIN_NOTIONAL':
                        return float(f['minNotional'])
        
        return 10.0  # Default to 10.0 if not found
    

    def buy_order(self, symbol, shares):
        try:
            lot_size = self.get_lot_size(symbol)
            min_notional = self.get_min_notional(symbol)
            last_price = self.get_last_price(symbol)
            
            # Adjust shares to meet the lot size requirement
            shares = round(shares // lot_size * lot_size, 8)
            
            # Ensure the total value meets the minimum notional value
            if shares * last_price < min_notional:
                # Adjust shares to meet the minimum notional value
                shares = round((min_notional / last_price) // lot_size * lot_size, 8)
                # Add a small buffer to ensure the order value meets the minimum notional value
                shares += lot_size
                if shares * last_price < min_notional:
                    self.log_message(f"Order value {shares * last_price} is still below the minimum notional value {min_notional} after adjustment")
                    return
            
            # Check if the order value exceeds available funds
            order_value = shares * last_price
            if order_value > self.available_funds:
                self.log_message(f"Insufficient funds to buy {shares} coins of {symbol}. Order value: {order_value}, Available funds: {self.available_funds}")
                return
            
            order = client.new_order(symbol=symbol, side='BUY', type='MARKET', quantity=shares)
            self.order_numbers[symbol] = order['orderId']
            self.available_funds -= order_value  # Update available funds
            self.log_message(f"Buying {shares} coins of {symbol} at market price")
        except Exception as e:
            self.log_message(f"Error buying {shares} coins of {symbol}: {e}")
    
    
    def get_last_price(symbol):
        try:
            ticker = fetcher_client.get_symbol_ticker(symbol=symbol)
            return float(ticker['price'])
        except Exception as e:
            print(f"Error fetching last price for {symbol}: {e}")
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

        buy_price = None
        portfolio_values = [self.portfolio_value]  # Track portfolio value over time

        while time.time() < end_time:
            last_price = self.get_last_price()
            if last_price is None:
                continue

            if buy_price is None:
                buy_price = last_price
                self.quantity = self.portfolio_value / buy_price
                self.buy_order(self.quantity)
                self.position = 1
            else:
                profit = (last_price - buy_price) / buy_price
                loss = (buy_price - last_price) / buy_price

                if profit >= self.profit_threshold:
                    self.sell_order(self.quantity)
                    self.portfolio_value = self.quantity * last_price
                    portfolio_values.append(self.portfolio_value)  # Update portfolio value
                    print(f"Trade closed with profit: {profit * 100:.2f}%")
                    if self.max_profit_trade is None or profit > self.max_profit_trade['profit']:
                        self.max_profit_trade = {'profit': profit, 'time': time.time()}
                    buy_price = None
                    self.position = 0
                elif loss >= self.stop_loss_threshold:
                    self.sell_order(self.quantity)
                    self.portfolio_value = self.quantity * last_price
                    portfolio_values.append(self.portfolio_value)  # Update portfolio value
                    print(f"Trade closed with loss: {loss * 100:.2f}%")
                    if self.max_loss_trade is None or loss > self.max_loss_trade['loss']:
                        self.max_loss_trade = {'loss': loss, 'time': time.time()}
                    buy_price = None
                    self.position = 0


        # Sell all positions before ending the live trading
        if self.position == 1:
            self.sell_order(self.quantity)

        print(f"Final portfolio value: {self.portfolio_value}")
        print(f"Closing live trading at time {dt.now()}")

if __name__ == "__main__":
    strategy = ScalpingStrategy(symbol='BTC/USDT')
    strategy.run_live_trading(duration_minutes=30)  # Run live trading for specified minutes