import numpy as np
import pandas as pd
import time
import os
import csv
import sys
import threading
import math
import json
import websocket
import logging
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
from binance.client import Client
from binance.spot import Spot
from binance.exceptions import BinanceAPIException
import ta
from ta.volatility import BollingerBands, AverageTrueRange
from ta.momentum import RSIIndicator
from ta.trend import MACD, ADXIndicator
from concurrent.futures import ThreadPoolExecutor
import numba
from numba import jit, cuda
import queue
import signal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("trading_log.txt"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("GPULiveScalper")

# Load environment variables
load_dotenv()

# Initialize Binance clients
api_key = os.getenv('Binance_API_KEY')
api_secret = os.getenv('Binance_secret_KEY')
client = Client(api_key, api_secret)
spot_client = Spot(api_key=api_key, api_secret=api_secret)

# GPU-accelerated calculations using Numba
@jit(nopython=True)
def calculate_rsi_numba(close_prices, period=14):
    """Calculate RSI using Numba for GPU acceleration"""
    deltas = np.diff(close_prices)
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum()/period
    down = -seed[seed < 0].sum()/period
    
    rs = up/down if down != 0 else np.inf
    rsi = np.zeros_like(close_prices)
    rsi[:period] = 100. - 100./(1. + rs)
    
    for i in range(period, len(close_prices)):
        delta = deltas[i-1]
        if delta > 0:
            upval = delta
            downval = 0
        else:
            upval = 0
            downval = -delta
            
        up = (up * (period-1) + upval) / period
        down = (down * (period-1) + downval) / period
        
        rs = up/down if down != 0 else np.inf
        rsi[i] = 100. - 100./(1. + rs)
        
    return rsi

@jit(nopython=True)
def calculate_bollinger_bands_numba(close_prices, window=20, num_std=2):
    """Calculate Bollinger Bands using Numba for GPU acceleration"""
    rolling_mean = np.zeros_like(close_prices)
    rolling_std = np.zeros_like(close_prices)
    upper_band = np.zeros_like(close_prices)
    lower_band = np.zeros_like(close_prices)
    
    for i in range(window-1, len(close_prices)):
        rolling_mean[i] = np.mean(close_prices[i-window+1:i+1])
        rolling_std[i] = np.std(close_prices[i-window+1:i+1])
        upper_band[i] = rolling_mean[i] + (rolling_std[i] * num_std)
        lower_band[i] = rolling_mean[i] - (rolling_std[i] * num_std)
    
    return rolling_mean, upper_band, lower_band

@jit(nopython=True)
def calculate_atr_numba(high, low, close, period=14):
    """Calculate ATR using Numba for GPU acceleration"""
    atr = np.zeros_like(close)
    tr = np.zeros_like(close)
    
    for i in range(1, len(close)):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i-1]),
            abs(low[i] - close[i-1])
        )
    
    atr[period] = np.mean(tr[1:period+1])
    
    for i in range(period+1, len(close)):
        atr[i] = (atr[i-1] * (period-1) + tr[i]) / period
        
    return atr

@jit(nopython=True)
def calculate_entry_exit_signals_numba(
    close, rsi, bb_middle, bb_upper, atr, 
    prev_macd_diff, curr_macd_diff, adx, di_plus, di_minus,
    rsi_threshold=30, adx_threshold=25
):
    """Accelerated calculation of entry and exit signals"""
    entry_signals = np.zeros(len(close), dtype=np.int8)
    exit_signals = np.zeros(len(close), dtype=np.int8)
    
    for i in range(1, len(close)):
        # Entry conditions
        trend_condition = (close[i] > bb_middle[i] and 
                          adx[i] > adx_threshold and 
                          di_plus[i] > di_minus[i])
        
        momentum_entry = (rsi[i] > rsi_threshold and 
                         rsi[i] < 60 and 
                         curr_macd_diff[i] > 0 and 
                         prev_macd_diff[i] < curr_macd_diff[i])
        
        volatility_entry = (close[i] > bb_upper[i-1])
        
        if trend_condition and (momentum_entry or volatility_entry):
            entry_signals[i] = 1
            
        # Exit conditions
        overbought_exit = (rsi[i] > 70 and rsi[i-1] < rsi[i])
        macd_reversal = (curr_macd_diff[i] < 0 and prev_macd_diff[i] > 0)
        
        if overbought_exit or macd_reversal:
            exit_signals[i] = 1
            
    return entry_signals, exit_signals


