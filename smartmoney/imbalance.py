"""Имбаланс / Fair Value Gap (FVG) — «пустоты ликвидности».

Bearish FVG (тройка i-1, i, i+1): low[i-1] > high[i+1] -> зона [high[i+1], low[i-1]].
Bullish FVG: high[i-1] < low[i+1] -> зона [high[i-1], low[i+1]].
Перекрытие достаточно на 50% (проход цены за mid).
"""
from __future__ import annotations

from typing import List

from .models import FVG, Candle


def find_fvgs(candles: List[Candle]) -> List[FVG]:
    out: List[FVG] = []
    for i in range(1, len(candles) - 1):
        prev, nxt = candles[i - 1], candles[i + 1]
        # медвежий разрыв
        if prev.low > nxt.high:
            out.append(FVG(True, nxt.high, prev.low, i, i + 1))
        # бычий разрыв
        elif prev.high < nxt.low:
            out.append(FVG(False, prev.high, nxt.low, i, i + 1))
    return out


def is_filled(fvg: FVG, candles: List[Candle], upto_index: int) -> bool:
    """Перекрыт ли FVG на >=50% к бару upto_index (цена прошла за середину)."""
    for c in candles[fvg.confirmed_at + 1:upto_index + 1]:
        if fvg.bearish and c.high >= fvg.mid:
            return True
        if not fvg.bearish and c.low <= fvg.mid:
            return True
    return False
