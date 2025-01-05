from datetime import datetime
import pandas as pd
import ccxt

class ScalpingStrategy:
    def __init__(self, symbol, quantity, profit_threshold=0.001, stop_loss_threshold=0.001):
        self.symbol = symbol
        self.quantity = quantity
        self.profit_threshold = profit_threshold
        self.stop_loss_threshold = stop_loss_threshold
        self.exchange = ccxt.binance()
        self.data = None

    #Fetch data using binance connectors
    def get_minute_data(self, start_date, end_date, interval='1m'):
        since = self.exchange.parse8601(start_date.isoformat())
        end = self.exchange.parse8601(end_date.isoformat())
        ohlcv = []
        while since < end:
            data = self.exchange.fetch_ohlcv(self.symbol, timeframe=interval, since=since, limit=1000)
            if not data:
                break
            since = data[-1][0] + 1
            ohlcv.extend(data)
        frame = pd.DataFrame(ohlcv, columns=['Time', 'Open', 'High', 'Low', 'Close', 'Volume'])
        print(frame)
        frame = frame.set_index('Time')
        frame.index = pd.to_datetime(frame.index, unit='ms')
        frame = frame.astype(float)
        return frame

    def place_order(self, side):
        print(f"Simulating {side} order for {self.quantity} {self.symbol}")
        return True

    def run_backtest(self, start_date, end_date):
        print("starting backtest")
        self.data = self.get_minute_data(start_date, end_date)
        buy_price = self.data['Close'].iloc[0]
        self.place_order('buy') # Check out the df shape from ccxt and binance as well
        
        for i in range(1, len(self.data)):
            current_price = self.data['Close'].iloc[i]
            profit = (current_price - buy_price) / buy_price
            loss = (buy_price - current_price) / buy_price
            
            if profit >= self.profit_threshold:
                self.place_order('sell')
                print(f"Trade closed with profit: {profit * 100:.2f}%")
                break
            elif loss >= self.stop_loss_threshold:
                self.place_order('sell')
                print(f"Trade closed with loss: {loss * 100:.2f}%")
                break

if __name__ == "__main__":
    symbol = 'XLM/USDT'
    quantity = 100000  # Adjust the quantity as needed
    start_date = datetime(2025, 1, 1)
    end_date = datetime(2025, 1, 2)
    strategy = ScalpingStrategy(symbol, quantity)
    strategy.run_backtest(start_date, end_date)