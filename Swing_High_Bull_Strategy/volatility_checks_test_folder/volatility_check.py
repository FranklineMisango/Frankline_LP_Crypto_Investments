from datetime import datetime as dt, timedelta
import ccxt
import csv
import matplotlib.pyplot as plt

class CryptoVolatilityFetcher:
    def __init__(self):
        self.exchange = ccxt.binance()
        self.initial_gains = {}

    def fetch_the_volatile_cryptocurrencies(self, hours=1):
        now = dt.now()
        since = int((now - timedelta(hours=hours)).timestamp() * 1000)
        markets = self.exchange.load_markets()
        volatile_tickers = []

        for symbol in markets:
            if '/USDT' in symbol:
                try:
                    data = self.get_minute_data(symbol, since)
                    if data:
                        initial_price = data[0][1]  # Opening price hours ago
                        current_price = data[-1][4]  # Closing price now
                        gain = (current_price - initial_price) / initial_price * 100
                        num_trades = len(data)

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
        return volatile_tickers

    def get_minute_data(self, symbol, since):
        ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe='1m', since=since)
        return ohlcv

# Create an instance of the class and call the method
fetcher = CryptoVolatilityFetcher()
volatile_cryptocurrencies = fetcher.fetch_the_volatile_cryptocurrencies(hours=2)  # Specify the number of hours here

# Save the result in a CSV
with open('volatile_cryptocurrencies.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['symbol', 'initial_price', 'current_price', '%change', 'num_trades'])
    writer.writeheader()
    for item in volatile_cryptocurrencies:
        writer.writerow(item)

# Print the volatile cryptocurrencies
print(volatile_cryptocurrencies)

# Plot the volatility chart
symbols = [item['symbol'] for item in volatile_cryptocurrencies]
changes = [item['%change'] for item in volatile_cryptocurrencies]

plt.figure(figsize=(10, 5))
plt.barh(symbols, changes, color='skyblue')
plt.xlabel('% Change')
plt.ylabel('Cryptocurrency')
plt.title('Cryptocurrency Volatility')
plt.gca().invert_yaxis()
plt.savefig('volatile_cryptocurrencies.png')
plt.show()