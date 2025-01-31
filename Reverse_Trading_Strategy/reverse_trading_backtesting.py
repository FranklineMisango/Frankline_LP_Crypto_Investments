import ccxt
import pandas as pd
import numpy as np
import plotly.graph_objects as go


class ReverseTradingBacktest:

    def fetch_data(self, exchange_id, symbol, timeframe='1d', limit=1000, start_date=None, end_date=None):
        """Fetch OHLCV data from an exchange using CCXT and filter by date range."""
        exchange_class = getattr(ccxt, exchange_id)
        exchange = exchange_class()
        
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)

        # Filter data by start and end date if provided
        if start_date:
            df = df[df.index >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df.index <= pd.to_datetime(end_date)]
        
        return df

    def calculate_support_resistance(self, df):
        """Calculate support and resistance levels using rolling min/max."""
        df['support'] = df['low'].rolling(window=14).min()
        df['resistance'] = df['high'].rolling(window=14).max()
        return df

    def identify_reversal_signals(self, df):
        """Check for buy/sell reversal signals based on support/resistance levels."""
        latest = df.iloc[-1]
        previous = df.iloc[-2]
        
        if latest['high'] >= latest['resistance'] and latest['close'] < previous['close']:
            return 'sell'
        
        if latest['low'] <= latest['support'] and latest['close'] > previous['close']:
            return 'buy'

        return 'none'

    def run_backtest(self, exchange_id, symbol, initial_balance=100, start_date=None, end_date=None):
        """Runs a simple backtest and plots P&L."""
        df = self.fetch_data(exchange_id, symbol, start_date=start_date, end_date=end_date)
        df = self.calculate_support_resistance(df)

        balance = initial_balance
        position = 0
        entry_price = 0
        trade_log = []

        for i in range(15, len(df)):  # Start after enough data is collected
            signal = self.identify_reversal_signals(df.iloc[:i])

            if signal == 'buy' and position == 0:
                entry_price = df.iloc[i]['close']
                position = balance / entry_price  # Buy as many units as possible
                balance = 0  # Use full balance
                trade_log.append(('BUY', df.index[i], entry_price))

            elif signal == 'sell' and position > 0:
                balance = position * df.iloc[i]['close']  # Sell at current price
                position = 0
                trade_log.append(('SELL', df.index[i], df.iloc[i]['close']))

        # Final value (assuming we sell at the last close price)
        final_value = balance + (position * df.iloc[-1]['close'])
        print(f"Initial Balance: {initial_balance}")
        print(f"Final Balance: {final_value}")
        print(f"Total Return: {((final_value / initial_balance) - 1) * 100:.2f}%")

        # Plot price & trade signals using Plotly for interactivity
        fig = go.Figure()

        # Add price data as a line chart
        fig.add_trace(go.Scatter(x=df.index, y=df['close'], mode='lines', name='Price',
                                line=dict(color='royalblue', width=2)))

        # Add buy and sell markers
        buy_dates = [trade[1] for trade in trade_log if trade[0] == 'BUY']
        buy_prices = [trade[2] for trade in trade_log if trade[0] == 'BUY']
        sell_dates = [trade[1] for trade in trade_log if trade[0] == 'SELL']
        sell_prices = [trade[2] for trade in trade_log if trade[0] == 'SELL']

        fig.add_trace(go.Scatter(x=buy_dates, y=buy_prices, mode='markers', name='Buy',
                                marker=dict(color='green', size=10, symbol='triangle-up')))
        fig.add_trace(go.Scatter(x=sell_dates, y=sell_prices, mode='markers', name='Sell',
                                marker=dict(color='red', size=10, symbol='triangle-down')))

        # Customize layout
        fig.update_layout(
            title=f"Backtest Results for {symbol}",
            xaxis_title="Date",
            yaxis_title="Price",
            legend_title="Legend",
            template='plotly_white',  # Clean background
            font=dict(family='Arial, sans-serif', size=12, color='black'),
            xaxis=dict(showgrid=True, gridcolor='lightgrey'),  # Add gridlines
            yaxis=dict(showgrid=True, gridcolor='lightgrey'),
            hovermode='x unified'  # Unified hover
        )

        # Add annotations for buy/sell signals
        for trade in trade_log:
            action, date, price = trade
            fig.add_annotation(
                x=date,
                y=price,
                text=f"{action} at {price:.2f}",
                showarrow=True,
                arrowhead=2,
                ax=0,
                ay=-40 if action == 'BUY' else 40,
                font=dict(color='green' if action == 'BUY' else 'red')
            )

        # Show the interactive plot
        fig.show()


# Run the custom backtest with specified start and end dates
backtest = ReverseTradingBacktest()
backtest.run_backtest(
    exchange_id="binance", 
    symbol="BTC/USDT", 
    start_date="2024-01-01", 
    end_date="2025-01-01"
)

