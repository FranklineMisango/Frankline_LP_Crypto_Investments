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
from binance.spot import Spot

client = Spot()
client = Spot(api_key=os.getenv('Binance_API_KEY'), api_secret=os.getenv('Binance_secret_KEY'))

api_key = os.getenv('Binance_API_KEY')
api_secret = os.getenv('Binance_secret_KEY')

# Initialize Binance client
fetcher_client = Client(api_key, api_secret)

class SwingHigh():

    def __init__(self):

        self.initial_gains = {}
        self.data = {}
        self.order_numbers = {}
        self.shares_per_ticker = {}
        self.positions = {}
        self.fees = 0.001  # Binance trading fee (0.1%)

    def get_stock_data(self,ticker, since):
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
    
    def fetch_volatile_tickers_for_last_30_minutes(self):
        hkt = pytz.timezone('Asia/Hong_Kong')
        now = dt.now(hkt)
        since = int((now - timedelta(minutes=30)).timestamp() * 1000)
        markets = fetcher_client.get_all_tickers()
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



    def fetch_volatile_tickers_lively(self):
        print("Fetching volatile tickers for the last 30 minutes...")
        volatile_tickers = self.fetch_volatile_tickers_for_last_30_minutes()
        
        with open('30_minutes_dynamic_updates_volatile_tickers.csv', 'w') as f:
            writer = csv.writer(f)
            writer.writerow(['Crypto Symbol', 'initial_price', 'current_price', 'Percentage Change (%)', 'num_trades', 'Volume'])
            for ticker in volatile_tickers.values():
                writer.writerow([ticker['Crypto Symbol'], ticker['initial_price'], ticker['current_price'], ticker['Percentage Change'], ticker['num_trades'], ticker['Volume ']])
        
        print("Updated volatile tickers list.")
        return volatile_tickers

    
    # customize for live ordering and selling 
    def buy_order(self, symbol, shares):
            try:
                order = client.order_market_buy(symbol=symbol, quantity=shares)
                self.order_numbers[symbol] = order['orderId']
                self.log_message(f"Buying {shares} coins of {symbol} at market price")
            except Exception as e:
                self.log_message(f"Error buying {shares} coins of {symbol}: {e}")
       
    def log_message(self, message): 
        #TODO - Send to my E-mail every 1 hour the live running actions and the portfolio value
        print(message)
        with open('Live_Running_Actions.csv', 'a') as f:
            writer = csv.writer(f)
            writer.writerow([dt.now(), message])

    def get_position(self, symbol):
        return self.positions.get(symbol, False)


    def get_last_price(self, symbol):
        try:
            ticker = client.get_symbol_ticker(symbol=symbol)
            return float(ticker['price'])
        except Exception as e:
            self.log_message(f"Error fetching last price for {symbol}: {e}")
            return None
    
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
                    order = client.order_market_sell(symbol=symbol, quantity=shares)
                    sale_value = shares * current_price
                    sale_value -= sale_value * self.fees  # Subtract fees
                    self.portfolio_value += sale_value
                    self.log_message(f"Selling all for {symbol} at {current_price}")
                    self.positions[symbol] = False
                except Exception as e:
                    self.log_message(f"Error selling {shares} coins of {symbol}: {e}")

    def run_live_trading(self, duration_minutes):
        print("Running live trading...")
        account_info = client.account()['balances']
        for item in account_info:
            if item['asset'] == 'USDT':
                self.portfolio_value = float(item['free'])
                print(f"Starting with a portfolio value of : {self.portfolio_value} USDT")
        
        start_time = time.time()
        end_time = start_time + duration_minutes * 60

        while time.time() < end_time:
            volatile_tickers = self.fetch_volatile_tickers_lively()
            new_symbols = [ticker for ticker in volatile_tickers]

            # Sell tickers that are no longer in the top volatile tickers
            for symbol in list(self.positions.keys()):
                if symbol not in new_symbols:
                    self.sell_all(symbol, self.data[symbol][0]['initial_price'])

            # Buy new top volatile tickers
            for ticker in volatile_tickers.values():
                symbol = ticker['Crypto Symbol']
                initial_price_trading = ticker['initial_price']
                if symbol not in self.positions or not self.positions[symbol]:
                    allocation = self.portfolio_value / len(volatile_tickers)
                    shares = allocation / initial_price_trading
                    self.shares_per_ticker[symbol] = shares
                    self.positions[symbol] = True
                    self.data[symbol] = [ticker]  # Initialize the data list for the symbol
                    self.buy_order(symbol, shares)
                    self.log_message(f"Bought {shares} coins of {symbol} at {initial_price_trading}")

            print("Waiting for 5 minutes before volatility checks...")
            time.sleep(300)  # Wait for 5 minutes before fetching again

        # Sell all positions after the duration
        for symbol in list(self.positions.keys()):
            self.sell_all(symbol, self.data[symbol][0]['initial_price'])

        # Calculate final portfolio value
        final_portfolio_value = 0
        for symbol in self.shares_per_ticker:
            final_portfolio_value += self.shares_per_ticker[symbol] * self.get_last_price(symbol)
        final_portfolio_value -= final_portfolio_value * self.fees  # Subtract fees

        self.log_message(f"Final portfolio value: {final_portfolio_value}")

if __name__ == "__main__":
    strategy = SwingHigh()
    strategy.run_live_trading(duration_minutes=60)  # Run live trading for specified minutes