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

# Configuring the Binance client API ; # Get API keys from environment variables
api_key = os.getenv('Binance_API_KEY')
api_secret = os.getenv('Binance_secret_KEY')

# Initialize Binance client
client = Client(api_key, api_secret)

class SwingHigh():

    def __init__(self):

        self.initial_gains = {}
        self.data = {}
        self.order_numbers = {}
        self.shares_per_ticker = {}
        self.positions = {}
        self.portfolio_value = client.get_account()
        self.fees = 0.006  # Binance trading fee (0.1%)

    def fetch_volatile_tickers_for_last_30_minutes(self):
        hkt = pytz.timezone('Asia/Hong_Kong')
        now = dt.now(hkt)
        since = int((now - timedelta(minutes=30)).timestamp() * 1000)
        markets = client.get_all_tickers()
        volatile_tickers = {}

        for market in markets:
            symbol = market['symbol']
            if 'USDT' in symbol:
                try:
                    data = self.get_stock_data(symbol, since)
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


    def get_stock_data(self,ticker, since):
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


    def fetch_volatile_tickers_lively(self):
        all_volatile_tickers = {}
        while True:
            print("Fetching volatile tickers for the last 30 minutes...")
            volatile_tickers = self.fetch_volatile_tickers_for_last_30_minutes()
            all_volatile_tickers.update(volatile_tickers)
            
            with open('30_minutes_dynamic_updates_volatile_tickers.csv', 'w') as f:
                writer = csv.writer(f)
                writer.writerow(['Crypto Symbol', 'initial_price', 'current_price', 'Percentage Change (%)', 'num_trades', 'Volume'])
                for ticker in all_volatile_tickers.values():
                    writer.writerow([ticker['Crypto Symbol'], ticker['initial_price'], ticker['current_price'], ticker['Percentage Change'], ticker['num_trades'], ticker['Volume ']])
            
            print("Updated volatile tickers list.")
            print("Waiting for 30 minutes before fetching again...")
            time.sleep(1800)  # Wait for 30 minutes before fetching again

    def buy_order(self, symbol, shares):
        try:
            order = self.exchange.create_market_buy_order(symbol, shares)
            self.order_numbers[symbol] = order['id']
            self.log_message(f"Buying {shares} coins of {symbol} at market price")
        except Exception as e:
            self.log_message(f"Error buying {shares} coins of {symbol}: {e}")
       
    def log_message(self, message):
        print(message)
        with open('backtest_log.csv', 'a') as f:
            writer = csv.writer(f)
            writer.writerow([dt.now(), message])

    def get_position(self, symbol):
        return self.positions.get(symbol, False)

    def get_last_price(self, symbol):
        return self.exchange.fetch_ticker(symbol)['last']
    
    def sell_all(self, symbol, entry_price):
        current_price = self.get_last_price(symbol)
        if self.get_position(symbol):
            # TODO - Redefine the logic for selling and work on whether should follow volatilty or the backtest sale logic
            dropping_price =  entry_price * 0.995
            higher_than_earlier_price = entry_price * 1.015
            if current_price < dropping_price or current_price >= higher_than_earlier_price:
                shares = self.shares_per_ticker[symbol]
                sale_value = shares * current_price
                sale_value -= sale_value * self.fees  # Subtract fees
                self.portfolio_value += sale_value
                self.log_message(f"Selling all for {symbol} at {current_price} ")
                self.positions[symbol] = False

    def run_live_trading(self):
        print("Running live trading...")
        print(f"Starting with a portfolio value of :{self.portfolio_value}")
        volatile_tickers = self.fetch_volatile_tickers_lively()
        self.symbols = [ticker['symbol'] for ticker in volatile_tickers]
        
        # Allocate 30% to the highest volatility ticker and 70% to the rest
        if volatile_tickers:
            highest_volatility_ticker = volatile_tickers[0]
            highest_volatility_allocation = self.portfolio_value * 0.3
            rest_allocation = self.portfolio_value * 0.7 / (len(volatile_tickers) - 1) if len(volatile_tickers) > 1 else 0

        for ticker in volatile_tickers:
            symbol = ticker['symbol']
            initial_price_trading = ticker['initial_price']
            allocation = highest_volatility_allocation if symbol == highest_volatility_ticker['symbol'] else rest_allocation
            shares = allocation / initial_price_trading
            self.shares_per_ticker[symbol] = shares
            self.positions[symbol] = True
            self.data[symbol] = []  # Initialize the data list for the symbol
            self.log_message(f"Bought {shares} coins of {symbol} at {initial_price_trading}")
        
        for _ in range(60):  
            for symbol in self.symbols:
                if self.get_position(symbol):
                    current_price = self.get_last_price(symbol)
                    entry_price = self.data[symbol][0] if symbol in self.data and self.data[symbol] else current_price
                    self.data[symbol].append(current_price)
                    if current_price < entry_price * 0.995 or current_price >= entry_price * 1.015:
                        self.sell_all(symbol, entry_price)
            #time.sleep(60)  # Wait for 1 minute

        # Sell everything at the end of the backtest
        for symbol in self.symbols:
            if self.get_position(symbol):
                self.sell_all(symbol, self.data[symbol][0])

        # Calculate final portfolio value
        final_portfolio_value = 0
        for symbol in self.symbols:
            if symbol in self.shares_per_ticker:
                final_portfolio_value += self.shares_per_ticker[symbol] * self.get_last_price(symbol)
        final_portfolio_value -= final_portfolio_value * self.fees  # Subtract fees

        self.log_message(f"Final portfolio value: {final_portfolio_value}")
if __name__ == "__main__":
    strategy = SwingHigh()
    strategy.run_live_trading()