from __future__ import annotations

import json
import re
from dataclasses import dataclass

from config import PAIRS_FILE


@dataclass(frozen=True)
class Pair:
    symbol: str
    label: str
    category: str
    active: bool


def load_pairs() -> list[Pair]:
    raw = json.loads(PAIRS_FILE.read_text(encoding="utf-8"))
    return [Pair(**item) for item in raw]


def active_pairs() -> list[Pair]:
    return [pair for pair in load_pairs() if pair.active]


def pair_by_symbol(query: str) -> Pair | None:
    normalized = re.sub(r"[^A-Z0-9]", "", query.upper())
    for pair in active_pairs():
        options = {
            re.sub(r"[^A-Z0-9]", "", pair.symbol.upper()),
            re.sub(r"[^A-Z0-9]", "", pair.label.upper()),
        }
        if normalized in options:
            return pair
    return None
