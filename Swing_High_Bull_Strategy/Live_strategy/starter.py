#!/usr/bin/env python3

import os
import sys
import subprocess
import argparse
import time

def main():
    parser = argparse.ArgumentParser(description='Start the trading system')
    parser.add_argument('--api-key', help='Binance API key')
    parser.add_argument('--api-secret', help='Binance API secret')
    parser.add_argument('--test', action='store_true', help='Run in test mode (no real orders)')
    args = parser.parse_args()
    
    # Set environment variables if API credentials provided
    env = os.environ.copy()
    if args.api_key:
        env['BINANCE_API_KEY'] = args.api_key
    if args.api_secret:
        env['BINANCE_API_SECRET'] = args.api_secret
    
    # Construct command
    cmd = [sys.executable, 'realtime_strategy.py']
    if args.api_key:
        cmd.extend(['--api-key', args.api_key])
    if args.api_secret:
        cmd.extend(['--api-secret', args.api_secret])
    if args.test:
        cmd.append('--test')
    
    # Start the trading strategy
    print("Starting trading system...")
    process = subprocess.Popen(cmd, env=env)
    
    try:
        process.wait()
    except KeyboardInterrupt:
        print("Stopping trading system...")
        process.terminate()
        process.wait()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())