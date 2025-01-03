import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import math
import plotly.graph_objects as go
import os
from binance.client import Client

# Get API keys from environment variables
api_key = os.getenv('Binance_API_KEY')
api_secret = os.getenv('Binance_secret_KEY')


# Initialize Binance client
client = Client(api_key, api_secret)

class GBM:
    # Class for Geometric Brownian Motion simulation
    def __init__(self, initial_price, drift, volatility, time_period, total_time):
        self.initial_price = initial_price
        self.drift = drift
        self.volatility = volatility
        self.time_period = time_period
        self.total_time = total_time
        self.simulate()

    def simulate(self):
        self.prices = [self.initial_price]
        while self.total_time > 0:
            dS = self.prices[-1] * (self.drift * self.time_period + 
                                    self.volatility * np.random.normal(0, math.sqrt(self.time_period)))
            self.prices.append(self.prices[-1] + dS)
            self.total_time -= self.time_period

def get_stock_data(ticker, start, end):
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
    return df
    

# Define start_date and end_date as strings
start_date = '2020-01-01'
end_date = '2023-01-01'

ticker = input("Enter the Crypto ticker symbol for fetching : ")
stock = ticker
index = '^GSPC' #experiment with the index changes to crypto std

# Fetching historical data from Yahoo Finance
stock_data = get_stock_data(stock, start_date, end_date)
index_data = yf.download(index, start_date, end_date)

# Resampling data to monthly frequency and calculating returns
stock_monthly = stock_data.resample('M').last()
index_monthly = index_data.resample('M').last()
combined_data = pd.DataFrame({'Crypto': stock_monthly['Close'], 
                            'Index': index_monthly['Adj Close']})
combined_returns = combined_data.pct_change().dropna()

# Calculating covariance matrix for the returns
cov_matrix = np.cov(combined_returns['Crypto'], combined_returns['Index'])

# Parameters for GBM simulation
num_simulations = 20
initial_price = stock_data['Close'][-1]
drift = 0.24
volatility = math.sqrt(cov_matrix[0, 0])
time_period = 1 / 365
total_time = 1

# Running multiple GBM simulations
simulations = [GBM(initial_price, drift, volatility, time_period, total_time) for _ in range(num_simulations)]

# Plotting the simulations
fig = go.Figure()
for i, sim in enumerate(simulations):
    fig.add_trace(go.Scatter(x=np.arange(len(sim.prices)), y=sim.prices, mode='lines', name=f'Simulation {i+1}'))

fig.add_trace(go.Scatter(x=np.arange(len(sim.prices)), y=[initial_price] * len(sim.prices),
                        mode='lines', name='Initial Price', line=dict(color='red', dash='dash')))
fig.update_layout(title=f'Geometric Brownian Motion for {stock.upper()}',
                xaxis_title='Time Steps',
                yaxis_title='Price')
fig.show()