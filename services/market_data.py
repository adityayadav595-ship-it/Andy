from __future__ import annotations

from dataclasses import dataclass
from time import time

import httpx

from config import MARKET_DATA_API_KEY, MARKET_DATA_API_URL, MAX_CANDLE_AGE_SECONDS


class MarketDataUnavailable(Exception):
    pass


@dataclass(frozen=True)
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class CandleSeries:
    symbol: str
    source: str
    candles: list[Candle]

    @property
    def is_fresh(self) -> bool:
        return bool(self.candles) and time() - self.candles[-1].timestamp <= MAX_CANDLE_AGE_SECONDS


async def fetch_candles(symbol: str, limit: int = 80) -> CandleSeries:
    if not MARKET_DATA_API_URL:
        raise MarketDataUnavailable("No candle-data bridge is configured.")
    headers = {"X-API-Key": MARKET_DATA_API_KEY} if MARKET_DATA_API_KEY else {}
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(
                f"{MARKET_DATA_API_URL}/candles",
                params={"symbol": symbol, "interval": 60, "limit": limit},
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise MarketDataUnavailable("Candle data could not be reached.") from error

    try:
        candles = [
            Candle(
                timestamp=int(item["timestamp"]), open=float(item["open"]), high=float(item["high"]),
                low=float(item["low"]), close=float(item["close"])
            )
            for item in payload["candles"]
        ]
    except (KeyError, TypeError, ValueError) as error:
        raise MarketDataUnavailable("The candle-data response has an invalid format.") from error

    if len(candles) < 35:
        raise MarketDataUnavailable("At least 35 one-minute candles are required.")
    series = CandleSeries(symbol=payload.get("symbol", symbol), source=payload.get("source", "configured data bridge"), candles=candles)
    if not series.is_fresh:
        raise MarketDataUnavailable("Candle data is stale; analysis paused.")
    return series
