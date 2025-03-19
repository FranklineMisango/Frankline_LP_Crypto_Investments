import ccxt
from prettytable import PrettyTable
import time
import threading
from concurrent.futures import ThreadPoolExecutor

class FindTopGainers():
    def __init__(self):
        self.exchange = ccxt.binance()
        self.data = {}
        self.top_gainers = []
        self.lock = threading.Lock()

    def fetch_recent_trades(self, symbol):
        since = self.exchange.milliseconds() - 5 * 60 * 1000  # 5 minutes ago
        trades = self.exchange.fetch_trades(symbol, since=since)
        return trades

    def calculate_percentage_change(self, trades):
        if not trades:
            return 0
        start_price = trades[0]['price']
        end_price = trades[-1]['price']
        percentage_change = ((end_price - start_price) / start_price) * 100
        return percentage_change

    def find_top_gainers(self):
        tickers = self.exchange.fetch_tickers()
        symbols = [ticker['symbol'] for ticker in tickers.values() if ticker['percentage'] is not None and '/USDT' in ticker['symbol']]
        percentage_changes = []

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(self.fetch_recent_trades, symbol): symbol for symbol in symbols}
            for future in futures:
                symbol = futures[future]
                trades = future.result()
                percentage_change = self.calculate_percentage_change(trades)
                percentage_changes.append((symbol, tickers[symbol]['last'], percentage_change))

        sorted_tickers = sorted(percentage_changes, key=lambda x: x[2], reverse=True)
        with self.lock:
            self.top_gainers = sorted_tickers[:5]

    def display_top_gainers(self):
        with self.lock:
            table = PrettyTable()
            table.field_names = ["Symbol", "Price", "Percentage Change (5 min)"]
            for ticker in self.top_gainers:
                table.add_row([ticker[0], ticker[1], ticker[2]])
            print(table)

    def run(self, duration_minutes):
        end_time = time.time() + duration_minutes * 60
        def update_gainers():
            while time.time() < end_time:
                self.find_top_gainers()
                time.sleep(1)  # Check every second

        update_thread = threading.Thread(target=update_gainers)
        update_thread.start()

        while time.time() < end_time:
            self.display_top_gainers()
            time.sleep(1)  # Display every second

        update_thread.join()

if __name__ == "__main__":
    strategy = FindTopGainers()
    strategy.run(duration_minutes=10)  # Run the algorithm for 10 minutes