
#source : https://github.com/StephanAkkerman/binance-data?tab=readme-ov-file

import pandas as pd
from binance.client import Client

# Initialize the Client
client = Client()

def fetchData(symbol = "BTCUSDT", amount = 1, timeframe = '1d', as_csv = False, file_name = None):
    """
    Pandas DataFrame with the latest OHLCV data from Binance.

    Parameters
    --------------
    symbol : string, combine the coin you want to get with the pair. For instance "BTCUSDT" for BTC/USDT.
    amount : int, the amount of rows that should be returned divided by 500. For instance 2 will return 1000 rows.
    timeframe : string, the timeframe according to the Binance API. For instance "4h" for the 4 hour candles.
    All the timeframe options are: '1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1M'
    """
    # https://python-binance.readthedocs.io/en/latest/binance.html#binance.client.Client.get_klines

    # ms calculations based on: http://convertlive.com/nl/u/converteren/minuten/naar/milliseconden
    # 1m = 60000 ms
    if timeframe == "1m":
        diff = 60000
    elif timeframe == "3m":
        diff = 3 * 60000
    elif timeframe == "5m":
        diff = 5 * 60000
    elif timeframe == "15m":
        diff = 15 * 60000
    elif timeframe == "30m":
        diff = 30 * 60000

    # 1h = 3600000 ms
    elif timeframe == "1h":
        diff = 3600000
    elif timeframe == "2h":
        diff = 2 * 3600000
    elif timeframe == "4h":
        diff = 4 * 3600000
    if timeframe == "6h":
        diff = 6 * 3600000
    elif timeframe == "8h":
        diff = 8 * 3600000
    elif timeframe == "12h":
        diff = 12 * 3600000

    # 1d = 86400000 ms
    elif timeframe == "1d":
        diff = 86400000
    elif timeframe == "3d":
        diff = 3 * 86400000
    elif timeframe == "1W":
        diff = 604800000
    elif timeframe == "1M":
        diff = 2629800000

    else:
        print("Invalid timeframe")
        return

    # Get current time, by getting the latest candle
    end = client.get_klines(symbol=symbol, interval=timeframe)[-1][0]

    # The list that keeps track of all the data before converting it to a DataFrame
    candleList = []

    # Get the amount of data specified by amount parameter
    for _ in range(amount):
        # Make the list from oldest to newest
        candleList = (
            client.get_klines(symbol=symbol, interval=timeframe, endTime=end)
            + candleList
        )

        # Calculate the end point by using the difference in ms per candle
        end = end - diff * 500

    df = pd.DataFrame(candleList)

    # Only the columns containt the OHLCV data
    df.drop(columns=[6, 7, 8, 9, 10, 11], axis=1, inplace=True)
    df.columns = ["date", "open", "high", "low", "close", "volume"]

    # Convert time in ms to datetime
    df["date"] = pd.to_datetime(df["date"], unit="ms")

    # The default values are string, so convert these to numeric values
    df["open"] = pd.to_numeric(df["open"])
    df["high"] = pd.to_numeric(df["high"])
    df["low"] = pd.to_numeric(df["low"])
    df["close"] = pd.to_numeric(df["close"])
    df["volume"] = pd.to_numeric(df["volume"])

    # Volume in USDT
    df["volume"] = df.volume * df.close

    if as_csv:
        if file_name == None:
            file_name = symbol + "_" + timeframe + ".csv"

        df.to_csv(f"data/{file_name}",index=False)
        print(f"Succesfully saved {len(df)} rows to {file_name}")

    return df