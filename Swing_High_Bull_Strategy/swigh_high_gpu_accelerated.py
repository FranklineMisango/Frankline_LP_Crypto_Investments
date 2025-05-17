import ccxt
import numpy as np
import cupy as cp
from numba import cuda, njit
import timeit
import csv
from datetime import datetime as dt, timedelta
import pytz
import asyncio
import aiohttp

class SwingHigh():
    def __init__(self):
        self.exchange = ccxt.okx()
        self.initial_gains = {}
        self.data = {}
        self.order_numbers = {}
        self.shares_per_ticker = {}
        self.positions = {}
        self.portfolio_value = 1000  # Initial portfolio value
        self.fees = 0.006  # Trading fee (0.6%)

    @staticmethod
    @cuda.jit
    def calculate_gains(initial_prices, current_prices, gains):
        idx = cuda.grid(1)
        if idx < initial_prices.size:
            gains[idx] = (current_prices[idx] - initial_prices[idx]) / initial_prices[idx] * 100

    @staticmethod
    @njit
    def process_data(initial_prices, current_prices):
        gains = np.zeros_like(initial_prices, dtype=np.float32)
        for i in range(initial_prices.size):
            gains[i] = (current_prices[i] - initial_prices[i]) / initial_prices[i] * 100
        return gains

    async def fetch_data(self, symbol, since):
        loop = asyncio.get_event_loop()
        async with aiohttp.ClientSession() as session:
            try:
                data = await loop.run_in_executor(None, self.get_minute_data, symbol, since)
                return data
            except Exception as e:
                print(f"Error fetching data for {symbol}: {e}")
                return None

    async def fetch_all_data(self, symbols, since):
        tasks = [self.fetch_data(symbol, since) for symbol in symbols]
        return await asyncio.gather(*tasks)

    async def fetch_the_volatile_cryptocurrencies(self, hours):
        hkt = pytz.timezone('Asia/Hong_Kong')
        now = dt.now(hkt)
        print(f"Fetching coin prices from Binance from {hours} hour(s) ago to now which is {now} HKT")
        since = int((now - timedelta(hours=hours)).timestamp() * 1000)
        #markets = self.exchange.load_markets()
        markets = ["BTC/USDT", "ETH/USDT"]
        volatile_tickers = []

        initial_prices = []
        current_prices = []
        symbols = []

        # Fetch data asynchronously
        symbols_to_fetch = [symbol for symbol in markets if '/USDT' in symbol]
        data_list = await self.fetch_all_data(symbols_to_fetch, since)

        for i, symbol in enumerate(symbols_to_fetch):
            data = data_list[i]
            if data:
                initial_prices.append(data[0][1])  # Opening price hours ago
                current_prices.append(data[-1][4])  # Closing price now
                symbols.append(symbol)

        # Convert to CuPy arrays for GPU processing
        initial_prices = cp.array(initial_prices, dtype=cp.float32)
        current_prices = cp.array(current_prices, dtype=cp.float32)
        gains = cp.zeros_like(initial_prices)

        threads_per_block = 128
        blocks_per_grid = (initial_prices.size + (threads_per_block - 1)) // threads_per_block
        self.calculate_gains[blocks_per_grid, threads_per_block](initial_prices, current_prices, gains)

        # Copy gains back to CPU from GPU
        gains = cp.asnumpy(gains)

        for i, symbol in enumerate(symbols):
            gain = gains[i]
            num_trades = self.exchange.fetch_trades(symbol, since=since)
            if gain >= 2:
                volatile_tickers.append({
                    'symbol': symbol,
                    'initial_price': initial_prices[i],
                    'current_price': current_prices[i],
                    '%change': gain,
                    'num_trades': num_trades
                })
                self.initial_gains[symbol] = gain
            elif symbol in self.initial_gains and gain < self.initial_gains[symbol] * 0.95:
                volatile_tickers = [ticker for ticker in volatile_tickers if ticker['symbol'] != symbol]
                del self.initial_gains[symbol]

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

    def get_last_price(self, symbol):
        return self.exchange.fetch_ticker(symbol)['last']

    def sell_all(self, symbol, entry_price):
        current_price = self.get_last_price(symbol)
        if self.get_position(symbol):
            dropping_price = entry_price * 0.995
            higher_than_earlier_price = entry_price * 1.015
            if current_price < dropping_price or current_price >= higher_than_earlier_price:
                shares = self.shares_per_ticker[symbol]
                sale_value = shares * current_price
                sale_value -= sale_value * self.fees  # Subtract fees
                self.portfolio_value += sale_value
                self.log_message(f"Selling all for {symbol} at {current_price} ")
                self.positions[symbol] = False

    async def run_backtest(self):
        volatile_tickers = await self.fetch_the_volatile_cryptocurrencies(hours=24)
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

import nest_asyncio
nest_asyncio.apply()

if __name__ == "__main__":
    start_time = timeit.default_timer()
    strategy = SwingHigh()
    start_time = timeit.default_timer()
    asyncio.run(strategy.run_backtest())
    elapsed = timeit.default_timer() - start_time
    print(f"Backtest completed in {elapsed:.2f} seconds.")

