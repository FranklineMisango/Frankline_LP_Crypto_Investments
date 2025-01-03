from datetime import datetime as dt
from binance.client import Client
import pandas as pd
import datetime
import os
from dotenv import load_dotenv
import plotly.graph_objects as go
import matplotlib.dates as mdates


#Attempting to use CCXT backtesting
from lumibot.backtesting import CcxtBacktesting

# Get API keys from environment variables
api_key = os.getenv('Binance_API_KEY')
api_secret = os.getenv('Binance_secret_KEY')

# Initialize Binance client
client = Client(api_key, api_secret)

def ema_strategy(start_date, end_date, ticker):
    ''' This tool plots the candlestick chart of a stock along with the Exponential Moving Average (EMA) of the stock's closing price.'''
    
    symbol = ticker
    start = start_date
    end = end_date

    # Read data
    
    klines = client.get_historical_klines(ticker, Client.KLINE_INTERVAL_1DAY, start, end)
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

    n = 15
    df["EMA"] = (
        df["Close"].ewm(ignore_na=False, span=n, min_periods=n, adjust=True).mean()
    )

    dfc = df.copy()
    dfc["VolumePositive"] = dfc["Open"] < dfc["Close"]
    dfc = dfc.reset_index()
    dfc["Open Time"] = pd.to_datetime(dfc["Open Time"])  # Convert Date column to datetime
    dfc["Close Time"] = dfc["Close"].apply(mdates.date2num)

    # Plotting Moving Average using Plotly
    trace_adj_close = go.Scatter(x=df.index, y=df["Close"], mode='lines', name='Close')
    trace_ema = go.Scatter(x=df.index, y=df["EMA"], mode='lines', name='EMA')
    layout_ma = go.Layout(title="EMA v Closing Price of " + str(n) + "-Day Exponential Moving Average",
                        xaxis=dict(title="Date"), yaxis=dict(title="Price"))
    fig_ma = go.Figure(data=[trace_adj_close, trace_ema], layout=layout_ma)
    fig_ma.update_layout(template='plotly_dark')

    # Plotting Candlestick with EMA using Plotly
    dfc = df.copy()
    dfc["VolumePositive"] = dfc["Open"] < dfc["Close"]

    trace_candlestick = go.Candlestick(x=dfc.index,
                                    open=dfc['Open'],
                                    high=dfc['High'],
                                    low=dfc['Low'],
                                    close=dfc['Close'],
                                    name='Candlestick')

    trace_ema = go.Scatter(x=df.index, y=df["EMA"], mode='lines', name='EMA')

    trace_volume = go.Bar(x=dfc.index, y=dfc['Volume'], marker=dict(color=dfc['VolumePositive'].map({True: 'green', False: 'red'})),
                        name='Volume')

    layout_candlestick = go.Layout(title="Coin " + str(symbol) + " Closing Price",
                                xaxis=dict(title="Date", type='date', tickformat='%d-%m-%Y'),
                                yaxis=dict(title="Price"),
                                yaxis2=dict(title="Volume", overlaying='y', side='right'))
    fig_candlestick = go.Figure(data=[trace_candlestick, trace_ema, trace_volume], layout=layout_candlestick)
    fig_candlestick.update_layout(template='plotly_dark')

    # Display Plotly figures in Streamlit
    fig_ma.show()
    fig_candlestick.show()


print("EMA Trading Strategy Visualization")
stock = input("Enter the Binance coin : ")
start = dt(2020, 1, 1)
end = dt.now()


start_str = start.strftime('%Y-%m-%d')
end_str = end.strftime('%Y-%m-%d')

ema_strategy(start_str, end_str, stock)
