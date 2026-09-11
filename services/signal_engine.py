from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev

from services.market_data import CandleSeries


@dataclass(frozen=True)
class Analysis:
    label: str
    market_state: str
    quality: str
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


def macd_histogram(values: list[float]) -> float:
    macd_line = [ema(values[: index + 1], 12) - ema(values[: index + 1], 26) for index in range(25, len(values))]
    return macd_line[-1] - ema(macd_line, 9)


def analyse(series: CandleSeries) -> Analysis:
    closes = [candle.close for candle in series.candles]
    last = series.candles[-1]
    e9, e21 = ema(closes[-60:], 9), ema(closes[-60:], 21)
    e50 = ema(closes[-80:], 50)
    e200 = ema(closes, 200) if len(closes) >= 200 else e50
    current_rsi = rsi(closes)
    histogram = macd_histogram(closes[-60:])
    ranges = [candle.high - candle.low for candle in series.candles[-14:]]
    avg_range, last_range = mean(ranges), last.high - last.low
    body = abs(last.close - last.open)
    recent = closes[-20:]
    middle, deviation = mean(recent), pstdev(recent)
    upper, lower = middle + 2 * deviation, middle - 2 * deviation
    reasons: list[str] = []

    trend_up = e9 > e21 > e50 and last.close > e50
    trend_down = e9 < e21 < e50 and last.close < e50
    if trend_up and e50 >= e200:
        market_state, direction = "UP", 1
        reasons.append("EMA 9/21/50 alignment is upward")
    elif trend_down and e50 <= e200:
        market_state, direction = "DOWN", -1
        reasons.append("EMA 9/21/50 alignment is downward")
    elif abs(e9 - e21) <= avg_range * 0.15:
        market_state, direction = "RANGE", 0
        reasons.append("fast EMAs are compressed—range conditions")
    else:
        market_state, direction = "TRANSITION", 0
        reasons.append("trend filters are not aligned")

    if last_range > avg_range * 2.1:
        return Analysis("WICKET ALERT — NO TRADE", market_state, "Blocked", reasons, "Volatility spike detected; wait for a close and retest.")
    if last.close >= upper or last.close <= lower or current_rsi >= 72 or current_rsi <= 28:
        return Analysis("WICKET ALERT — NO TRADE", market_state, "Blocked", reasons, "Price is stretched; avoid late/FOMO entries.")
    if direction == 0:
        return Analysis("NO TRADE", market_state, "Weak", reasons, "Wait for structure, zone and candle trigger to align.")

    score = 1
    if direction == 1 and 52 <= current_rsi <= 68:
        score += 1
        reasons.append(f"RSI supports buyers at {current_rsi:.0f}")
    elif direction == -1 and 32 <= current_rsi <= 48:
        score += 1
        reasons.append(f"RSI supports sellers at {current_rsi:.0f}")
    else:
        reasons.append(f"RSI is neutral at {current_rsi:.0f}")
    if (direction == 1 and histogram > 0) or (direction == -1 and histogram < 0):
        score += 1
        reasons.append("MACD momentum agrees with the trend")
    if ((direction == 1 and last.close > last.open) or (direction == -1 and last.close < last.open)) and body >= avg_range * 0.30:
        score += 1
        reasons.append("latest candle provides momentum confirmation")
    if score < 3:
        return Analysis("NO TRADE", market_state, "Weak", reasons, "Trend exists, but confirmation is incomplete—wait.")
    label = "POWERPLAY — BULLISH OBSERVATION" if direction == 1 else "POWERPLAY — BEARISH OBSERVATION"
    quality = "Selected" if score == 4 else "Qualified"
    return Analysis(label, market_state, quality, reasons, "Observation only: confirm your own zone, candle close and timing before acting.")
