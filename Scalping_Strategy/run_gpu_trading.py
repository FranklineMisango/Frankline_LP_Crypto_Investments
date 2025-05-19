#!/usr/bin/env python3
"""
Simple launcher for the GPU-accelerated live trading strategy.
Run with: python run_gpu_trading.py
"""
import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Check for API keys
if not os.getenv('Binance_API_KEY') or not os.getenv('Binance_secret_KEY'):
    print("ERROR: Binance API keys not found in .env file")
    print("Please create a .env file with your Binance API keys:")
    print("Binance_API_KEY=your_api_key")
    print("Binance_secret_KEY=your_api_secret")
    sys.exit(1)

# Import the strategy
try:
    from scalping_gpu_live import GPUScalpingStrategy
except ImportError:
    print("ERROR: Could not import GPUScalpingStrategy")
    print("Make sure you have installed all required dependencies:")
    print("pip install numpy pandas websocket-client numba ta python-binance python-dotenv")
    sys.exit(1)

# Configuration
SYMBOL = "BTCUSDT"  # Trading pair
INITIAL_PORTFOLIO = 1000  # Initial portfolio value in USDT (adjust as needed)
RISK_PER_TRADE = 0.01  # 1% risk per trade
USE_GPU = True  # Set to False to disable GPU acceleration
DURATION_HOURS = None  # None for indefinite trading, or specify hours

if __name__ == "__main__":
    print(f"===== GPU-Accelerated Live Trading Strategy =====")
    print(f"Starting at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Trading symbol: {SYMBOL}")
    print(f"Initial portfolio: {INITIAL_PORTFOLIO} USDT")
    print(f"Risk per trade: {RISK_PER_TRADE*100}%")
    print(f"GPU acceleration: {'Enabled' if USE_GPU else 'Disabled'}")
    
    if DURATION_HOURS:
        print(f"Trading duration: {DURATION_HOURS} hours")
    else:
        print("Trading duration: Indefinite (press Ctrl+C to stop)")
    
    print("=================================================")
    
    # Initialize and start the strategy
    strategy = GPUScalpingStrategy(
        symbol=SYMBOL,
        initial_portfolio_value=INITIAL_PORTFOLIO,
        risk_per_trade=RISK_PER_TRADE,
        use_gpu=USE_GPU,
        debug=False
    )
    
    try:
        # Start the strategy
        strategy.start(duration_hours=DURATION_HOURS)
    except KeyboardInterrupt:
        print("\nTrading stopped by user. Closing positions...")
        # The shutdown handler will take care of closing positions
    except Exception as e:
        print(f"Error running strategy: {e}")
        sys.exit(1)
