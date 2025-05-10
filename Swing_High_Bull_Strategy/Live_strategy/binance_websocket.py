import json
import asyncio
import websockets
import hmac
import hashlib
import time
import logging
from typing import Dict, List, Callable, Any, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('binance_websocket')

class BinanceWebsocketClient:
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_endpoint = "wss://stream.binance.com:9443/ws"
        self.stream_endpoint = "wss://stream.binance.com:9443/stream"
        self.connections = {}  # Store active connections
        self.callbacks = {}    # Store message callbacks
        self.running = False
        self.keep_running = True

    async def _listen_forever(self, ws, stream_name):
        """Listen to websocket messages indefinitely."""
        try:
            while self.keep_running:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=30)
                    await self._process_message(stream_name, json.loads(msg))
                except asyncio.TimeoutError:
                    try:
                        pong = await ws.ping()
                        await asyncio.wait_for(pong, timeout=10)
                        logger.debug(f"Ping successful on {stream_name}")
                    except asyncio.TimeoutError:
                        logger.warning(f"Ping timeout on {stream_name}, reconnecting...")
                        break
                except websockets.exceptions.ConnectionClosed:
                    logger.warning(f"Connection closed for {stream_name}, reconnecting...")
                    break
        finally:
            await ws.close()
            if stream_name in self.connections:
                del self.connections[stream_name]
            if self.keep_running:
                logger.info(f"Reconnecting to {stream_name}...")
                await self.connect_to_stream(stream_name)

    async def _process_message(self, stream_name, msg):
        """Process incoming websocket messages."""
        if stream_name in self.callbacks:
            for callback in self.callbacks[stream_name]:
                await callback(msg)

    async def connect_to_stream(self, stream_name):
        """Connect to a specific stream."""
        if stream_name in self.connections:
            logger.warning(f"Already connected to {stream_name}")
            return

        ws = await websockets.connect(f"{self.base_endpoint}/{stream_name}")
        self.connections[stream_name] = ws
        asyncio.create_task(self._listen_forever(ws, stream_name))
        logger.info(f"Connected to {stream_name}")

    async def connect_to_multiple_streams(self, streams):
        """Connect to multiple streams at once using the combined stream."""
        streams_str = '/'.join(streams)
        ws = await websockets.connect(f"{self.stream_endpoint}?streams={streams_str}")
        
        for stream in streams:
            self.connections[stream] = ws
            
        asyncio.create_task(self._listen_forever(ws, streams_str))
        logger.info(f"Connected to combined streams: {streams_str}")

    def add_callback(self, stream_name, callback):
        """Add a callback for a specific stream."""
        if stream_name not in self.callbacks:
            self.callbacks[stream_name] = []
        self.callbacks[stream_name].append(callback)

    async def subscribe_ticker(self, symbol, callback):
        """Subscribe to ticker updates for a symbol."""
        stream_name = f"{symbol.lower()}@ticker"
        self.add_callback(stream_name, callback)
        await self.connect_to_stream(stream_name)

    async def subscribe_klines(self, symbol, interval, callback):
        """Subscribe to kline/candlestick updates."""
        stream_name = f"{symbol.lower()}@kline_{interval}"
        self.add_callback(stream_name, callback)
        await self.connect_to_stream(stream_name)

    async def subscribe_trade(self, symbol, callback):
        """Subscribe to trade updates."""
        stream_name = f"{symbol.lower()}@trade"
        self.add_callback(stream_name, callback)
        await self.connect_to_stream(stream_name)

    async def subscribe_depth(self, symbol, callback, level="20"):
        """Subscribe to order book updates."""
        stream_name = f"{symbol.lower()}@depth{level}"
        self.add_callback(stream_name, callback)
        await self.connect_to_stream(stream_name)

    async def close_all(self):
        """Close all websocket connections."""
        self.keep_running = False
        for stream_name, ws in list(self.connections.items()):
            await ws.close()
            logger.info(f"Closed connection to {stream_name}")
        self.connections = {}
        self.callbacks = {}