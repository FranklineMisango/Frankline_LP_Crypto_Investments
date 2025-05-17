import ccxt
from prettytable import PrettyTable
import os

class FindTopGainers():
    def __init__(self):
        self.exchange = ccxt.binance()
        self.initial_gains = {}
        self.data = {}

    def find_top_gainers(self):
        tickers = self.exchange.fetch_tickers()
        filtered_tickers = [ticker for ticker in tickers.values() if ticker['percentage'] is not None]
        sorted_tickers = sorted(filtered_tickers, key=lambda x: x['percentage'], reverse=True)
        table = PrettyTable()
        table.field_names = ["Symbol", "Price", "Percentage Change"]
        for ticker in sorted_tickers[:20]:
            table.add_row([ticker['symbol'], ticker['last'], ticker['percentage']])
        print(table)

Fetch_top_tickers = FindTopGainers()
Fetch_top_tickers.find_top_gainers()