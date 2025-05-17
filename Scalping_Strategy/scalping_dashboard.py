import dash
from dash import dcc, html, Input, Output
import plotly.graph_objs as go
import pandas as pd
import threading
import time

# This assumes trades.csv and portfolio_values.csv are updated by your backtest/live code
# You may need to adapt file paths or data sources as needed

def load_trades():
    try:
        return pd.read_csv('Scalping_Strategy/trades.csv')
    except Exception:
        return pd.DataFrame()

def load_portfolio():
    try:
        df = pd.read_csv('Scalping_Strategy/portfolio_values.csv')
        return df
    except Exception:
        return pd.DataFrame()

app = dash.Dash(__name__)

app.layout = html.Div([
    html.H1('Scalping Strategy Live Dashboard'),
    dcc.Interval(id='interval', interval=5*1000, n_intervals=0),
    html.Div(id='summary-metrics'),
    dcc.Graph(id='portfolio-graph'),
    dcc.Graph(id='trades-graph'),
])

@app.callback(
    [Output('portfolio-graph', 'figure'),
     Output('trades-graph', 'figure'),
     Output('summary-metrics', 'children')],
    [Input('interval', 'n_intervals')]
)
def update_dashboard(n):
    trades = load_trades()
    portfolio = load_portfolio()
    # Portfolio value plot
    if not portfolio.empty:
        fig_portfolio = go.Figure([
            go.Scatter(x=portfolio['time'], y=portfolio['value'], mode='lines', name='Portfolio Value')
        ])
    else:
        fig_portfolio = go.Figure()
    # Trades plot
    if not trades.empty:
        buy_trades = trades[trades['side'] == 'buy']
        sell_trades = trades[trades['side'] == 'sell']
        fig_trades = go.Figure()
        fig_trades.add_trace(go.Scatter(x=buy_trades['time'], y=buy_trades['price'], mode='markers', marker=dict(color='green'), name='Buy'))
        fig_trades.add_trace(go.Scatter(x=sell_trades['time'], y=sell_trades['price'], mode='markers', marker=dict(color='red'), name='Sell'))
    else:
        fig_trades = go.Figure()
    # Summary metrics
    if not trades.empty:
        total_trades = len(trades[trades['side'] == 'sell'])
        win_trades = trades[(trades['side'] == 'sell') & (trades['price'] > trades['buy_price'] * (1 + 0.002))]
        win_ratio = len(win_trades) / max(1, total_trades)
        summary = html.Div([
            html.P(f"Total Trades: {total_trades}"),
            html.P(f"Win Ratio: {win_ratio:.2%}"),
            html.P(f"Last Portfolio Value: {portfolio['value'].iloc[-1] if not portfolio.empty else 'N/A'}")
        ])
    else:
        summary = html.Div([html.P("No trades yet.")])
    return fig_portfolio, fig_trades, summary

if __name__ == '__main__':
    app.run_server(debug=True)
