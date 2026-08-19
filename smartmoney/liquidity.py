"""Пулы ликвидности: BSL (над равными хаями) и SSL (под равными лоями).

Кластеризуем близкие свинги одного типа (двойные/тройные вершины/дна)
с толерансом equal_level_tol (доля от цены).
"""
from __future__ import annotations

from typing import List

from .config import LiquidityConfig
from .models import Candle, LiquidityPool, PoolType, Swing, SwingType


def find_pools(swings: List[Swing], cfg: LiquidityConfig) -> List[LiquidityPool]:
    pools: List[LiquidityPool] = []
    pools += _cluster(sorted([s for s in swings if s.type == SwingType.HIGH], key=lambda s: s.index),
                      PoolType.BSL, cfg)
    pools += _cluster(sorted([s for s in swings if s.type == SwingType.LOW], key=lambda s: s.index),
                      PoolType.SSL, cfg)
    return pools


def _cluster(swings: List[Swing], ptype: PoolType, cfg: LiquidityConfig) -> List[LiquidityPool]:
    pools: List[LiquidityPool] = []
    used = [False] * len(swings)
    for i, s in enumerate(swings):
        if used[i]:
            continue
        group = [s]
        used[i] = True
        for j in range(i + 1, len(swings)):
            if used[j]:
                continue
            if abs(swings[j].price - s.price) <= s.price * cfg.equal_level_tol:
                group.append(swings[j])
                used[j] = True
        if len(group) >= cfg.min_touches:
            price = max(g.price for g in group) if ptype == PoolType.BSL else min(g.price for g in group)
            pools.append(LiquidityPool(
                type=ptype,
                price=price,
                touches=len(group),
                first_index=min(g.index for g in group),
                last_index=max(g.index for g in group),
            ))
    return pools


def mark_swept(pools: List[LiquidityPool], candles: List[Candle],
               upto: int | None = None) -> List[LiquidityPool]:
    """Помечает пул снятым, если после его формирования цена вышла за уровень.

    `upto` (абсолютный индекс) ограничивает просмотр — снятие проверяется только
    по барам <= upto (защита от look-ahead в бэктесте). None = вся серия.
    """
    end = len(candles) if upto is None else upto + 1
    out: List[LiquidityPool] = []
    for p in pools:
        swept_at = None
        for c in candles[p.last_index + 1:end]:
            if p.type == PoolType.BSL and c.high > p.price:
                swept_at = c.index
                break
            if p.type == PoolType.SSL and c.low < p.price:
                swept_at = c.index
                break
        out.append(LiquidityPool(p.type, p.price, p.touches, p.first_index,
                                 p.last_index, swept_at is not None, swept_at))
    return out