class GPUScalpingStrategy:
    def __init__(self, symbol, initial_portfolio_value=1000, risk_per_trade=0.01, 
                 fee_rate=0.001, max_position_pct=0.2, use_gpu=True, debug=False):
        self.symbol = symbol
        self.ticker = self.symbol.replace("/", "")  # Convert from BTC/USDT to BTCUSDT format for WebSocket
        self.risk_per_trade = risk_per_trade
        self.fee_rate = fee_rate
        self.max_position_pct = max_position_pct
        self.use_gpu = use_gpu
        self.debug = debug
        
        # Trading state
        self.portfolio_value = initial_portfolio_value
        self.initial_portfolio_value = initial_portfolio_value
        self.available_funds = initial_portfolio_value
        self.position = 0
        self.quantity = 0
        self.buy_price = None
        self.highest_price = None
        self.initial_stop = None
        self.asset_value = 0
        self.trades = []
        
        # Technical parameters
        self.rsi_period = 14
        self.bb_period = 20
        self.atr_period = 14
        self.atr_multiplier = 2.0
        self.adx_threshold = 25
        self.rsi_oversold = 30
        self.rsi_overbought = 70
        
        # Data management
        self.price_queue = queue.Queue(maxsize=5000)  # Store incoming price data
        self.klines_data = {}  # Store historical and streaming kline data
        self.df = None  # DataFrame with indicator data
        self.last_kline_time = None
        self.last_price = None
        
        # Thread management
        self.running = False
        self.threads = []
        self.lock = threading.Lock()
        
        # WebSocket connection
        self.ws = None
        self.ws_reconnect_count = 0
        self.max_reconnects = 5
        
        # Log initial setup
        logger.info(f"Initializing GPU-accelerated live trading for {symbol}")
        logger.info(f"GPU acceleration: {'Enabled' if use_gpu else 'Disabled'}")

    def fetch_initial_data(self, lookback_hours=24):
        """Fetch historical data to initialize indicators"""
        logger.info(f"Fetching initial historical data for {self.symbol}...")
        
        start_time = datetime.now() - timedelta(hours=lookback_hours)
        start_time_ms = int(start_time.timestamp() * 1000)
        
        try:
            # Fetch 1-minute klines
            klines = client.get_historical_klines(
                self.ticker, 
                Client.KLINE_INTERVAL_1MINUTE, 
                start_str=start_time_ms
            )
            
            if not klines:
                logger.error(f"No historical data retrieved for {self.symbol}")
                return False
                
            # Process the klines into our data structure
            for kline in klines:
                timestamp = int(kline[0])
                self.klines_data[timestamp] = {
                    'open_time': timestamp,
                    'open': float(kline[1]),
                    'high': float(kline[2]),
                    'low': float(kline[3]),
                    'close': float(kline[4]),
                    'volume': float(kline[5]),
                    'close_time': int(kline[6])
                }
            
            logger.info(f"Successfully fetched {len(klines)} historical candles")
            
            # Update last kline time
            if klines:
                self.last_kline_time = int(klines[-1][0])
                
            # Convert to DataFrame and calculate indicators
            self.update_dataframe()
            return True
            
        except Exception as e:
            logger.error(f"Error fetching historical data: {e}")
            return False

    def update_dataframe(self):
        """Convert klines data to DataFrame and calculate indicators"""
        try:
            # Convert dictionary to DataFrame
            if not self.klines_data:
                logger.warning("No klines data available to update DataFrame")
                return
                
            df = pd.DataFrame(self.klines_data.values())
            
            # Sort by open_time to ensure chronological order
            df = df.sort_values('open_time')
            
            # Extract OHLCV data for indicator calculations
            close_prices = df['close'].values
            high_prices = df['high'].values
            low_prices = df['low'].values
            
            # Calculate indicators using GPU-accelerated functions if enabled
            if self.use_gpu:
                try:
                    # Numba-accelerated calculations
                    df['rsi'] = calculate_rsi_numba(close_prices, self.rsi_period)
                    bb_middle, bb_upper, bb_lower = calculate_bollinger_bands_numba(
                        close_prices, self.bb_period, 2
                    )
                    df['bb_middle'] = bb_middle
                    df['bb_upper'] = bb_upper
                    df['bb_lower'] = bb_lower
                    df['atr'] = calculate_atr_numba(
                        high_prices, low_prices, close_prices, self.atr_period
                    )
                    
                    # For MACD and ADX, we'll still use TA-Lib as they're more complex
                    macd = MACD(close=pd.Series(close_prices))
                    df['macd'] = macd.macd().values
                    df['macd_signal'] = macd.macd_signal().values
                    df['macd_diff'] = macd.macd_diff().values
                    
                    adx_indicator = ADXIndicator(
                        high=pd.Series(high_prices), 
                        low=pd.Series(low_prices), 
                        close=pd.Series(close_prices)
                    )
                    df['adx'] = adx_indicator.adx().values
                    df['di_plus'] = adx_indicator.adx_pos().values
                    df['di_minus'] = adx_indicator.adx_neg().values
                    
                    logger.debug("Calculated indicators using GPU acceleration")
                    
                except Exception as e:
                    logger.error(f"Error during GPU-accelerated calculations: {e}")
                    logger.info("Falling back to CPU calculations")
                    self.use_gpu = False
                    # Fall back to non-accelerated calculations
            
            # If GPU acceleration failed or is disabled, use regular TA calculations
            if not self.use_gpu:
                # Calculate indicators using TA-lib
                df['rsi'] = RSIIndicator(close=df['close']).rsi()
                
                bb = BollingerBands(close=df['close'], window=self.bb_period)
                df['bb_upper'] = bb.bollinger_hband()
                df['bb_middle'] = bb.bollinger_mavg() 
                df['bb_lower'] = bb.bollinger_lband()
                
                atr = AverageTrueRange(
                    high=df['high'], low=df['low'], close=df['close'], window=self.atr_period
                )
                df['atr'] = atr.average_true_range()
                
                macd = MACD(close=df['close'])
                df['macd'] = macd.macd()
                df['macd_signal'] = macd.macd_signal()
                df['macd_diff'] = macd.macd_diff()
                
                adx = ADXIndicator(high=df['high'], low=df['low'], close=df['close'])
                df['adx'] = adx.adx()
                df['di_plus'] = adx.adx_pos()
                df['di_minus'] = adx.adx_neg()
                
                logger.debug("Calculated indicators using CPU")
            
            # Update the DataFrame
            self.df = df
            
            # Update last price
            if not df.empty:
                self.last_price = df['close'].iloc[-1]
                
            logger.debug(f"DataFrame updated with {len(df)} rows, last price: {self.last_price}")
            
        except Exception as e:
            logger.error(f"Error updating DataFrame: {e}")

    def connect_websocket(self):
        """Establish WebSocket connection to Binance"""
        socket_url = f"wss://stream.binance.com:9443/ws/{self.ticker.lower()}@kline_1m"
        
        def on_message(ws, message):
            try:
                json_message = json.loads(message)
                
                # Extract kline data
                kline = json_message['k']
                
                # Process only completed klines for indicator calculations
                is_kline_closed = kline['x']
                
                # Always update the latest price for real-time monitoring
                self.last_price = float(kline['c'])
                
                # If this is a completed kline, add it to our klines data
                if is_kline_closed:
                    timestamp = int(kline['t'])  # Kline start time
                    
                    # Store the new kline
                    self.klines_data[timestamp] = {
                        'open_time': timestamp,
                        'open': float(kline['o']),
                        'high': float(kline['h']),
                        'low': float(kline['l']),
                        'close': float(kline['c']),
                        'volume': float(kline['v']),
                        'close_time': int(kline['T'])
                    }
                    
                    # Update the last kline time
                    self.last_kline_time = timestamp
                    
                    # Update indicators with the new data
                    self.update_dataframe()
                    
                    logger.debug(f"New kline processed: {datetime.fromtimestamp(timestamp/1000)}")
                
                # Add the current price to the price queue for real-time processing
                if not self.price_queue.full():
                    self.price_queue.put({
                        'price': float(kline['c']),
                        'timestamp': int(kline['T']),
                        'is_closed': is_kline_closed
                    })
                
            except Exception as e:
                logger.error(f"Error processing WebSocket message: {e}")
        
        def on_error(ws, error):
            logger.error(f"WebSocket error: {error}")
        
        def on_close(ws, close_status_code, close_msg):
            logger.info(f"WebSocket connection closed: {close_status_code} - {close_msg}")
            
            # Attempt to reconnect if still running
            if self.running and self.ws_reconnect_count < self.max_reconnects:
                self.ws_reconnect_count += 1
                logger.info(f"Attempting to reconnect (attempt {self.ws_reconnect_count}/{self.max_reconnects})...")
                time.sleep(5)  # Wait 5 seconds before reconnecting
                self.connect_websocket()
        
        def on_open(ws):
            logger.info("WebSocket connection established")
            self.ws_reconnect_count = 0  # Reset reconnect counter on successful connection
        
        # Create WebSocket connection
        self.ws = websocket.WebSocketApp(
            socket_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        
        # Start WebSocket connection in a separate thread
        ws_thread = threading.Thread(target=self.ws.run_forever, kwargs={"ping_interval": 30})
        ws_thread.daemon = True
        ws_thread.start()
        
        self.threads.append(ws_thread)
        logger.info(f"WebSocket thread started for {self.symbol}")

    def process_trading_signals(self):
        """Process price data and execute trades based on signals"""
        logger.info("Starting trading signal processor")
        
        while self.running:
            try:
                # Check if we have sufficient data for trading decisions
                if self.df is None or len(self.df) < 50:
                    logger.debug("Waiting for sufficient data...")
                    time.sleep(1)
                    continue
                
                # Get the latest candle data for signal generation
                with self.lock:
                    df = self.df.copy()
                
                # Skip if no data available
                if df.empty:
                    time.sleep(1)
                    continue
                
                # Get the latest data point
                last_row = df.iloc[-1]
                
                # Current market price (from real-time WebSocket feed)
                current_price = self.last_price
                
                # No position - check for entry
                if self.position == 0:
                    # Check entry conditions
                    entry_signal, entry_reason = self.check_entry_signal(last_row, df)
                    
                    if entry_signal and self.available_funds > 100:
                        # Calculate position size
                        stop_price = current_price - (last_row['atr'] * self.atr_multiplier)
                        risk_per_unit = current_price - stop_price
                        
                        if risk_per_unit > 0:
                            risk_amount = self.portfolio_value * self.risk_per_trade
                            position_size = risk_amount / risk_per_unit
                            
                            # Apply constraints
                            max_position_size = self.portfolio_value * self.max_position_pct / current_price
                            self.quantity = min(position_size, max_position_size, self.available_funds / current_price)
                            
                            # Execute buy order
                            order_successful = self.execute_order('BUY', current_price, datetime.now(), entry_reason)
                            
                            if order_successful:
                                self.buy_price = current_price
                                self.highest_price = current_price
                                self.initial_stop = stop_price
                                self.position = 1
                                logger.info(f"ENTRY: {entry_reason} at {current_price:.2f}")
                
                # Have position - check for exit
                elif self.position == 1:
                    # Update highest price for trailing stop
                    if current_price > self.highest_price:
                        self.highest_price = current_price
                    
                    # Check exit conditions
                    exit_signal, exit_reason = self.check_exit_signal(
                        last_row, df, self.buy_price, self.highest_price, self.initial_stop
                    )
                    
                    if exit_signal:
                        # Execute sell order
                        order_successful = self.execute_order('SELL', current_price, datetime.now(), exit_reason)
                        
                        if order_successful:
                            profit_pct = (current_price - self.buy_price) / self.buy_price
                            logger.info(f"EXIT: {exit_reason} at {current_price:.2f}, P&L: {profit_pct:.2%}")
                            
                            self.buy_price = None
                            self.highest_price = None
                            self.initial_stop = None
                            self.position = 0
                
                # Sleep to prevent excessive CPU usage
                time.sleep(0.2)
                
            except Exception as e:
                logger.error(f"Error in trading signal processor: {e}")
                time.sleep(1)

    def check_entry_signal(self, row, df):
        """Check if entry conditions are met"""
        try:
            prev_row = df.iloc[-2] if len(df) > 1 else row
            
            # Dynamic threshold adjustment based on market conditions
            adx_threshold = self.adx_threshold
            rsi_threshold = self.rsi_oversold
            
            # Baseline trend conditions
            trend_condition = (
                row['close'] > row['bb_middle'] and
                row['adx'] > adx_threshold and
                row['di_plus'] > row['di_minus']
            )
            
            # Momentum entry
            momentum_entry = (
                row['rsi'] > rsi_threshold and
                row['rsi'] < 60 and  # Not overbought
                row['macd_diff'] > 0 and
                prev_row['macd_diff'] < row['macd_diff']  # Increasing momentum
            )
            
            # Volatility breakout entry
            volatility_entry = (
                row['close'] > prev_row['bb_upper'] and
                row['volume'] > prev_row['volume'] * 1.5  # Above average volume
            )
            
            # Combined entry signals with reasons
            if trend_condition and momentum_entry:
                return True, "Momentum entry with trend alignment"
            elif trend_condition and volatility_entry:
                return True, "Volatility breakout with volume confirmation"
                
            return False, ""
            
        except Exception as e:
            logger.error(f"Error checking entry signal: {e}")
            return False, ""

    def check_exit_signal(self, row, df, buy_price, highest_price, initial_stop):
        """Check if exit conditions are met"""
        try:
            if buy_price is None:
                return False, ""
                
            prev_row = df.iloc[-2] if len(df) > 1 else row
            current_price = row['close']
            
            # Get ATR for dynamic stops
            atr = row['atr']
            
            # 1. Take profit based on volatility
            profit_threshold = min(self.atr_multiplier * atr / buy_price, 0.03)  # Cap at 3%
            if (current_price - buy_price) / buy_price >= profit_threshold:
                return True, f"Take profit target reached ({profit_threshold:.2%})"
                
            # 2. Trailing stop based on ATR
            trailing_stop = highest_price - (self.atr_multiplier * atr)
            if current_price < trailing_stop:
                loss_pct = (highest_price - current_price) / highest_price
                return True, f"Trailing stop hit ({loss_pct:.2%} from high)"
                
            # 3. Technical signal reversal
            if row['rsi'] > 70 and prev_row['rsi'] < row['rsi']:
                return True, "RSI overbought and increasing"
                
            if row['macd_diff'] < 0 and prev_row['macd_diff'] > 0:
                return True, "MACD crossed below signal line"
                
            # 4. Fixed stop loss from entry (risk management)
            if current_price < initial_stop:
                loss_pct = (buy_price - current_price) / buy_price
                return True, f"Initial stop loss hit ({loss_pct:.2%})"
                
            return False, ""
            
        except Exception as e:
            logger.error(f"Error checking exit signal: {e}")
            return False, ""

    def execute_order(self, side, price, timestamp, reason=""):
        """Execute order on Binance"""
        try:
            # For BUY orders
            if side == 'BUY':
                # Check that we have enough funds
                if self.available_funds < price * self.quantity:
                    logger.warning(f"Insufficient funds for {side} order: {self.available_funds:.2f} < {price * self.quantity:.2f}")
                    return False
                
                # Normalize quantity according to Binance rules
                quantity = self.normalize_quantity(self.quantity)
                
                # Place order on Binance
                logger.info(f"Placing {side} order for {quantity:.8f} {self.symbol} at {price:.2f}")
                
                try:
                    order = spot_client.new_order(
                        symbol=self.ticker,
                        side="BUY",
                        type="MARKET",
                        quantity=quantity
                    )
                    
                    # Update account state
                    purchase_cost = quantity * price * (1 + self.fee_rate)
                    self.available_funds -= purchase_cost
                    self.asset_value = quantity * price
                    self.quantity = quantity
                    
                    # Log the order
                    logger.info(f"BUY order executed: {quantity:.8f} {self.symbol} at {price:.2f}")
                    logger.info(f"Reason: {reason}")
                    logger.info(f"Available funds: {self.available_funds:.2f}, Asset value: {self.asset_value:.2f}")
                    
                    # Record the trade
                    self.trades.append({
                        'side': 'BUY',
                        'price': price,
                        'time': timestamp,
                        'quantity': quantity,
                        'fee': price * quantity * self.fee_rate,
                        'reason': reason
                    })
                    
                    return True
                    
                except BinanceAPIException as e:
                    logger.error(f"Binance API error during BUY: {e}")
                    return False
                except Exception as e:
                    logger.error(f"Error executing BUY order: {e}")
                    return False
            
            # For SELL orders
            elif side == 'SELL':
                if self.quantity <= 0:
                    logger.warning(f"No quantity to sell")
                    return False
                
                # Normalize quantity according to Binance rules
                quantity = self.normalize_quantity(self.quantity)
                
                # Place order on Binance
                logger.info(f"Placing {side} order for {quantity:.8f} {self.symbol} at {price:.2f}")
                
                try:
                    order = spot_client.new_order(
                        symbol=self.ticker,
                        side="SELL",
                        type="MARKET",
                        quantity=quantity
                    )
                    
                    # Update account state
                    sale_proceeds = quantity * price * (1 - self.fee_rate)
                    self.available_funds += sale_proceeds
                    self.asset_value = 0
                    buy_price = self.buy_price
                    
                    # Calculate portfolio value
                    self.portfolio_value = self.available_funds + self.asset_value
                    
                    # Log the order
                    logger.info(f"SELL order executed: {quantity:.8f} {self.symbol} at {price:.2f}")
                    logger.info(f"Reason: {reason}")
                    logger.info(f"Available funds: {self.available_funds:.2f}, Portfolio value: {self.portfolio_value:.2f}")
                    
                    # Record the trade with P&L information
                    profit_loss = (price - buy_price) / buy_price if buy_price else 0
                    
                    self.trades.append({
                        'side': 'SELL',
                        'price': price,
                        'time': timestamp,
                        'quantity': quantity,
                        'fee': price * quantity * self.fee_rate,
                        'buy_price': buy_price,
                        'profit_loss': profit_loss,
                        'reason': reason
                    })
                    
                    return True
                    
                except BinanceAPIException as e:
                    logger.error(f"Binance API error during SELL: {e}")
                    return False
                except Exception as e:
                    logger.error(f"Error executing SELL order: {e}")
                    return False
            
            return False
            
        except Exception as e:
            logger.error(f"Error in execute_order: {e}")
            return False

    def normalize_quantity(self, quantity):
        """Normalize quantity according to Binance rules"""
        try:
            # Get symbol info
            exchange_info = spot_client.exchange_info(symbol=self.ticker)
            
            # Find the LOT_SIZE filter
            lot_size_filter = next(filter(lambda x: x['filterType'] == 'LOT_SIZE', 
                                        exchange_info['symbols'][0]['filters']), None)
            
            if lot_size_filter:
                step_size = float(lot_size_filter['stepSize'])
                
                # Calculate decimal places
                if step_size < 1:
                    decimal_places = len(str(step_size).split('.')[-1].rstrip('0'))
                else:
                    decimal_places = 0
                
                # Normalize quantity
                normalized_qty = math.floor(quantity / step_size) * step_size
                normalized_qty = round(normalized_qty, decimal_places)
                
                return normalized_qty
            else:
                # If no LOT_SIZE filter, return quantity with 8 decimal places (Binance default)
                return round(quantity, 8)
        
        except Exception as e:
            logger.error(f"Error normalizing quantity: {e}")
            # Return quantity with 8 decimal places as fallback
            return round(quantity, 8)

    def monitor_account_balance(self):
        """Monitor account balance and update available funds"""
        logger.info("Starting account balance monitor")
        
        while self.running:
            try:
                # Get account info
                account = spot_client.account()
                
                # Find USDT balance
                for balance in account['balances']:
                    if balance['asset'] == 'USDT':
                        usdt_balance = float(balance['free'])
                        
                # Find asset balance
                asset = self.ticker.replace('USDT', '')
                asset_balance = 0
                for balance in account['balances']:
                    if balance['asset'] == asset:
                        asset_balance = float(balance['free'])
                
                # Update available funds (only if not in a position)
                if self.position == 0:
                    self.available_funds = usdt_balance
                
                # Update portfolio value
                asset_value = asset_balance * self.last_price if self.last_price else 0
                self.portfolio_value = usdt_balance + asset_value
                
                logger.debug(f"Account balance updated: USDT={usdt_balance:.2f}, {asset}={asset_balance}, Portfolio value={self.portfolio_value:.2f}")
                
                # Sleep for 1 minute
                time.sleep(60)
                
            except Exception as e:
                logger.error(f"Error monitoring account balance: {e}")
                time.sleep(30)

    def monitor_performance(self):
        """Monitor strategy performance and write to CSV"""
        logger.info("Starting performance monitor")
        
        # Initialize performance metrics file
        performance_file = f"performance_{self.symbol.replace('/', '')}.csv"
        with open(performance_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Time', 'Portfolio Value', 'Price', 'Position', 'P&L %'])
        
        while self.running:
            try:
                # Calculate performance metrics
                total_pnl = (self.portfolio_value - self.initial_portfolio_value) / self.initial_portfolio_value
                
                # Log performance
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                logger.info(f"Performance update: Portfolio={self.portfolio_value:.2f}, P&L={total_pnl:.2%}")
                
                # Write to CSV
                with open(performance_file, 'a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        current_time, 
                        self.portfolio_value, 
                        self.last_price, 
                        self.position,
                        f"{total_pnl:.2%}"
                    ])
                
                # Sleep for 5 minutes
                time.sleep(300)
                
            except Exception as e:
                logger.error(f"Error monitoring performance: {e}")
                time.sleep(60)
                
    def handle_shutdown(self, signum, frame):
        """Handle graceful shutdown"""
        logger.info("Shutdown signal received. Closing positions and exiting...")
        
        # Set running flag to false
        self.running = False
        
        # Close any open positions
        if self.position == 1 and self.quantity > 0:
            logger.info(f"Closing position of {self.quantity} {self.symbol} before exiting")
            self.execute_order('SELL', self.last_price, datetime.now(), "System shutdown")
        
        # Close WebSocket connection
        if self.ws:
            self.ws.close()
        
        # Write final trades to CSV
        if self.trades:
            trades_file = f"trades_{self.symbol.replace('/', '')}.csv"
            pd.DataFrame(self.trades).to_csv(trades_file, index=False)
            logger.info(f"Trades saved to {trades_file}")
        
        # Log final statistics
        total_pnl = (self.portfolio_value - self.initial_portfolio_value) / self.initial_portfolio_value
        logger.info(f"Final portfolio value: {self.portfolio_value:.2f}")
        logger.info(f"Total P&L: {total_pnl:.2%}")
        logger.info(f"Total trades: {len(self.trades)}")
        
        # Exit
        logger.info("Trading system shutdown complete")
        sys.exit(0)

    def start(self, duration_hours=None):
        """Start the GPU-accelerated live trading strategy"""
        logger.info(f"Starting GPU-accelerated live trading strategy for {self.symbol}")
        
        # Set up signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)
        
        # Fetch initial account balance
        try:
            account = spot_client.account()
            for balance in account['balances']:
                if balance['asset'] == 'USDT':
                    self.available_funds = float(balance['free'])
                    self.portfolio_value = self.available_funds
                    self.initial_portfolio_value = self.portfolio_value
                    logger.info(f"Initial account balance: {self.portfolio_value} USDT")
                    break
        except Exception as e:
            logger.error(f"Error fetching initial account balance: {e}")
            return False
        
        # Fetch initial historical data
        if not self.fetch_initial_data():
            logger.error("Failed to fetch initial data. Exiting.")
            return False
        
        # Set running flag
        self.running = True
        
        # Connect to WebSocket
        self.connect_websocket()
        
        # Start trading signal processor
        signal_processor = threading.Thread(target=self.process_trading_signals)
        signal_processor.daemon = True
        signal_processor.start()
        self.threads.append(signal_processor)
        
        # Start account balance monitor
        balance_monitor = threading.Thread(target=self.monitor_account_balance)
        balance_monitor.daemon = True
        balance_monitor.start()
        self.threads.append(balance_monitor)
        
        # Start performance monitor
        performance_monitor = threading.Thread(target=self.monitor_performance)
        performance_monitor.daemon = True
        performance_monitor.start()
        self.threads.append(performance_monitor)
        
        logger.info("All threads started successfully")
        
        # Run for specified duration if provided
        if duration_hours:
            logger.info(f"Trading will run for {duration_hours} hours")
            end_time = time.time() + duration_hours * 3600
            
            while time.time() < end_time and self.running:
                time.sleep(10)
                
            # Initiate shutdown
            self.handle_shutdown(None, None)
        else:
            # Run indefinitely
            logger.info("Trading started - press Ctrl+C to stop")
            
            # Keep main thread alive
            while self.running:
                time.sleep(10)
                
        return True


if __name__ == "__main__":
    # Parse command line arguments
    import argparse
    
    parser = argparse.ArgumentParser(description='GPU-accelerated Live Trading Strategy')
    parser.add_argument('--symbol', type=str, default='BTC/USDT', help='Trading symbol (e.g., BTC/USDT)')
    parser.add_argument('--initial', type=float, default=1000, help='Initial portfolio value in USDT')
    parser.add_argument('--risk', type=float, default=0.01, help='Risk per trade (default: 0.01 = 1%)')
    parser.add_argument('--no-gpu', action='store_true', help='Disable GPU acceleration')
    parser.add_argument('--duration', type=float, help='Trading duration in hours (optional)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    # Set up logging level
    if args.debug:
        logger.setLevel(logging.DEBUG)
    
    # Initialize strategy
    symbol = args.symbol.replace('/', '')  # Convert BTC/USDT to BTCUSDT
    strategy = GPUScalpingStrategy(
        symbol=symbol,
        initial_portfolio_value=args.initial,
        risk_per_trade=args.risk,
        use_gpu=not args.no_gpu,
        debug=args.debug
    )
    
    # Start trading
    strategy.start(duration_hours=args.duration)
