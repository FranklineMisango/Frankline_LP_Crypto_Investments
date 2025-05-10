import os
import yfinance as yf
import threading
import concurrent.futures
from dotenv import load_dotenv
load_dotenv()
import datetime
import alpaca_trade_api as tradeapi
import time
import pandas as pd
import numpy as np
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import csv
import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objs as go
from datetime import datetime, timedelta
import json

# API keys and configuration
API_KEY = os.environ.get('APCA_API_KEY_ID')
API_SECRET = os.environ.get('APCA_API_SECRET_KEY')
APCA_API_BASE_URL = "https://paper-api.alpaca.markets"
EMAIL_USER = os.environ.get('EMAIL_USER')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')
EMAIL_RECEIVER = os.environ.get('EMAIL_RECEIVER')

class TradingDashboard:
    def __init__(self, long_short_instance):
        self.ls = long_short_instance
        self.app = dash.Dash(__name__)
        self.performance_data = {
            'timestamp': [],
            'equity': [],
            'long_value': [],
            'short_value': [],
            'daily_pnl': [],
            'total_pnl': []
        }
        self.positions_data = []
        self.orders_data = []
        
        # Setup dashboard layout
        self.setup_layout()
        
        # Create data directory if it doesn't exist
        if not os.path.exists('data'):
            os.makedirs('data')
        
        # Load backup data if it exists
        self.load_data()
        
        # Start data collection thread
        self.running = True
        self.update_thread = threading.Thread(target=self.update_data_thread)
        self.update_thread.daemon = True
        self.update_thread.start()
        
    def setup_layout(self):
        self.app.layout = html.Div([
            html.H1("Long-Short Trading Strategy Dashboard"),
            
            html.Div([
                html.Div([
                    html.H3("Account Summary"),
                    html.Div(id='account-summary')
                ], className='summary-box'),
                
                html.Div([
                    html.H3("Performance Metrics"),
                    html.Div(id='performance-metrics')
                ], className='summary-box')
            ], className='summary-row'),
            
            html.Div([
                dcc.Graph(id='equity-chart'),
            ], className='chart-container'),
            
            html.Div([
                html.H3("Open Positions"),
                html.Div(id='positions-table')
            ]),
            
            html.Div([
                html.H3("Recent Orders"),
                html.Div(id='orders-table')
            ]),
            
            dcc.Interval(
                id='interval-component',
                interval=5*1000,  # Update every 5 seconds
                n_intervals=0
            )
        ])
        
        self.setup_callbacks()
        
    def setup_callbacks(self):
        @self.app.callback(
            [Output('account-summary', 'children'),
             Output('performance-metrics', 'children'),
             Output('equity-chart', 'figure'),
             Output('positions-table', 'children'),
             Output('orders-table', 'children')],
            [Input('interval-component', 'n_intervals')]
        )
        def update_dashboard(n):
            # Account summary
            account_summary = self.get_account_summary_html()
            
            # Performance metrics
            performance_metrics = self.get_performance_metrics_html()
            
            # Equity chart
            equity_chart = self.get_equity_chart()
            
            # Positions table
            positions_table = self.get_positions_table_html()
            
            # Orders table
            orders_table = self.get_orders_table_html()
            
            return account_summary, performance_metrics, equity_chart, positions_table, orders_table
    
    def update_data_thread(self):
        while self.running:
            try:
                # Get account info
                account = self.ls.alpaca.get_account()
                
                # Calculate current values
                equity = float(account.equity)
                prev_equity = self.performance_data['equity'][-1] if self.performance_data['equity'] else float(account.last_equity)
                daily_pnl = equity - prev_equity
                total_pnl = equity - float(account.initial_margin)
                
                # Get position values
                positions = self.ls.alpaca.list_positions()
                long_value = sum([float(p.market_value) for p in positions if p.side == 'long'])
                short_value = sum([float(p.market_value) for p in positions if p.side == 'short'])
                
                # Update data
                self.performance_data['timestamp'].append(datetime.now())
                self.performance_data['equity'].append(equity)
                self.performance_data['long_value'].append(long_value)
                self.performance_data['short_value'].append(short_value)
                self.performance_data['daily_pnl'].append(daily_pnl)
                self.performance_data['total_pnl'].append(total_pnl)
                
                # Update positions data
                self.positions_data = [
                    {
                        'symbol': p.symbol,
                        'qty': p.qty,
                        'side': p.side,
                        'avg_entry': p.avg_entry_price,
                        'current_price': p.current_price,
                        'market_value': p.market_value,
                        'unrealized_pl': p.unrealized_pl,
                        'unrealized_plpc': p.unrealized_plpc
                    } for p in positions
                ]
                
                # Update orders data (last 20)
                orders = self.ls.alpaca.list_orders(limit=20)
                self.orders_data = [
                    {
                        'symbol': o.symbol,
                        'qty': o.qty,
                        'side': o.side,
                        'type': o.type,
                        'status': o.status,
                        'submitted_at': o.submitted_at
                    } for o in orders
                ]
                
                # Save data to file as backup
                self.save_data()
            except Exception as e:
                print(f"Error updating dashboard data: {e}")
            
            time.sleep(10)  # Update every 10 seconds
    
    def save_data(self):
        """Save performance data to file for persistence"""
        try:
            # Convert timestamps to strings for JSON serialization
            serializable_data = {
                'timestamp': [ts.isoformat() for ts in self.performance_data['timestamp']],
                'equity': self.performance_data['equity'],
                'long_value': self.performance_data['long_value'],
                'short_value': self.performance_data['short_value'],
                'daily_pnl': self.performance_data['daily_pnl'],
                'total_pnl': self.performance_data['total_pnl']
            }
            
            # Save performance data
            with open('data/performance_data.json', 'w') as f:
                json.dump(serializable_data, f)
                
            # Save positions data
            with open('data/positions_data.json', 'w') as f:
                json.dump(self.positions_data, f)
                
            # Save orders data
            with open('data/orders_data.json', 'w') as f:
                json.dump(self.orders_data, f)
                
        except Exception as e:
            print(f"Error saving dashboard data: {e}")
    
    def load_data(self):
        """Load performance data from file if available"""
        try:
            # Load performance data
            if os.path.exists('data/performance_data.json'):
                with open('data/performance_data.json', 'r') as f:
                    data = json.load(f)
                    
                    # Convert timestamp strings back to datetime objects
                    self.performance_data['timestamp'] = [datetime.fromisoformat(ts) for ts in data['timestamp']]
                    self.performance_data['equity'] = data['equity']
                    self.performance_data['long_value'] = data['long_value']
                    self.performance_data['short_value'] = data['short_value']
                    self.performance_data['daily_pnl'] = data['daily_pnl']
                    self.performance_data['total_pnl'] = data['total_pnl']
            
            # Load positions data
            if os.path.exists('data/positions_data.json'):
                with open('data/positions_data.json', 'r') as f:
                    self.positions_data = json.load(f)
                    
            # Load orders data
            if os.path.exists('data/orders_data.json'):
                with open('data/orders_data.json', 'r') as f:
                    self.orders_data = json.load(f)
                    
        except Exception as e:
            print(f"Error loading dashboard data: {e}")
    
    def get_account_summary_html(self):
        if not self.performance_data['equity']:
            return html.Div("Loading...")
        
        equity = self.performance_data['equity'][-1]
        daily_pnl = self.performance_data['daily_pnl'][-1]
        total_pnl = self.performance_data['total_pnl'][-1]
        
        return html.Div([
            html.Div([
                html.Span("Equity: "),
                html.Span(f"${equity:,.2f}")
            ]),
            html.Div([
                html.Span("Daily P&L: "),
                html.Span(f"${daily_pnl:,.2f}", style={'color': 'green' if daily_pnl >= 0 else 'red'})
            ]),
            html.Div([
                html.Span("Total P&L: "),
                html.Span(f"${total_pnl:,.2f}", style={'color': 'green' if total_pnl >= 0 else 'red'})
            ])
        ])
    
    def get_performance_metrics_html(self):
        if not self.performance_data['equity']:
            return html.Div("Loading...")
        
        # Calculate metrics
        equity_series = self.performance_data['equity']
        daily_returns = []
        for i in range(1, len(equity_series)):
            daily_returns.append((equity_series[i] - equity_series[i-1]) / equity_series[i-1])
        
        if not daily_returns:
            return html.Div("Insufficient data for metrics")
        
        # Calculate metrics
        total_return = (equity_series[-1] - equity_series[0]) / equity_series[0] if len(equity_series) > 1 else 0
        sharpe = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252) if len(daily_returns) > 1 else 0
        max_drawdown = 0
        peak = equity_series[0]
        
        for equity in equity_series:
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak
            max_drawdown = max(max_drawdown, drawdown)
        
        return html.Div([
            html.Div([
                html.Span("Total Return: "),
                html.Span(f"{total_return:.2%}", style={'color': 'green' if total_return >= 0 else 'red'})
            ]),
            html.Div([
                html.Span("Sharpe Ratio: "),
                html.Span(f"{sharpe:.2f}")
            ]),
            html.Div([
                html.Span("Max Drawdown: "),
                html.Span(f"{max_drawdown:.2%}", style={'color': 'red'})
            ])
        ])
    
    def get_equity_chart(self):
        if not self.performance_data['equity']:
            return {'data': [], 'layout': {'title': 'No data available'}}
        
        # Create traces
        equity_trace = go.Scatter(
            x=self.performance_data['timestamp'],
            y=self.performance_data['equity'],
            mode='lines',
            name='Equity'
        )
        
        long_value_trace = go.Scatter(
            x=self.performance_data['timestamp'],
            y=self.performance_data['long_value'],
            mode='lines',
            name='Long Value'
        )
        
        short_value_trace = go.Scatter(
            x=self.performance_data['timestamp'],
            y=self.performance_data['short_value'],
            mode='lines',
            name='Short Value'
        )
        
        # Create layout
        layout = go.Layout(
            title='Portfolio Value Over Time',
            xaxis={'title': 'Time'},
            yaxis={'title': 'Value ($)'},
            legend={'orientation': 'h'}
        )
        
        return {'data': [equity_trace, long_value_trace, short_value_trace], 'layout': layout}
    
    def get_positions_table_html(self):
        if not self.positions_data:
            return html.Div("No open positions")
        
        # Create header
        header = html.Tr([
            html.Th("Symbol"),
            html.Th("Side"),
            html.Th("Quantity"),
            html.Th("Entry Price"),
            html.Th("Current Price"),
            html.Th("Market Value"),
            html.Th("Unrealized P&L"),
            html.Th("P&L %")
        ])
        
        # Create rows
        rows = []
        for position in self.positions_data:
            pl_color = 'green' if float(position['unrealized_pl']) >= 0 else 'red'
            rows.append(html.Tr([
                html.Td(position['symbol']),
                html.Td(position['side']),
                html.Td(position['qty']),
                html.Td(f"${float(position['avg_entry']):,.2f}"),
                html.Td(f"${float(position['current_price']):,.2f}"),
                html.Td(f"${float(position['market_value']):,.2f}"),
                html.Td(f"${float(position['unrealized_pl']):,.2f}", style={'color': pl_color}),
                html.Td(f"{float(position['unrealized_plpc']):,.2%}", style={'color': pl_color})
            ]))
        
        # Create table
        return html.Table([
            html.Thead(header),
            html.Tbody(rows)
        ])
    
    def get_orders_table_html(self):
        if not self.orders_data:
            return html.Div("No recent orders")
        
        # Create header
        header = html.Tr([
            html.Th("Symbol"),
            html.Th("Side"),
            html.Th("Quantity"),
            html.Th("Type"),
            html.Th("Status"),
            html.Th("Time")
        ])
        
        # Create rows
        rows = []
        for order in self.orders_data:
            rows.append(html.Tr([
                html.Td(order['symbol']),
                html.Td(order['side']),
                html.Td(order['qty']),
                html.Td(order['type']),
                html.Td(order['status']),
                html.Td(str(order['submitted_at']))
            ]))
        
        # Create table
        return html.Table([
            html.Thead(header),
            html.Tbody(rows)
        ])
    
    def run(self, debug=False, port=8050):
        self.app.run_server(debug=debug, port=port)


