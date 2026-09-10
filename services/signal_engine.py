from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from services.market_data import CandleSeries


@dataclass(frozen=True)
class Analysis:
    label: str
    confidence: int
    reasons: list[str]
    caution: str


def ema(values: list[float], period: int) -> float:
    multiplier = 2 / (period + 1)
    current = values[0]
    for value in values[1:]:
        current = (value - current) * multiplier + current
    return current


def rsi(values: list[float], period: int = 14) -> float:
    changes = [values[index] - values[index - 1] for index in range(1, len(values))]
    gains = [max(change, 0) for change in changes[-period:]]
    losses = [abs(min(change, 0)) for change in changes[-period:]]
    average_gain, average_loss = mean(gains), mean(losses)
    if average_loss == 0:
        return 100.0
    return 100 - (100 / (1 + average_gain / average_loss))


def analyse(series: CandleSeries) -> Analysis:
    closes = [candle.close for candle in series.candles]
    last = series.candles[-1]
    fast, slow = ema(closes[-35:], 9), ema(closes[-35:], 21)
    current_rsi = rsi(closes)
    ranges = [candle.high - candle.low for candle in series.candles[-14:]]
    average_range = mean(ranges)
    last_range = last.high - last.low
    body = abs(last.close - last.open)
    reasons: list[str] = []
    score = 0

    if fast > slow:
        score += 1
        reasons.append("EMA 9 is above EMA 21")
    elif fast < slow:
        score -= 1
        reasons.append("EMA 9 is below EMA 21")
    if 52 <= current_rsi <= 68:
        score += 1
        reasons.append(f"RSI is constructive at {current_rsi:.0f}")
    elif 32 <= current_rsi <= 48:
        score -= 1
        reasons.append(f"RSI is weak at {current_rsi:.0f}")
    else:
        reasons.append(f"RSI is stretched at {current_rsi:.0f}")
    if last.close > last.open and body >= average_range * 0.35:
        score += 1
        reasons.append("latest candle closed with bullish momentum")
    elif last.close < last.open and body >= average_range * 0.35:
        score -= 1
        reasons.append("latest candle closed with bearish momentum")
    else:
        reasons.append("latest candle momentum is limited")

    if last_range > average_range * 2.2:
        return Analysis("NO TRADE", 0, reasons, "Volatility spike detected—wait for calmer structure.")
    if score >= 3:
        return Analysis("BULLISH SETUP", 70, reasons, "Observation only; wait for your own candle confirmation.")
    if score <= -3:
        return Analysis("BEARISH SETUP", 70, reasons, "Observation only; wait for your own candle confirmation.")
    return Analysis("NO TRADE", 0, reasons, "Signals are mixed or weak—capital protection first.")
