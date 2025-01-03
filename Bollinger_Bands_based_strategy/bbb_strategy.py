
from datetime import datetime
from lumibot.entities import Asset, Order
from lumibot.strategies import Strategy
from lumibot.backtesting import CcxtBacktesting
from pandas import DataFrame
import ccxt

class BollingerBandsBased(Strategy):
    
    def initialize(self, asset:tuple[Asset,Asset] = None,
                cash_at_risk:float=.25,window:int=21):
        if asset is None:
            raise ValueError("You must provide a valid asset pair")
        
        self.set_market("24/7")
        self.sleeptime = "1D"
        self.asset = asset
        self.base, self.quote = asset
        self.window = window
        self.symbol = f"{self.base.symbol}/{self.quote.symbol}"
        self.last_trade = None
        self.order_quantity = 0.0
        self.cash_at_risk = cash_at_risk

    def _position_sizing(self):
        cash = self.get_cash()
        last_price = self.get_last_price(asset=self.asset,quote=self.quote)
        quantity = round(cash * self.cash_at_risk / last_price,0)
        return cash, last_price, quantity

    def _get_historical_prices(self):
        return self.get_historical_prices(asset=self.asset,length=None,
                                    timestep="day",quote=self.quote).df

    def _get_bbands(self,history_df:DataFrame):
        num_std_dev = 2.0
        close = 'close'

        df = DataFrame(index=history_df.index)
        df[close] = history_df[close]
        df['bbm'] = df[close].rolling(window=self.window).mean()
        df['bbu'] = df['bbm'] + df[close].rolling(window=self.window).std() * num_std_dev
        df['bbl'] = df['bbm'] - df[close].rolling(window=self.window).std() * num_std_dev
        df['bbb'] = (df['bbu'] - df['bbl']) / df['bbm']
        df['bbp'] = (df[close] - df['bbl']) / (df['bbu'] - df['bbl'])
        return df

    def on_trading_iteration(self):

        current_dt = self.get_datetime()
        cash, last_price, quantity = self._position_sizing()
        history_df = self._get_historical_prices()
        bbands = self._get_bbands(history_df)
        prev_bbp = bbands[bbands.index < current_dt].tail(1).bbp.values[0]

        if prev_bbp < -0.13 and cash > 0 and self.last_trade != Order.OrderSide.BUY and quantity > 0.0:
            order = self.create_order(self.base,
                                    quantity,
                                    side = Order.OrderSide.BUY,
                                    type = Order.OrderType.MARKET,
                                    quote=self.quote)
            self.submit_order(order)
            self.last_trade = Order.OrderSide.BUY
            self.order_quantity = quantity
            self.log_message(f"Last buy trade was at {current_dt}")
        elif prev_bbp > 1.2 and self.last_trade != Order.OrderSide.SELL and self.order_quantity > 0.0:
            order = self.create_order(self.base,
                                    self.order_quantity,
                                    side = Order.OrderSide.SELL,
                                    type = Order.OrderType.MARKET,
                                    quote=self.quote)
            self.submit_order(order)
            self.last_trade = Order.OrderSide.SELL
            self.order_quantity = 0.0
            self.log_message(f"Last sell trade was at {current_dt}")

print("Check the Market Pairs from Binance (Modify code for other exchanges) below first before running the backtest")
print("Loading Market Pairs from Binance.....")
exchange = ccxt.binance()
markets = exchange.load_markets()

# Print market pairs in a readable format
for market in markets.keys():
    print(market)

# Allow the user to paste the market pair in form of A /B 
base_symbol = input("Enter the base symbol for backtesting : ") 
quote_symbol = input("Enter the quote symbol for run against base symbol  : ")
start_date = datetime(2024,1,1)
end_date = datetime(2024,12,31)
asset = (Asset(symbol=base_symbol, asset_type="crypto"),
        Asset(symbol=quote_symbol, asset_type="crypto"))

exchange_id = "binance"  #"kucoin" #"bybit" #"okx" #"bitmex" # "binance"

kwargs = {
    # "max_data_download_limit":10000, # optional
    "exchange_id":exchange_id,
}
CcxtBacktesting.MIN_TIMESTEP = "day"
results, strat_obj = BollingerBandsBased.run_backtest(
    CcxtBacktesting,
    start_date,
    end_date,
    benchmark_asset=f"{base_symbol}/{quote_symbol}",
    quote_asset=Asset(symbol=quote_symbol, asset_type="crypto"),
    parameters={
            "asset":asset,
            "cash_at_risk":.25,
            "window":21,},
    **kwargs,
)