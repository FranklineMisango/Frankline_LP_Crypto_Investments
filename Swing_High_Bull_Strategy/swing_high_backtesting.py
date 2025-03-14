import ccxt
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime as dt
from datetime import timedelta
import csv
import time
import timeit
import pytz

#TODO - Find a fix for : Error fetching data for BTCST/USDT:USDT: binance {"code":-1122,"msg":"Invalid symbol status."}

class SwingHigh():
    def __init__(self):
        self.exchange = ccxt.binance()
        self.initial_gains = {}
        self.data = {}
        self.order_numbers = {}
        self.shares_per_ticker = {}
        self.positions = {}
        self.portfolio_value = 1000  # Initial portfolio value
        self.fees = 0.1/100  # Binance trading fee (0.1%)

    def fetch_the_volatile_cryptocurrencies(self, hours):
        hkt = pytz.timezone('Asia/Hong_Kong')
        now = dt.now(hkt)
        print(f"Fetching coin prices from {self.exchange} from {hours} hour(s) ago to now which is {now} HKT")
        since = int((now - timedelta(hours=hours)).timestamp() * 1000)
        markets = self.exchange.load_markets()
        #markets = ["BTC/USDT", "ETH/USDT"]
        
        #markets = ['PI/USDT']

        volatile_tickers = []

        for symbol in markets:
            if '/USDT' in symbol:
                try:
                    data = self.get_minute_data(symbol, since)
                    if data:
                        initial_price = data[0][1]  # Opening price hours ago
                        current_price = data[-1][4]  # Closing price now
                        gain = (current_price - initial_price) / initial_price * 100
                        num_trades = self.exchange.fetch_trades(symbol, since=since)

                        if gain >= 2:
                            volatile_tickers.append({
                                'symbol': symbol,
                                'initial_price': initial_price,
                                'current_price': current_price,
                                '%change': gain,
                                'num_trades': num_trades
                            })
                            self.initial_gains[symbol] = gain
                        elif symbol in self.initial_gains and gain < self.initial_gains[symbol] * 0.95:
                            volatile_tickers = [ticker for ticker in volatile_tickers if ticker['symbol'] != symbol]
                            del self.initial_gains[symbol]
                except ccxt.BaseError as e:
                    print(f"Error fetching data for {symbol}: {e}")

        volatile_tickers.sort(key=lambda x: x['%change'], reverse=True)
        with open('volatile_tickers.csv', 'w') as f:
            writer = csv.writer(f)
            writer.writerow(['symbol', 'initial_price', 'current_price', '%change', 'num_trades'])
            for ticker in volatile_tickers:
                writer.writerow([ticker['symbol'], ticker['initial_price'], ticker['current_price'], ticker['%change'], ticker['num_trades']])
        return volatile_tickers

    def get_minute_data(self, symbol, since):
        ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe='1m', since=since)
        return ohlcv

    def log_message(self, message):
        print(message)
        with open('backtest_log.csv', 'a') as f:
            writer = csv.writer(f)
            writer.writerow([dt.now(), message])

    def get_position(self, symbol):
        return self.positions.get(symbol, False)

    #TODO - problematic logic for last price - should be the last price of the candle. ie if the price at 12.00 is 100 and at 12.01 is 101, the last price should be 101 and not at the dt.now price
    def get_last_price(self, symbol):
        return self.exchange.fetch_ticker(symbol)['last']
    
    def sell_all(self, symbol, entry_price):
        current_price = self.get_last_price(symbol)
        if self.get_position(symbol):
            dropping_price =  entry_price * 0.995
            higher_than_earlier_price = entry_price * 1.015
            if current_price < dropping_price or current_price >= higher_than_earlier_price:
                shares = self.shares_per_ticker[symbol]
                sale_value = shares * current_price
                sale_value -= sale_value * self.fees  # Subtract fees
                self.portfolio_value += sale_value
                self.log_message(f"Selling all for {symbol} at {current_price} ")
                self.positions[symbol] = False

    def run_backtest(self):
        volatile_tickers = self.fetch_the_volatile_cryptocurrencies(hours=24)
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
    start_time = timeit.default_timer()
    strategy.run_backtest()
    elapsed = timeit.default_timer() - start_time
    print(f"Backtest completed in {elapsed:.2f} seconds.")
