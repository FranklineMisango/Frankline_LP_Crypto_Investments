# Import the libraries you need here
import math
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime as dt
from datetime import timedelta
from binance.client import Client
import pandas as pd
import os
import sys
from binance.spot import Spot
import math



#define the API keys
client = Spot()
client = Spot(api_key=os.getenv('Binance_API_KEY'), api_secret=os.getenv('Binance_secret_KEY')) # Main Trader API
fetcher_client = Client(os.getenv('Binance_Fetcher_api'), os.getenv('Binance_Fetcher_secret')) #Main Data Fetcher API


class MyStrategy():
    def __init__(self):
        #define your self variables here
        self.available_funds = 1000.0

    #Shares you can buy per ticker utmost
    def calculate_max_shares(self, symbol, available_funds):
        last_price = self.get_last_price(symbol)
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
    

    #Sell everything in a stock ticker 
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


    def run_live_backtesting_Strategy():
        pass
