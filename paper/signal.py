"""Расчёт сигнала mean-reversion — общий код с бэктестом (та же формула z).

Работает на ЗАКРЫТЫХ барах. Чистые функции — легко тестировать.
"""
from __future__ import annotations

from statistics import pstdev
from typing import List, Optional


def sma(closes: List[float], n: int) -> Optional[float]:
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n


def zscore(closes: List[float], n: int) -> Optional[float]:
    """z последнего close относительно SMA(n)."""
    if len(closes) < n:
        return None
    window = closes[-n:]
    m = sum(window) / n
    sd = pstdev(window) or 1e-9
    return (window[-1] - m) / sd


def entry_signal(closes: List[float], n: int, entry_z: float) -> bool:
    z = zscore(closes, n)
    return z is not None and z < entry_z


def exit_signal(closes: List[float], n: int, exit_z: float,
                bars_held: int, max_hold: int,
                entry_price: float, last_low: float, stop_frac: float) -> Optional[str]:
    """Возвращает причину выхода ('stop'|'reversion'|'time') или None."""
    if stop_frac > 0 and last_low <= entry_price * (1 - stop_frac):
        return "stop"
    z = zscore(closes, n)
    if z is not None and z >= exit_z:
        return "reversion"
    if bars_held >= max_hold:
        return "time"
    return None
