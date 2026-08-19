"""Блоки заказов (Order Blocks) со score силы 0..4.

Медвежий OB: последняя бычья свеча перед импульсом вниз, при условиях:
  1) снятие ликвидности сверху (обновлён ближайший swing high / BSL),
  2) поглощение + дисплейсмент (импульс >= displacement_atr * ATR),
  3) импульс оставил bearish FVG,
  4) импульс закрылся телом ниже предыдущего swing low (BOS).
score = число выполненных условий; strong = 4.
Бычий OB — зеркально.
"""
from __future__ import annotations

from typing import List, Optional

from .config import OrderBlockConfig, StructureConfig
from .imbalance import find_fvgs
from .models import Candle, FVG, OrderBlock, Side, Swing, SwingType, Trend
from .structure import atr


def find_order_blocks(
    candles: List[Candle],
    swings: List[Swing],
    ob_cfg: OrderBlockConfig,
) -> List[OrderBlock]:
    a = atr(candles, ob_cfg.atr_period)
    fvgs = find_fvgs(candles)
    blocks: List[OrderBlock] = []
    n = len(candles)
    look = ob_cfg.impulse_lookahead

    for i in range(1, n - look):
        c = candles[i]
        # --- медвежий OB: бычья свеча перед импульсом вниз ---
        if c.is_bull:
            ob = _try_bear_ob(candles, swings, fvgs, i, look, a[i], ob_cfg)
            if ob is not None:
                blocks.append(ob)
        # --- бычий OB: медвежья свеча перед импульсом вверх ---
        if c.is_bear:
            ob = _try_bull_ob(candles, swings, fvgs, i, look, a[i], ob_cfg)
            if ob is not None:
                blocks.append(ob)
    return blocks


def _prev_swing_price(swings: List[Swing], stype: SwingType, before_index: int) -> Optional[float]:
    cand = [s for s in swings if s.type == stype and s.index < before_index]
    return cand[-1].price if cand else None


def _try_bear_ob(candles, swings, fvgs, i, look, atr_i, cfg) -> Optional[OrderBlock]:
    c = candles[i]
    impulse = candles[i + 1:i + 1 + look]
    if not impulse:
        return None
    # 2) дисплейсмент: суммарный ход вниз >= порог
    move = c.high - min(x.low for x in impulse)
    engulfed = any(x.close < c.body_low for x in impulse)
    displaced = move >= cfg.displacement_atr * atr_i and engulfed
    # 1) снятие ликвидности сверху
    prev_high = _prev_swing_price(swings, SwingType.HIGH, i)
    swept = prev_high is not None and c.high > prev_high
    # 3) FVG в импульсе
    has_fvg = any(f.bearish and i <= f.index <= i + look for f in fvgs)
    # 4) BOS вниз: импульс закрылся ниже предыдущего swing low
    prev_low = _prev_swing_price(swings, SwingType.LOW, i)
    caused_bos = prev_low is not None and any(x.close < prev_low for x in impulse)

    if not (swept or displaced or has_fvg or caused_bos):
        return None
    return OrderBlock(
        side=Side.SHORT, index=i, low=c.low, high=c.high,
        confirmed_at=i + look,
        swept_liquidity=swept, engulfed=displaced, has_fvg=has_fvg, caused_bos=caused_bos,
    )


def _try_bull_ob(candles, swings, fvgs, i, look, atr_i, cfg) -> Optional[OrderBlock]:
    c = candles[i]
    impulse = candles[i + 1:i + 1 + look]
    if not impulse:
        return None
    move = max(x.high for x in impulse) - c.low
    engulfed = any(x.close > c.body_high for x in impulse)
    displaced = move >= cfg.displacement_atr * atr_i and engulfed
    prev_low = _prev_swing_price(swings, SwingType.LOW, i)
    swept = prev_low is not None and c.low < prev_low
    has_fvg = any((not f.bearish) and i <= f.index <= i + look for f in fvgs)
    prev_high = _prev_swing_price(swings, SwingType.HIGH, i)
    caused_bos = prev_high is not None and any(x.close > prev_high for x in impulse)

    if not (swept or displaced or has_fvg or caused_bos):
        return None
    return OrderBlock(
        side=Side.LONG, index=i, low=c.low, high=c.high,
        confirmed_at=i + look,
        swept_liquidity=swept, engulfed=displaced, has_fvg=has_fvg, caused_bos=caused_bos,
    )


def update_mitigation(blocks: List[OrderBlock], candles: List[Candle]) -> None:
    """Проставляет mitigated_at (цена вернулась в зону блока) и invalidated_at
    (закрытие телом сквозь дальнюю границу)."""
    for ob in blocks:
        for c in candles[ob.confirmed_at + 1:]:
            overlaps = c.low <= ob.high and c.high >= ob.low
            if ob.mitigated_at is None and overlaps:
                ob.mitigated_at = c.index
            if ob.side == Side.SHORT and c.close > ob.high:
                ob.invalidated_at = c.index
                break
            if ob.side == Side.LONG and c.close < ob.low:
                ob.invalidated_at = c.index
                break


def strong_blocks(blocks: List[OrderBlock], cfg: OrderBlockConfig) -> List[OrderBlock]:
    return [b for b in blocks if b.score >= cfg.min_ob_score and b.invalidated_at is None]
