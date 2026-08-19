"""Структура рынка: свинги (пивоты), ATR, тренд, слом структуры (BOS).

Все функции работают на закрытых свечах и НЕ заглядывают в будущее сверх
того, что нужно для подтверждения пивота (pivot_strength баров справа).
"""
from __future__ import annotations

from typing import List, Optional

from .config import StructureConfig
from .models import BOS, Candle, Swing, SwingType, Trend


def find_swings(candles: List[Candle], strength: int) -> List[Swing]:
    """Пивоты: экстремум строго больше/меньше `strength` баров с каждой стороны.

    Свинг подтверждается на баре (index + strength) — с этого момента он
    считается известным (защита от look-ahead).
    """
    swings: List[Swing] = []
    n = len(candles)
    for i in range(strength, n - strength):
        window = candles[i - strength:i + strength + 1]
        c = candles[i]
        is_high = all(c.high > w.high for w in window if w.index != i)
        is_low = all(c.low < w.low for w in window if w.index != i)
        if is_high:
            swings.append(Swing(SwingType.HIGH, c.index, c.high, c.index + strength))
        elif is_low:
            swings.append(Swing(SwingType.LOW, c.index, c.low, c.index + strength))
    return swings


def atr(candles: List[Candle], period: int) -> List[float]:
    """ATR (Wilder упрощённо, SMA от true range). Возвращает список длиной n.

    Первые `period` значений — накопительное среднее; корректно для нашей цели.
    """
    n = len(candles)
    out = [0.0] * n
    trs: List[float] = []
    prev_close: Optional[float] = None
    for i, c in enumerate(candles):
        if prev_close is None:
            tr = c.high - c.low
        else:
            tr = max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close))
        trs.append(tr)
        window = trs[max(0, i - period + 1):i + 1]
        out[i] = sum(window) / len(window)
        prev_close = c.close
    return out


def _last_swings(swings: List[Swing], stype: SwingType, upto_index: int, count: int) -> List[Swing]:
    """Последние `count` свингов типа `stype`, подтверждённых не позже upto_index."""
    filtered = [s for s in swings if s.type == stype and s.confirmed_at <= upto_index]
    return filtered[-count:]


def classify_trend(swings: List[Swing], upto_index: int, cfg: StructureConfig) -> Trend:
    """Тренд по HH/HL/LH/LL на основе последних двух хаёв и лоёв."""
    highs = _last_swings(swings, SwingType.HIGH, upto_index, 2)
    lows = _last_swings(swings, SwingType.LOW, upto_index, 2)
    if len(highs) < 2 or len(lows) < 2:
        return Trend.RANGE
    lower_highs = highs[1].price < highs[0].price
    lower_lows = lows[1].price < lows[0].price
    higher_highs = highs[1].price > highs[0].price
    higher_lows = lows[1].price > lows[0].price
    if lower_highs and lower_lows:
        return Trend.DOWN
    if higher_highs and higher_lows:
        return Trend.UP
    return Trend.RANGE


def detect_bos(
    candles: List[Candle],
    swings: List[Swing],
    at_index: int,
    direction: Trend,
) -> Optional[BOS]:
    """Слом структуры на баре `at_index` в заданном направлении.

    BOS вниз: close бара ниже последнего swing low (закрытие ТЕЛОМ, не шпилькой).
    BOS вверх: close бара выше последнего swing high.
    Прокол хвостом без закрытия за уровнем = сбор ликвидности, не BOS.
    """
    c = candles[at_index]
    if direction == Trend.DOWN:
        lows = _last_swings(swings, SwingType.LOW, at_index - 1, 1)
        if not lows:
            return None
        level = lows[0].price
        if c.close < level:
            ob_idx = _find_ob_candle(candles, at_index, Trend.DOWN)
            return BOS(Trend.DOWN, level, at_index, ob_idx)
    elif direction == Trend.UP:
        highs = _last_swings(swings, SwingType.HIGH, at_index - 1, 1)
        if not highs:
            return None
        level = highs[0].price
        if c.close > level:
            ob_idx = _find_ob_candle(candles, at_index, Trend.UP)
            return BOS(Trend.UP, level, at_index, ob_idx)
    return None


def is_liquidity_grab(candles: List[Candle], swings: List[Swing], at_index: int, direction: Trend) -> bool:
    """Хвост вышел за уровень, но закрытие вернулось внутрь = сбор ликвидности."""
    c = candles[at_index]
    if direction == Trend.DOWN:
        lows = _last_swings(swings, SwingType.LOW, at_index - 1, 1)
        if not lows:
            return False
        return c.low < lows[0].price <= c.close
    else:
        highs = _last_swings(swings, SwingType.HIGH, at_index - 1, 1)
        if not highs:
            return False
        return c.high > highs[0].price >= c.close


def _find_ob_candle(candles: List[Candle], bos_index: int, direction: Trend) -> int:
    """Свеча-блок, вызвавшая слом: последняя противоположная свеча перед импульсом.

    Для BOS вниз — последняя бычья свеча перед серией медвежьих, приведших к слому.
    """
    i = bos_index
    if direction == Trend.DOWN:
        while i > 0 and candles[i].is_bear:
            i -= 1
        return i  # первая бычья (или разворотная) свеча слева от импульса
    else:
        while i > 0 and candles[i].is_bull:
            i -= 1
        return i
