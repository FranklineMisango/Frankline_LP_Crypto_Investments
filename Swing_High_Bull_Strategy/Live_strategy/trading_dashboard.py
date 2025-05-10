import dash
from dash import dcc, html, Input, Output, callback_context
import plotly.graph_objs as go
from dash.exceptions import PreventUpdate
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import threading
import ccxt.async_support as ccxt_async
from collections import deque
import plotly.express as px

# Shared data store for communication between trading engine and dashboard
class SharedDataStore:
    def __init__(self):
        self.portfolio_history = []
        self.positions = {}  # Symbol -> {entry_price, current_price, qty, pnl, pnl_percent}
        self.trade_history = []  # List of executed trades
        self.alerts = []  # System alerts/notifications
        self.active_symbols = []  # Currently tracked symbols
        self.market_data = {}  # Symbol -> {price, volume, change_24h}
        self.lock = threading.Lock()  # Thread safety

data_store = SharedDataStore()

# Initialize the Dash app
app = dash.Dash(__name__, 
                title='Crypto Trading Dashboard',
                meta_tags=[{'name': 'viewport', 'content': 'width=device-width, initial-scale=1'}])

# Create the app layout
app.layout = html.Div([
    html.Div([
        html.H1("Crypto Trading Dashboard", style={'textAlign': 'center'}),
        
        html.Div([
            dcc.Tabs([
                dcc.Tab(label='Portfolio Overview', children=[
                    html.Div([
                        html.Div([
                            html.H3("Portfolio Performance"),
                            dcc.Graph(id='portfolio-chart'),
                        ], className='chart-container'),
                        
                        html.Div([
                            html.H3("Positions"),
                            html.Div(id='positions-table')
                        ], className='table-container'),
                    ], style={'display': 'flex', 'flexWrap': 'wrap'})
                ]),
                
                dcc.Tab(label='Market Data', children=[
                    html.Div([
                        html.H3("Market Overview"),
                        dcc.Dropdown(
                            id='timeframe-selector',
                            options=[
                                {'label': '1 Hour', 'value': '1h'},
                                {'label': '4 Hours', 'value': '4h'},
                                {'label': '1 Day', 'value': '1d'}
                            ],
                            value='1h'
                        ),
                        dcc.Graph(id='market-chart'),
                    ])
                ]),
                
                dcc.Tab(label='Trade History', children=[
                    html.Div([
                        html.H3("Recent Trades"),
                        html.Div(id='trade-history-table')
                    ])
                ]),
                
                dcc.Tab(label='System Control', children=[
                    html.Div([
                        html.H3("Trading Controls"),
                        html.Button('Start Trading', id='start-button', n_clicks=0),
                        html.Button('Stop Trading', id='stop-button', n_clicks=0, style={'marginLeft': '10px'}),
                        html.Button('Emergency Exit', id='emergency-button', n_clicks=0, 
                                    style={'marginLeft': '10px', 'backgroundColor': 'red', 'color': 'white'}),
                        html.Div(id='control-status'),
                        
                        html.H3("System Alerts", style={'marginTop': '20px'}),
                        html.Div(id='alerts-log', style={'height': '200px', 'overflowY': 'auto', 
                                                        'border': '1px solid #ddd', 'padding': '10px'})
                    ])
                ]),
            ]),
        ]),
    ]),
    
    # Hidden div for storing data
    html.Div(id='hidden-data-store', style={'display': 'none'}),
    
    # Interval component for periodic updates
    dcc.Interval(
        id='interval-component',
        interval=5000,  # Update every 5 seconds
        n_intervals=0
    ),
])

# Callback to update portfolio chart
@app.callback(
    Output('portfolio-chart', 'figure'),
    Input('interval-component', 'n_intervals')
)
def update_portfolio_chart(n):
    with data_store.lock:
        if not data_store.portfolio_history:
            # Return empty chart if no data
            return {
                'data': [],
                'layout': go.Layout(title="Portfolio Value Over Time")
            }
        
        df = pd.DataFrame(data_store.portfolio_history)
        
        fig = px.line(df, x='timestamp', y='value', title="Portfolio Value")
        fig.update_layout(
            xaxis_title="Time",
            yaxis_title="Portfolio Value (USDT)",
            template="plotly_dark",
            height=400
        )
        return fig

# Callback to update positions table
@app.callback(
    Output('positions-table', 'children'),
    Input('interval-component', 'n_intervals')
)
def update_positions_table(n):
    with data_store.lock:
        if not data_store.positions:
            return html.P("No open positions")
        
        positions = data_store.positions
        table_header = [
            html.Thead(html.Tr([
                html.Th("Symbol"),
                html.Th("Entry Price"),
                html.Th("Current Price"),
                html.Th("Quantity"),
                html.Th("PnL"),
                html.Th("PnL %"),
                html.Th("Action")
            ]))
        ]
        
        rows = []
        for symbol, position in positions.items():
            pnl_color = 'green' if position.get('pnl', 0) >= 0 else 'red'
            rows.append(html.Tr([
                html.Td(symbol),
                html.Td(f"{position.get('entry_price', 0):.4f}"),
                html.Td(f"{position.get('current_price', 0):.4f}"),
                html.Td(f"{position.get('qty', 0):.6f}"),
                html.Td(f"{position.get('pnl', 0):.2f}", style={'color': pnl_color}),
                html.Td(f"{position.get('pnl_percent', 0):.2f}%", style={'color': pnl_color}),
                html.Td(html.Button("Close", id={'type': 'close-button', 'symbol': symbol}, 
                                    style={'backgroundColor': '#ff5050'}))
            ]))
        
        table_body = [html.Tbody(rows)]
        
        return html.Table(table_header + table_body, style={'width': '100%', 'textAlign': 'center'})

# Add more callbacks for other dashboard elements

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8050)