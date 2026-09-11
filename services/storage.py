from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "ultron.sqlite3"


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY, alerts INTEGER NOT NULL DEFAULT 0)")
    connection.execute("CREATE TABLE IF NOT EXISTS watchlist (chat_id INTEGER NOT NULL, symbol TEXT NOT NULL, PRIMARY KEY(chat_id, symbol))")
    return connection


def ensure_user(chat_id: int) -> None:
    with _connection() as db:
        db.execute("INSERT OR IGNORE INTO users(chat_id) VALUES(?)", (chat_id,))


def set_alerts(chat_id: int, enabled: bool) -> None:
    ensure_user(chat_id)
    with _connection() as db:
        db.execute("UPDATE users SET alerts=? WHERE chat_id=?", (int(enabled), chat_id))


def add_watch(chat_id: int, symbol: str) -> None:
    ensure_user(chat_id)
    with _connection() as db:
        db.execute("INSERT OR IGNORE INTO watchlist(chat_id, symbol) VALUES(?, ?)", (chat_id, symbol))


def remove_watch(chat_id: int, symbol: str) -> None:
    with _connection() as db:
        db.execute("DELETE FROM watchlist WHERE chat_id=? AND symbol=?", (chat_id, symbol))


def get_watchlist(chat_id: int) -> list[str]:
    with _connection() as db:
        return [row[0] for row in db.execute("SELECT symbol FROM watchlist WHERE chat_id=? ORDER BY symbol", (chat_id,))]


def alert_subscriptions() -> dict[int, list[str]]:
    with _connection() as db:
        rows = db.execute("SELECT w.chat_id, w.symbol FROM watchlist w JOIN users u ON u.chat_id=w.chat_id WHERE u.alerts=1").fetchall()
    result: dict[int, list[str]] = {}
    for chat_id, symbol in rows:
        result.setdefault(chat_id, []).append(symbol)
    return result