class LongShort:
    def __init__(self):
        self.alpaca = tradeapi.REST(API_KEY, API_SECRET, APCA_API_BASE_URL, 'v2')
        stockUniverse = ['DOMO', 'TLRY', 'SQ', 'MRO', 'AAPL', 'GM', 'SNAP', 'SHOP',
                         'BA', 'AMZN', 'SUI', 'SUN', 'TSLA', 'CGC', 'NIO', 'CAT', 
                         'MSFT', 'PANW', 'OKTA', 'TM', 'GS', 'BAC', 'MS', 'TWLO', 
                         'QCOM', 'NVDA', 'VST', 'MSTR', 'CVNA', 'CAVA', 'SN', 
                         'INSM', 'FTAI', 'WING', 'MMYT', 'SFM', 'FYBR', 'ASTS', 
                         'BRFS', 'TLN', 'ANF', 'ERJ', 'ZETA', 'LUMN', 'BMA', 'PI', 
                         'OSCR', 'CLBT', 'DYN', 'EAT', 'BBAR', 'AMRX', 'CORZ', 'CDE']
        self.allStocks = [[stock, 0] for stock in stockUniverse]
        self.long = []
        self.short = []
        self.qShort = None
        self.qLong = None
        self.adjustedQLong = None
        self.adjustedQShort = None
        self.blacklist = set()
        self.longAmount = 0
        self.shortAmount = 0
        self.timeToClose = None
        self.orders_log = []
        
        # Add risk management parameters
        self.max_drawdown_pct = 0.05  # 5% maximum drawdown
        self.stop_loss_pct = 0.03     # 3% stop loss
        self.take_profit_pct = 0.05   # 5% take profit
        self.max_position_pct = 0.10  # No position can be more than 10% of portfolio
        
        # Performance tracking
        self.starting_equity = None
        self.peak_equity = 0
        self.current_drawdown = 0
        
        # Initialize GPU-based ranking if available
        try:
            # Try to import GPU support - falls back to CPU if not available
            import tensorflow as tf
            print(f"TensorFlow version: {tf.__version__}")
            print(f"GPU available: {len(tf.config.list_physical_devices('GPU')) > 0}")
            self.gpu_available = len(tf.config.list_physical_devices('GPU')) > 0
        except:
            print("TensorFlow not available, defaulting to CPU-based ranking")
            self.gpu_available = False

    def run(self):
        # Initialize dashboard in a separate thread
        dashboard = TradingDashboard(self)
        dash_thread = threading.Thread(target=dashboard.run, kwargs={'debug': False, 'port': 8050})
        dash_thread.daemon = True
        dash_thread.start()
        
        self.log_portfolio("start")
        # Cancel any existing orders
        orders = self.alpaca.list_orders(status="open")
        for order in orders:
            self.alpaca.cancel_order(order.id)
            
        print("Waiting for market to open...")
        tAMO = threading.Thread(target=self.awaitMarketOpen)
        tAMO.start()
        tAMO.join()
        print("Market opened.")
        
        # Initialize equity tracking
        account = self.alpaca.get_account()
        self.starting_equity = float(account.equity)
        self.peak_equity = self.starting_equity
        
        while True:
            # Check market hours
            clock = self.alpaca.get_clock()
            closingTime = clock.next_close.replace(tzinfo=datetime.timezone.utc).timestamp()
            currTime = clock.timestamp.replace(tzinfo=datetime.timezone.utc).timestamp()
            self.timeToClose = closingTime - currTime
            
            # If market is about to close (30 minutes instead of 15)
            if self.timeToClose < (60 * 30):
                print("Market closing soon. Closing positions.")
                # Use the improved parallel position closing method
                self.close_positions()
                print(f"Sleeping until market close ({int(self.timeToClose/60)} minutes).")
                time.sleep(self.timeToClose)
                self.log_portfolio("end")
                self.send_email()
            else:
                # Check risk limits
                if not self.check_risk_limits():
                    print("Risk limits exceeded. Waiting for 1 hour before resuming.")
                    time.sleep(3600)  # Wait an hour
                    continue
                    
                # Check stop loss/take profit
                self.check_stop_loss_take_profit()
                
                # Check position size limits
                self.check_position_limits()
                
                # Regular rebalancing (run in background thread)
                tRebalance = threading.Thread(target=self.rebalance)
                tRebalance.start()
                
                # Wait for rebalance to complete
                tRebalance.join()
                
                # Sleep between cycles - adaptive based on market volatility
                time.sleep(30)  # Reduced from 60 to be more responsive

    def close_positions(self, timeout_seconds=60):
        """Close all positions with retry logic and parallel execution"""
        positions = self.alpaca.list_positions()
        if not positions:
            return
            
        # Use ThreadPoolExecutor for truly parallel order submission
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for position in positions:
                order_side = 'sell' if position.side == 'long' else 'buy'
                qty = abs(int(float(position.qty)))
                futures.append(
                    executor.submit(self.submit_order_with_retry, 
                                    qty, position.symbol, order_side, max_retries=3)
                )
            
            # Wait for all orders with timeout
            done, not_done = concurrent.futures.wait(
                futures, timeout=timeout_seconds, 
                return_when=concurrent.futures.ALL_COMPLETED
            )
            
            if not_done:
                print(f"Warning: {len(not_done)} orders didn't complete within {timeout_seconds}s")
            
    def submit_order_with_retry(self, qty, stock, side, max_retries=3):
        """Submit order with retry logic"""
        if qty <= 0:
            return False
            
        for attempt in range(max_retries):
            try:
                self.alpaca.submit_order(stock, qty, side, "market", "day")
                print(f"Market order of | {qty} {stock} {side} | completed.")
                self.orders_log.append([stock, qty, side, "completed", datetime.now()])
                return True
            except Exception as e:
                print(f"Order attempt {attempt+1}/{max_retries} failed: {qty} {stock} {side}: {e}")
                if attempt == max_retries - 1:
                    self.orders_log.append([stock, qty, side, f"failed after {max_retries} attempts: {e}", 
                                           datetime.now()])
                    return False
                time.sleep(1)  # Brief pause before retry

    def check_risk_limits(self):
        """Check if risk limits are breached and take action if needed"""
        account = self.alpaca.get_account()
        equity = float(account.equity)
        
        # Initialize on first run
        if self.starting_equity is None:
            self.starting_equity = equity
            self.peak_equity = equity
        
        # Update peak equity
        if equity > self.peak_equity:
            self.peak_equity = equity
        
        # Calculate current drawdown
        self.current_drawdown = (self.peak_equity - equity) / self.peak_equity
        
        # Check for maximum drawdown breach
        if self.current_drawdown > self.max_drawdown_pct:
            print(f"WARNING: Maximum drawdown breached: {self.current_drawdown:.2%}")
            print("Closing all positions to limit losses...")
            self.close_positions()
            return False
        
        return True
    
    def check_position_limits(self):
        """Check individual position limits and adjust if needed"""
        positions = self.alpaca.list_positions()
        account = self.alpaca.get_account()
        equity = float(account.equity)
        
        for position in positions:
            position_value = float(position.market_value)
            position_pct = position_value / equity
            
            # Check if position exceeds maximum allowed percentage
            if position_pct > self.max_position_pct:
                print(f"Position {position.symbol} exceeds max size ({position_pct:.2%})")
                
                # Calculate how much to reduce
                excess_pct = position_pct - self.max_position_pct
                excess_value = excess_pct * equity
                excess_shares = int(excess_value / float(position.current_price))
                
                if excess_shares > 0:
                    print(f"Reducing position by {excess_shares} shares")
                    side = 'sell' if position.side == 'long' else 'buy'
                    self.submit_order_with_retry(excess_shares, position.symbol, side)
    
    def check_stop_loss_take_profit(self):
        """Check if any positions have hit stop loss or take profit levels"""
        positions = self.alpaca.list_positions()
        
        for position in positions:
            # Calculate P&L percentage
            entry_price = float(position.avg_entry_price)
            current_price = float(position.current_price)
            
            if position.side == 'long':
                pnl_pct = (current_price - entry_price) / entry_price
                # Stop loss check
                if pnl_pct < -self.stop_loss_pct:
                    print(f"Stop loss triggered for {position.symbol}: {pnl_pct:.2%}")
                    self.submit_order_with_retry(abs(int(float(position.qty))), position.symbol, 'sell')
                # Take profit check
                elif pnl_pct > self.take_profit_pct:
                    print(f"Take profit triggered for {position.symbol}: {pnl_pct:.2%}")
                    self.submit_order_with_retry(abs(int(float(position.qty))), position.symbol, 'sell')
            else:  # short position
                pnl_pct = (entry_price - current_price) / entry_price
                # Stop loss check
                if pnl_pct < -self.stop_loss_pct:
                    print(f"Stop loss triggered for {position.symbol}: {pnl_pct:.2%}")
                    self.submit_order_with_retry(abs(int(float(position.qty))), position.symbol, 'buy')
                # Take profit check
                elif pnl_pct > self.take_profit_pct:
                    print(f"Take profit triggered for {position.symbol}: {pnl_pct:.2%}")
                    self.submit_order_with_retry(abs(int(float(position.qty))), position.symbol, 'buy')

    def awaitMarketOpen(self):
        isOpen = self.alpaca.get_clock().is_open
        while not isOpen:
            clock = self.alpaca.get_clock()
            openingTime = clock.next_open.replace(tzinfo=datetime.timezone.utc).timestamp()
            currTime = clock.timestamp.replace(tzinfo=datetime.timezone.utc).timestamp()
            timeToOpen = int((openingTime - currTime) / 60)
            print(f"{timeToOpen} minutes til market open.")
            time.sleep(60)
            isOpen = self.alpaca.get_clock().is_open

    def rebalance(self):
        tRerank = threading.Thread(target=self.rerank)
        tRerank.start()
        tRerank.join()
        
        # Cancel any open orders
        orders = self.alpaca.list_orders(status="open")
        for order in orders:
            self.alpaca.cancel_order(order.id)
            
        print(f"We are taking a long position in: {self.long}")
        print(f"We are taking a short position in: {self.short}")
        
        executed = [[], []]
        positions = self.alpaca.list_positions()
        self.blacklist.clear()
        
        # Process existing positions
        for position in positions:
            if self.long.count(position.symbol) == 0:
                if self.short.count(position.symbol) == 0:
                    # Close positions not in our target lists
                    side = "sell" if position.side == "long" else "buy"
                    qty = abs(int(float(position.qty)))
                    self.submit_order_with_retry(qty, position.symbol, side)
                else:
                    # Handle positions in our short list
                    if position.side == "long":
                        # Need to flip from long to short
                        self.submit_order_with_retry(int(float(position.qty)), position.symbol, "sell")
                    else:
                        # Already short, adjust quantity if needed
                        if abs(int(float(position.qty))) == self.qShort:
                            pass  # Quantity is correct
                        else:
                            diff = abs(int(float(position.qty))) - self.qShort
                            side = "buy" if diff > 0 else "sell"
                            self.submit_order_with_retry(abs(diff), position.symbol, side)
                        executed[1].append(position.symbol)
                        self.blacklist.add(position.symbol)
            else:
                # Handle positions in our long list
                if position.side == "short":
                    # Need to flip from short to long
                    self.submit_order_with_retry(abs(int(float(position.qty))), position.symbol, "buy")
                else:
                    # Already long, adjust quantity if needed
                    if int(float(position.qty)) == self.qLong:
                        pass  # Quantity is correct
                    else:
                        diff = abs(int(float(position.qty))) - self.qLong
                        side = "sell" if diff > 0 else "buy"
                        self.submit_order_with_retry(abs(diff), position.symbol, side)
                    executed[0].append(position.symbol)
                    self.blacklist.add(position.symbol)
        
        # Process batch orders for new positions in parallel
        long_futures = []
        short_futures = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            # Submit orders for long positions not already executed
            for stock in self.long:
                if stock not in executed[0] and stock not in self.blacklist:
                    long_futures.append(
                        executor.submit(self.submit_order_with_retry, 
                                        self.qLong, stock, "buy")
                    )
            
            # Submit orders for short positions not already executed
            for stock in self.short:
                if stock not in executed[1] and stock not in self.blacklist:
                    short_futures.append(
                        executor.submit(self.submit_order_with_retry, 
                                        self.qShort, stock, "sell")
                    )
            
            # Wait for completion with timeout
            done_long, not_done_long = concurrent.futures.wait(
                long_futures, timeout=60, 
                return_when=concurrent.futures.ALL_COMPLETED
            )
            
            done_short, not_done_short = concurrent.futures.wait(
                short_futures, timeout=60, 
                return_when=concurrent.futures.ALL_COMPLETED
            )
        
        if not_done_long:
            print(f"Warning: {len(not_done_long)} long orders didn't complete within timeout")
        
        if not_done_short:
            print(f"Warning: {len(not_done_short)} short orders didn't complete within timeout")

    def rerank(self):
        if self.gpu_available:
            try:
                # Attempt to use GPU-accelerated ranking if available
                ranked_stocks = self.gpu_rank_stocks()
                if ranked_stocks:
                    # Update allStocks with the ranking results
                    ranked_dict = {symbol: score for symbol, score in ranked_stocks}
                    for i, stock_data in enumerate(self.allStocks):
                        stock_data[1] = ranked_dict.get(stock_data[0], 0)
                    self.allStocks.sort(key=lambda x: x[1])
                    return
            except Exception as e:
                print(f"GPU ranking failed: {e}, falling back to CPU")
                
        # Fallback to traditional method
        tGetPC = threading.Thread(target=self.getPercentChanges)
        tGetPC.start()
        tGetPC.join()
        self.allStocks.sort(key=lambda x: x[1])

    def gpu_rank_stocks(self):
        """Use GPU to calculate momentum scores if available"""
        try:
            import tensorflow as tf
            
            # Get stock prices using yfinance
            stock_symbols = [stock[0] for stock in self.allStocks]
            price_data = {}
            
            # Get historical data for all stocks
            for symbol in stock_symbols:
                try:
                    data = yf.download(symbol, period='10d', interval='1d', progress=False)
                    if not data.empty:
                        price_data[symbol] = data['Close'].values
                except Exception as e:
                    print(f"Error downloading data for {symbol}: {e}")
            
            # Prepare data for batch processing
            valid_symbols = []
            momentum_data = []
            
            for symbol, prices in price_data.items():
                if len(prices) >= 2:  # Need at least 2 data points
                    valid_symbols.append(symbol)
                    # Simple momentum formula: Calculate recent returns
                    returns = (prices[-1] / prices[0]) - 1
                    momentum_data.append(returns)
            
            # Convert to tensors for efficient computation
            momentum_tensor = tf.convert_to_tensor(momentum_data, dtype=tf.float32)
            
            # Use GPU for batch processing if available
            with tf.device('/GPU:0' if self.gpu_available else '/CPU:0'):
                # Sort by momentum
                indices = tf.argsort(momentum_tensor)
                ranked_symbols = [(valid_symbols[i.numpy()], momentum_data[i.numpy()]) 
                                for i in indices]
                
                return ranked_symbols
                
        except Exception as e:
            print(f"GPU ranking error: {e}")
            return None

    def getTotalPrice(self, stocks, resp):
        totalPrice = 0
        for stock in stocks:
            try:
                stock_data = yf.Ticker(stock)
                bars = stock_data.history(period='1d', interval='1m')
                if not bars.empty:
                    totalPrice += bars['Close'].iloc[-1]
                else:
                    print(f"No price data found for {stock}, skipping...")
            except Exception as e:
                print(f"Failed to download data for {stock}: {e}")
        resp.append(totalPrice)

    def submitOrder(self, qty, stock, side, resp):
        """Legacy submitOrder method - retained for compatibility"""
        if qty is None:
            print("Quantity is None, cannot submit order.")
            resp.append(False)
            return
        if qty > 0:
            try:
                self.alpaca.submit_order(stock, qty, side, "market", "day")
                print(f"Market order of | {qty} {stock} {side} | completed.")
                self.orders_log.append([stock, qty, side, "completed", datetime.now()])
                resp.append(True)
            except Exception as e:
                print(f"Order of | {qty} {stock} {side} | did not go through: {e}")
                self.orders_log.append([stock, qty, side, f"failed: {e}", datetime.now()])
                resp.append(False)
        else:
            print(f"Quantity is 0, order of | {qty} {stock} {side} | not completed.")
            self.orders_log.append([stock, qty, side, "not completed: qty is 0", datetime.now()])
            resp.append(True)

    def sendBatchOrder(self, qty, stocks, side, resp):
        """Legacy batch order method - using improved parallel execution"""
        executed = []
        incomplete = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {}
            # Submit all orders
            for stock in stocks:
                if self.blacklist.isdisjoint({stock}):
                    futures[stock] = executor.submit(
                        self.submit_order_with_retry, qty, stock, side)
            
            # Collect results
            for stock, future in futures.items():
                try:
                    result = future.result(timeout=30)
                    if result:
                        executed.append(stock)
                    else:
                        incomplete.append(stock)
                except concurrent.futures.TimeoutError:
                    print(f"Order for {stock} timed out")
                    incomplete.append(stock)
        
        resp.append([executed, incomplete])

    def log_portfolio(self, time_of_day):
        positions = self.alpaca.list_positions()
        with open(f'portfolio_{time_of_day}.csv', mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["Symbol", "Qty", "Side", "Avg Entry", "Current Price", "Market Value", "Unrealized P&L"])
            for position in positions:
                writer.writerow([
                    position.symbol, 
                    position.qty, 
                    position.side,
                    position.avg_entry_price,
                    position.current_price,
                    position.market_value,
                    position.unrealized_pl
                ])

    def send_email(self):
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = EMAIL_RECEIVER
        msg['Subject'] = "Daily Trading Report - Long-Short Strategy"
        
        # Calculate daily performance
        account = self.alpaca.get_account()
        equity = float(account.equity)
        daily_change = (equity - float(account.last_equity)) / float(account.last_equity)
        
        # Create email body with performance summary
        body = f"""
        <html>
        <body>
            <h2>Long-Short Trading Strategy - Daily Report</h2>
            <p>Trading completed for {datetime.now().strftime('%Y-%m-%d')}</p>
            
            <h3>Performance Summary:</h3>
            <ul>
                <li>Starting Equity: ${float(account.last_equity):,.2f}</li>
                <li>Ending Equity: ${equity:,.2f}</li>
                <li>Daily P&L: ${equity - float(account.last_equity):,.2f} ({daily_change:.2%})</li>
                <li>Buying Power: ${float(account.buying_power):,.2f}</li>
            </ul>
            
            <p>Detailed trade log and current positions attached.</p>
        </body>
        </html>
        """
        msg.attach(MIMEText(body, 'html'))
        
        # Attach orders log
        filename = "orders.csv"
        with open(filename, "w", newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["Stock", "Quantity", "Side", "Status", "Timestamp"])
            writer.writerows(self.orders_log)
        attachment = open(filename, "rb")
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename= {filename}")
        msg.attach(part)
        
        # Attach current positions
        positions_file = "current_positions.csv"
        with open(positions_file, "w", newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["Symbol", "Side", "Qty", "Avg Entry", "Current Price", "P&L"])
            positions = self.alpaca.list_positions()
            for p in positions:
                writer.writerow([
                    p.symbol, p.side, p.qty, p.avg_entry_price, 
                    p.current_price, p.unrealized_pl
                ])
        attachment = open(positions_file, "rb")
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename= {positions_file}")
        msg.attach(part)
        
        # Send email
        try:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            text = msg.as_string()
            server.sendmail(EMAIL_USER, EMAIL_RECEIVER, text)
            server.quit()
            print("Trading report email sent successfully")
        except Exception as e:
            print(f"Failed to send email: {e}")

    def getPercentChanges(self):
        length = 10
        for i, stock in enumerate(self.allStocks):
            try:
                data = yf.download(stock[0], period='1d', interval='1m', progress=False)
                if len(data) >= length:
                    open_price = data.iloc[0]['Open']
                    close_price = data.iloc[-1]['Close']
                    self.allStocks[i][1] = (close_price - open_price) / open_price
                else:
                    print(f"Not enough data for {stock[0]}, setting percent change to 0")
                    self.allStocks[i][1] = 0
            except Exception as e:
                print(f"Error getting percent change for {stock[0]}: {e}")
                self.allStocks[i][1] = 0

    def rank(self):
        """Legacy rank method - redirects to the improved version"""
        return self.rerank()


# Run the LongShort class
if __name__ == "__main__":
    ls = LongShort()
    ls.run()