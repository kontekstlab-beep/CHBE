"""Загрузка свечей: с Binance (ccxt, опционально) и из CSV.

ccxt импортируется лениво — прототип работает и без него (на синтетике/CSV).
"""
from __future__ import annotations

import csv
import os
import time
from typing import List

from .models import Candle

_TF_MS = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000,
    "1d": 86_400_000, "1w": 604_800_000,
}


def candles_from_ohlcv(rows: List[list]) -> List[Candle]:
    """rows: [[ts, open, high, low, close, volume], ...] (формат ccxt)."""
    out: List[Candle] = []
    for i, r in enumerate(rows):
        ts, o, h, l, c = int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])
        v = float(r[5]) if len(r) > 5 else 0.0
        out.append(Candle(i, ts, o, h, l, c, v))
    return out


def load_csv(path: str) -> List[Candle]:
    """CSV с колонками ts,open,high,low,close[,volume] (с заголовком)."""
    rows: List[list] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append([
                row["ts"], row["open"], row["high"],
                row["low"], row["close"], row.get("volume", 0),
            ])
    return candles_from_ohlcv(rows)


def load_binance(symbol: str = "BTC/USDT", timeframe: str = "1h",
                 limit: int = 1000, since: int | None = None,
                 futures: bool = True) -> List[Candle]:
    """Свечи с Binance через ccxt. Требует `pip install ccxt`.

    Только публичные данные (ключи не нужны). futures=True -> USDT-M perpetual.
    """
    try:
        import ccxt  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Для загрузки с Binance установите ccxt: pip install ccxt") from e

    ex = ccxt.binanceusdm() if futures else ccxt.binance()
    ohlcv = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
    return candles_from_ohlcv(ohlcv)


def load_binance_paged(symbol: str = "BTC/USDT", timeframe: str = "1h",
                       total: int = 4000, futures: bool = True) -> List[Candle]:
    """Пагинированная загрузка >1500 свечей: несколько запросов ccxt с `since`."""
    try:
        import ccxt  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Для загрузки установите ccxt: pip install ccxt") from e

    ex = ccxt.binanceusdm() if futures else ccxt.binance()
    step = _TF_MS.get(timeframe)
    if step is None:
        raise ValueError(f"неизвестный таймфрейм: {timeframe}")
    per_call = 1000  # фактический потолок binanceusdm на один запрос
    now = ex.milliseconds()
    since = now - total * step
    rows: list = []
    while len(rows) < total:
        batch = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=per_call)
        if not batch:
            break
        rows += batch
        new_since = batch[-1][0] + step
        if new_since <= since:          # нет продвижения
            break
        since = new_since
        if batch[-1][0] >= now - step:  # догнали настоящее
            break
        time.sleep(ex.rateLimit / 1000.0)
    # убрать дубли по ts, обрезать до total последних
    seen = {}
    for r in rows:
        seen[int(r[0])] = r
    ordered = [seen[k] for k in sorted(seen)][-total:]
    return candles_from_ohlcv(ordered)


def get_cached(symbol: str, timeframe: str, total: int,
               cache_dir: str = "data", futures: bool = True) -> List[Candle]:
    """Загрузка из CSV-кэша; при отсутствии — скачать с Binance и сохранить."""
    os.makedirs(cache_dir, exist_ok=True)
    safe = symbol.replace("/", "") + f"_{timeframe}_{total}.csv"
    path = os.path.join(cache_dir, safe)
    if os.path.exists(path):
        return load_csv(path)
    candles = load_binance_paged(symbol, timeframe, total, futures)
    save_csv(candles, path)
    return candles


def save_csv(candles: List[Candle], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ts", "open", "high", "low", "close", "volume"])
        for c in candles:
            w.writerow([c.ts, c.open, c.high, c.low, c.close, c.volume])
