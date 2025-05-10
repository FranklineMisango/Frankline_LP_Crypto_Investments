import ccxt.async_support as ccxt_async  
import asyncio
import pandas as pd
import numpy as np
import logging
import time
from datetime import datetime, timedelta
import threading
import json
import os
import sys
from collections import deque
from binance_websocket import BinanceWebsocketClient
from trading_dashboard import data_store, app
import threading

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("trading.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('trading_strategy')

class SwingHighRealtime:
    def __init__(self, api_key=None, api_secret=None, test_mode=True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.test_mode = test_mode
        
        # Initialize exchange
        if api_key and api_secret:
            self.exchange = ccxt_async.binance({
                'apiKey': api_key,
                'secret': api_secret,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'spot'
                }
            })
        else:
            self.exchange = ccxt_async.binance({'enableRateLimit': True})

        # Initialize websocket client
        self.ws_client = BinanceWebsocketClient(api_key, api_secret)
        
        # Strategy parameters
        self.portfolio_value = 1000  # Initial portfolio value in USDT
        self.max_positions = 5       # Maximum number of simultaneous positions
        self.position_size_pct = 0.2  # 20% of portfolio per position
        self.stop_loss_pct = 0.05     # 5% stop loss
        self.take_profit_pct = 0.1    # 10% take profit
        self.trailing_stop_pct = 0.02  # 2% trailing stop
        
        # Data structures
        self.symbols = []             # Symbols we're tracking
        self.positions = {}           # Current positions
        self.price_data = {}          # Price data for each symbol
        self.highest_prices = {}      # Highest prices seen for trailing stops
        self.orders = {}              # Active orders
        
        # Runtime state
        self.running = False
        self.last_update = {}
        
        # Data store for dashboard communication
        self.data_store = data_store
        
    async def initialize(self):
        """Initialize the strategy, load markets, etc."""
        logger.info("Initializing trading strategy...")
        
        try:
            # Load exchange markets
            await self.exchange.load_markets()
            logger.info(f"Loaded {len(self.exchange.markets)} markets")
            
            # Update initial portfolio value if we're using real API
            if self.api_key and self.api_secret:
                balance = await self.exchange.fetch_balance()
                self.portfolio_value = float(balance['total']['USDT'])
                logger.info(f"Initial portfolio value: {self.portfolio_value} USDT")
            
            # Initialize portfolio history with current value
            with self.data_store.lock:
                self.data_store.portfolio_history.append({
                    'timestamp': datetime.now(),
                    'value': self.portfolio_value
                })
            
            return True
        
        except Exception as e:
            logger.error(f"Initialization error: {e}")
            return False

    async def find_top_gainers(self, count=20):
        """Find top gaining cryptocurrencies."""
        try:
            logger.info("Finding top gainers...")
            tickers = await self.exchange.fetch_tickers()
            
            # Filter for USDT pairs and valid percentage data
            filtered_tickers = [
                ticker for ticker in tickers.values() 
                if ticker['symbol'].endswith('/USDT') and ticker['percentage'] is not None
            ]
            
            # Sort by percentage change (descending)
            sorted_tickers = sorted(filtered_tickers, key=lambda x: x['percentage'], reverse=True)
            
            # Select top N gainers
            top_gainers = sorted_tickers[:count]
            
            logger.info(f"Found top {len(top_gainers)} gainers")
            self.symbols = [ticker['symbol'] for ticker in top_gainers]
            
            # Update data store with market data
            with self.data_store.lock:
                self.data_store.active_symbols = self.symbols.copy()
                for ticker in top_gainers:
                    self.data_store.market_data[ticker['symbol']] = {
                        'price': ticker['last'],
                        'volume': ticker['quoteVolume'],
                        'change_24h': ticker['percentage']
                    }
            
            return self.symbols
        
        except Exception as e:
            logger.error(f"Error finding top gainers: {e}")
            return []

    async def setup_websockets(self):
        """Set up websocket connections for all tracked symbols."""
        try:
            for symbol in self.symbols:
                # Create clean websocket symbol name (lowercase, no '/')
                ws_symbol = symbol.replace('/', '').lower()
                
                # Initialize price data structure
                self.price_data[symbol] = {
                    'current': None,
                    'high': None,
                    'low': None,
                    'open': None,
                    'close': None,
                    'volume': None,
                    'timestamp': None,
                    'history': deque(maxlen=100)  # Keep last 100 prices
                }
                
                # Subscribe to ticker updates
                await self.ws_client.subscribe_ticker(ws_symbol, 
                                                     lambda msg, s=symbol: self.handle_ticker_update(s, msg))
                
                # Subscribe to trade updates for more granular data
                await self.ws_client.subscribe_trade(ws_symbol,
                                                    lambda msg, s=symbol: self.handle_trade_update(s, msg))
                
                logger.info(f"Set up websockets for {symbol}")
            
            logger.info(f"Successfully set up websockets for {len(self.symbols)} symbols")
            return True
        
        except Exception as e:
            logger.error(f"Error setting up websockets: {e}")
            return False

    async def handle_ticker_update(self, symbol, msg):
        """Handle ticker updates from websocket."""
        try:
            # Update price data
            self.price_data[symbol]['current'] = float(msg['c'])
            self.price_data[symbol]['high'] = float(msg['h'])
            self.price_data[symbol]['low'] = float(msg['l'])
            self.price_data[symbol]['open'] = float(msg['o'])
            self.price_data[symbol]['volume'] = float(msg['v'])
            self.price_data[symbol]['timestamp'] = datetime.now()
            
            # Add to price history
            self.price_data[symbol]['history'].append({
                'price': float(msg['c']),
                'timestamp': datetime.now()
            })
            
            # Update market data in data store
            with self.data_store.lock:
                self.data_store.market_data[symbol] = {
                    'price': float(msg['c']),
                    'volume': float(msg['v']),
                    'change_24h': float(msg['p'])
                }
            
            # Check for position updates if we have this symbol
            if symbol in self.positions:
                await self.update_position_status(symbol)
            
            # Log updates periodically (not every tick)
            if symbol not in self.last_update or (datetime.now() - self.last_update[symbol]).seconds > 60:
                logger.debug(f"Price update for {symbol}: {float(msg['c'])}")
                self.last_update[symbol] = datetime.now()
        
        except Exception as e:
            logger.error(f"Error handling ticker update for {symbol}: {e}")

    async def handle_trade_update(self, symbol, msg):
        """Handle individual trade updates."""
        # Process individual trades if needed
        pass

    async def update_position_status(self, symbol):
        """Update position status including PnL calculations."""
        try:
            if symbol not in self.positions:
                return
            
            position = self.positions[symbol]
            current_price = self.price_data[symbol]['current']
            
            # Skip if we don't have current price
            if not current_price:
                return
            
            # Update highest price for trailing stop
            if symbol not in self.highest_prices:
                self.highest_prices[symbol] = current_price
            elif current_price > self.highest_prices[symbol]:
                self.highest_prices[symbol] = current_price
            
            # Calculate PnL
            entry_price = position['entry_price']
            quantity = position['quantity']
            
            pnl = (current_price - entry_price) * quantity
            pnl_percent = (current_price - entry_price) / entry_price * 100
            
            # Update position data
            position['current_price'] = current_price
            position['pnl'] = pnl
            position['pnl_percent'] = pnl_percent
            
            # Update data store
            with self.data_store.lock:
                self.data_store.positions[symbol] = {
                    'entry_price': entry_price,
                    'current_price': current_price,
                    'qty': quantity,
                    'pnl': pnl,
                    'pnl_percent': pnl_percent
                }
            
            # Check exit conditions
            await self.check_exit_conditions(symbol)
        
        except Exception as e:
            logger.error(f"Error updating position status for {symbol}: {e}")

    async def check_exit_conditions(self, symbol):
        """Check if we should exit a position based on strategy rules."""
        try:
            if symbol not in self.positions:
                return
            
            position = self.positions[symbol]
            current_price = self.price_data[symbol]['current']
            entry_price = position['entry_price']
            highest_price = self.highest_prices[symbol]
            
            # Take profit condition
            if current_price >= entry_price * (1 + self.take_profit_pct):
                await self.execute_sell(symbol, current_price, "Take profit triggered")
                return
            
            # Stop loss condition
            if current_price <= entry_price * (1 - self.stop_loss_pct):
                await self.execute_sell(symbol, current_price, "Stop loss triggered")
                return
            
            # Trailing stop condition (only if in profit)
            if current_price > entry_price and current_price <= highest_price * (1 - self.trailing_stop_pct):
                await self.execute_sell(symbol, current_price, "Trailing stop triggered")
                return
            
        except Exception as e:
            logger.error(f"Error checking exit conditions for {symbol}: {e}")

    async def execute_buy(self, symbol, price):
        """Execute a buy order for a symbol."""
        try:
            # Check if we're already in this position
            if symbol in self.positions:
                logger.warning(f"Already in position for {symbol}")
                return False
            
            # Calculate position size
            position_value = self.portfolio_value * self.position_size_pct
            quantity = position_value / price
            
            # Execute order
            if self.test_mode:
                logger.info(f"TEST MODE: Would buy {quantity} {symbol} at {price}")
                order_id = f"test-{int(time.time())}"
            else:
                # Real order execution
                order = await self.exchange.create_market_buy_order(symbol, quantity)
                order_id = order['id']
                logger.info(f"Bought {quantity} {symbol} at {price}, order ID: {order_id}")
            
            # Record position
            self.positions[symbol] = {
                'entry_price': price,
                'quantity': quantity,
                'entry_time': datetime.now(),
                'order_id': order_id,
                'current_price': price,
                'pnl': 0,
                'pnl_percent': 0
            }
            
            # Reset highest price for trailing stop
            self.highest_prices[symbol] = price
            
            # Update portfolio value
            self.portfolio_value -= position_value
            
            # Update data store
            with self.data_store.lock:
                # Update positions
                self.data_store.positions[symbol] = {
                    'entry_price': price,
                    'current_price': price,
                    'qty': quantity,
                    'pnl': 0,
                    'pnl_percent': 0
                }
                
                # Add to trade history
                self.data_store.trade_history.append({
                    'symbol': symbol,
                    'action': 'BUY',
                    'price': price,
                    'quantity': quantity,
                    'value': position_value,
                    'timestamp': datetime.now(),
                    'order_id': order_id
                })
                
                # Add to portfolio history
                self.data_store.portfolio_history.append({
                    'timestamp': datetime.now(),
                    'value': self.portfolio_value
                })
                
                # Add system alert
                self.data_store.alerts.append({
                    'timestamp': datetime.now(),
                    'message': f"Bought {quantity:.6f} {symbol} at {price:.4f}",
                    'type': 'success'
                })
            
            return True
        
        except Exception as e:
            logger.error(f"Error executing buy for {symbol}: {e}")
            
            # Add error alert to data store
            with self.data_store.lock:
                self.data_store.alerts.append({
                    'timestamp': datetime.now(),
                    'message': f"Error buying {symbol}: {str(e)}",
                    'type': 'error'
                })
            
            return False

    async def execute_sell(self, symbol, price, reason):
        """Execute a sell order for a symbol."""
        try:
            # Check if we're in this position
            if symbol not in self.positions:
                logger.warning(f"Not in position for {symbol}")
                return False
            
            position = self.positions[symbol]
            quantity = position['quantity']
            
            # Execute order
            if self.test_mode:
                logger.info(f"TEST MODE: Would sell {quantity} {symbol} at {price}, reason: {reason}")
                order_id = f"test-{int(time.time())}"
            else:
                # Real order execution
                order = await self.exchange.create_market_sell_order(symbol, quantity)
                order_id = order['id']
                logger.info(f"Sold {quantity} {symbol} at {price}, reason: {reason}, order ID: {order_id}")
            
            # Calculate PnL
            entry_price = position['entry_price']
            position_value = quantity * price
            initial_value = quantity * entry_price
            pnl = position_value - initial_value
            pnl_percent = (price - entry_price) / entry_price * 100
            
            # Update portfolio value
            self.portfolio_value += position_value
            
            # Update data store
            with self.data_store.lock:
                # Add to trade history
                self.data_store.trade_history.append({
                    'symbol': symbol,
                    'action': 'SELL',
                    'price': price,
                    'quantity': quantity,
                    'value': position_value,
                    'pnl': pnl,
                    'pnl_percent': pnl_percent,
                    'timestamp': datetime.now(),
                    'reason': reason,
                    'order_id': order_id
                })
                
                # Remove from positions
                if symbol in self.data_store.positions:
                    del self.data_store.positions[symbol]
                
                # Add to portfolio history
                self.data_store.portfolio_history.append({
                    'timestamp': datetime.now(),
                    'value': self.portfolio_value
                })
                
                # Add system alert
                alert_type = 'success' if pnl >= 0 else 'warning'
                self.data_store.alerts.append({
                    'timestamp': datetime.now(),
                    'message': f"Sold {quantity:.6f} {symbol} at {price:.4f} ({pnl_percent:.2f}%) - {reason}",
                    'type': alert_type
                })
            
            # Remove from positions
            del self.positions[symbol]
            if symbol in self.highest_prices:
                del self.highest_prices[symbol]
            
            return True
        
        except Exception as e:
            logger.error(f"Error executing sell for {symbol}: {e}")
            
            # Add error alert to data store
            with self.data_store.lock:
                self.data_store.alerts.append({
                    'timestamp': datetime.now(),
                    'message': f"Error selling {symbol}: {str(e)}",
                    'type': 'error'
                })
            
            return False

    async def scan_for_entries(self):
        """Scan for potential entry opportunities."""
        try:
            # Skip if we're at max positions
            if len(self.positions) >= self.max_positions:
                return
            
            # Get available funds
            available_funds = self.portfolio_value * self.position_size_pct
            if available_funds < 10:  # Minimum order size (adjust as needed)
                return
            
            # Find potential entries
            for symbol in self.symbols:
                # Skip if already in position
                if symbol in self.positions:
                    continue
                
                # Skip if no price data
                if symbol not in self.price_data or not self.price_data[symbol]['current']:
                    continue
                
                current_price = self.price_data[symbol]['current']
                price_history = self.price_data[symbol]['history']
                
                # Need at least some price history
                if len(price_history) < 10:
                    continue
                
                # Simple entry strategy: 5% increase in the last 10 minutes
                oldest_price = price_history[0]['price'] if len(price_history) > 0 else current_price
                price_change = (current_price - oldest_price) / oldest_price * 100
                
                if price_change >= 5:
                    logger.info(f"Entry signal for {symbol}: {price_change:.2f}% increase")
                    await self.execute_buy(symbol, current_price)
                    
                    # Stop after one entry to avoid entering too many positions at once
                    if len(self.positions) >= self.max_positions:
                        break
        
        except Exception as e:
            logger.error(f"Error scanning for entries: {e}")

    async def run(self):
        """Main strategy execution loop."""
        try:
            # Initialize
            success = await self.initialize()
            if not success:
                logger.error("Failed to initialize strategy")
                return
            
            # Find top gainers
            await self.find_top_gainers()
            
            # Setup websockets
            success = await self.setup_websockets()
            if not success:
                logger.error("Failed to set up websockets")
                return
            
            # Main loop
            self.running = True
            logger.info("Starting main strategy loop")
            
            while self.running:
                # Scan for entries
                await self.scan_for_entries()
                
                # Update positions (in case we missed any websocket updates)
                for symbol in list(self.positions.keys()):
                    await self.update_position_status(symbol)
                
                # Refresh top gainers every hour
                if datetime.now().minute == 0:
                    await self.find_top_gainers()
                
                # Sleep to avoid excessive CPU usage
                await asyncio.sleep(10)
                
        except KeyboardInterrupt:
            logger.info("Strategy interrupted by user")
            self.running = False
            
        except Exception as e:
            logger.error(f"Error in main strategy loop: {e}")
            self.running = False
            
        finally:
            # Clean up
            await self.cleanup()

    async def cleanup(self):
        """Clean up resources when shutting down."""
        logger.info("Cleaning up resources...")
        
        # Close websocket connections
        await self.ws_client.close_all()
        await self.exchange.close()
        
        logger.info("Cleanup complete")

    async def emergency_exit_all(self):
        """Emergency exit all positions."""
        logger.warning("EMERGENCY EXIT: Closing all positions")
        
        with self.data_store.lock:
            self.data_store.alerts.append({
                'timestamp': datetime.now(),
                'message': "EMERGENCY EXIT: Closing all positions",
                'type': 'error'
            })
        
        for symbol in list(self.positions.keys()):
            current_price = self.price_data[symbol]['current']
            await self.execute_sell(symbol, current_price, "Emergency exit")
        
        logger.warning(f"EMERGENCY EXIT COMPLETE: Closed {len(self.positions)} positions")

# Function to run the dashboard in a separate thread
def run_dashboard():
    app.run(debug=False, host='0.0.0.0', port=8050)

# Main function
async def main():
    # Parse command-line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Crypto Trading Strategy')
    parser.add_argument('--api-key', help='Binance API key')
    parser.add_argument('--api-secret', help='Binance API secret')
    parser.add_argument('--test', action='store_true', help='Run in test mode (no real orders)')
    args = parser.parse_args()
    
    # Start dashboard in a separate thread
    dashboard_thread = threading.Thread(target=run_dashboard)
    dashboard_thread.daemon = True
    dashboard_thread.start()
    
    # Create and run the strategy
    strategy = SwingHighRealtime(
        api_key=args.api_key,
        api_secret=args.api_secret,
        test_mode=args.test
    )
    
    await strategy.run()

if __name__ == "__main__":
    asyncio.run(main())