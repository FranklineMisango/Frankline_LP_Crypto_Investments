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

    #Max shares of the coin that we can buy with our balance
    def calculate_max_shares(self, symbol, available_funds):
            last_price = self.get_last_price(symbol)
            if last_price is None:
                self.log_message(f"Could not fetch last price for {symbol}")
                return 0

            min_notional = self.get_min_notional(symbol)
            lot_size = self.get_lot_size(symbol)
            
            # Calculate the maximum shares that can be bought with the available funds
            max_shares = available_funds / last_price
            
            # Adjust shares to meet the lot size requirement
            max_shares = round(max_shares // lot_size * lot_size, 8)
            
            # Ensure the total value meets the minimum notional value
            if max_shares * last_price < min_notional:
                # Adjust shares to meet the minimum notional value
                max_shares = round((min_notional / last_price) // lot_size * lot_size, 8)
                # Add a small buffer to ensure the order value meets the minimum notional value
                max_shares += lot_size
                if max_shares * last_price < min_notional:
                    self.log_message(f"Order value {max_shares * last_price} is still below the minimum notional value {min_notional} after adjustment")
                    return 0
            
            return max_shares
    
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
    
    def get_last_price(self, symbol):
            try:
                ticker = self.fetcher_client.get_symbol_ticker(symbol=symbol)
                return float(ticker['price'])
            except Exception as e:
                print(f"Error fetching last price for {symbol}: {e}")
                return None

    def log_message(self, message): 
        #TODO - Send to my E-mail the CSV every 1 hour the live running actions and the portfolio value
        print(message)
        with open('Live_Running_Actions.csv', 'a') as f:
            writer = csv.writer(f)
            writer.writerow([dt.now(), message])

    def sell_all(self, symbol, entry_price):
        current_price = self.get_last_price(symbol)
        if current_price is None:
            return
        if self.get_position(symbol):
            dropping_price = entry_price * 0.995
            higher_than_earlier_price = entry_price * 1.015
            if current_price < dropping_price or current_price >= higher_than_earlier_price:
                shares = self.shares_per_ticker[symbol]
                try:
                    # Fetch the actual balance from the exchange
                    account_info = client.account()
                    for item in account_info['balances']:
                        if item['asset'] == symbol[:-4]:
                            available_shares = float(item['free'])
                            break
                    else:
                        available_shares = 0

                    # Ensure the number of shares to sell does not exceed the available balance
                    shares_to_sell = min(shares, available_shares)
                    shares_to_sell = math.floor(shares_to_sell)  # Round down to the nearest whole number
                    if shares_to_sell <= 0:
                        # No available shares to sell then stop trying to sell 
                        self.log_message(f"No available shares to sell for {symbol}")
                        return

                    # Ensure client is accessible
                    order = client.new_order(symbol=symbol, side='SELL', type='MARKET', quantity=shares_to_sell)
                    sale_value = shares_to_sell * current_price
                    sale_value -= sale_value * self.fees  # Subtract fees
                    self.portfolio_value += sale_value
                    self.available_funds += sale_value  # Update available funds
                    self.log_message(f"Selling {shares_to_sell} coins of {symbol} at {current_price}")
                    self.positions[symbol] = False
                except Exception as e:
                    self.log_message(f"Error selling {shares} coins of {symbol}: {e}")
    
    def final_sell_everything_before_ending(self, symbol):
        print(f"Selling all {symbol} coins before ending the live trading...")
        current_price = self.get_last_price(symbol)
        if current_price is None:
            return
        shares = self.shares_per_ticker.get(symbol, 0)
        try:
            # Fetch the actual balance from the exchange
            account_info = client.account()
            for item in account_info['balances']:
                if item['asset'] == symbol[:-4]:
                    available_shares = float(item['free'])
                    break
            else:
                available_shares = 0

            # Ensure the number of shares to sell does not exceed the available balance
            shares_to_sell = min(shares, available_shares)
            shares_to_sell = math.floor(shares_to_sell)  # Round down to the nearest whole number
            if shares_to_sell <= 0:
                self.log_message(f"No available shares to sell for {symbol}")
                return

            # Place the sell order
            order = client.new_order(symbol=symbol, side='SELL', type='MARKET', quantity=shares_to_sell)
            sale_value = shares_to_sell * current_price
            sale_value -= sale_value * self.fees  # Subtract fees
            self.portfolio_value += sale_value
            self.available_funds += sale_value  # Update available funds
            self.log_message(f"Selling {shares_to_sell} coins of {symbol} at {current_price}")
            self.positions[symbol] = False
            self.shares_per_ticker[symbol] = 0  # Reset the shares per ticker
        except Exception as e:
            self.log_message(f"Error selling {shares} coins of {symbol}: {e}")
    
    def run_live_trading(self, duration_minutes):
        print("Starting Scalping live trading strategy ...")
        account_info = self.client.account()['balances']
        for item in account_info:
            if item['asset'] == 'USDT':
                self.portfolio_value = float(item['free'])
                self.available_funds = self.portfolio_value  # Initialize available funds
                print(f"Starting with a portfolio value of : {self.portfolio_value} USDT")

        start_time = time.time()
        end_time = start_time + duration_minutes * 60

        buy_price = None
        portfolio_values = [self.portfolio_value]  # Track portfolio value over time

        while time.time() < end_time:
            last_price = self.get_last_price(self.symbol)
            if last_price is None:
                continue

            if buy_price is None:
                buy_price = last_price
                self.quantity = self.calculate_max_shares(self.symbol, self.available_funds)
                if self.quantity > 0:
                    self.buy_order(self.symbol, self.quantity)
                    self.position = 1
            else:
                profit = (last_price - buy_price) / buy_price
                loss = (buy_price - last_price) / buy_price

                if profit >= self.profit_threshold:
                    self.sell_all(self.quantity)
                    self.portfolio_value = self.quantity * last_price
                    portfolio_values.append(self.portfolio_value)  # Update portfolio value
                    print(f"Trade closed with profit: {profit * 100:.2f}%")
                    if self.max_profit_trade is None or profit > self.max_profit_trade['profit']:
                        self.max_profit_trade = {'profit': profit, 'time': time.time()}
                    buy_price = None
                    self.position = 0
                elif loss >= self.stop_loss_threshold:
                    self.sell_all(self.quantity)
                    self.portfolio_value = self.quantity * last_price
                    portfolio_values.append(self.portfolio_value)  # Update portfolio value
                    print(f"Trade closed with loss: {loss * 100:.2f}%")
                    if self.max_loss_trade is None or loss > self.max_loss_trade['loss']:
                        self.max_loss_trade = {'loss': loss, 'time': time.time()}
                    buy_price = None
                    self.position = 0

        # Sell all positions before ending the live trading
        if self.position == 1:
            self.final_sell_everything_before_ending(self.quantity)

        print(f"Final portfolio value: {self.portfolio_value}")
        print(f"Closing live trading at time {dt.now()}") 

if __name__ == "__main__":
    account_info = client.account()['balances']
    for item in account_info:
        if item['asset'] == 'USDT':
            portfolio_value = float(item['free'])
            available_funds = portfolio_value  # Initialize available funds
            print(f"Starting with a portfolio value of : {portfolio_value} USDT")
    strategy = ScalpingStrategy(symbol='DEXEUSDT', initial_portfolio_value=available_funds)
    strategy.run_live_trading(duration_minutes=10)  # Run live trading for specified minutes