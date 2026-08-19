"""Генератор синтетических свечных рядов для тестов и демо.

Позволяет собирать ряд из явных OHLC-кортежей — так тесты остаются
детерминированными и человекочитаемыми.
"""
from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

from .models import Candle

OHLC = Tuple[float, float, float, float]  # open, high, low, close


def make(candles: Sequence[OHLC], start_ts: int = 0, step: int = 60_000) -> List[Candle]:
    out: List[Candle] = []
    for i, (o, h, l, c) in enumerate(candles):
        out.append(Candle(index=i, ts=start_ts + i * step, open=o, high=h, low=l, close=c, volume=1.0))
    return out


def zigzag_down() -> List[Candle]:
    """Нисходящий ряд с чёткими LH/LL (строгие пивоты при strength=1).

    Хаи: 110 (bar1) -> 108 (bar5) = LH.  Лои: 98 (bar3) -> 92 (bar6) = LL.
    Бар 6 закрывается ниже swing low 98 -> BOS вниз.
    """
    seq: List[OHLC] = [
        (100, 103, 99, 102),   # 0
        (102, 110, 101, 109),  # 1 swing high 110
        (109, 109, 104, 105),  # 2
        (105, 106, 98, 99),    # 3 swing low 98
        (99, 107, 99, 106),    # 4 коррекция вверх
        (106, 108, 103, 104),  # 5 lower high 108
        (104, 105, 92, 93),    # 6 импульс вниз: close 93 < swing low 98 -> BOS
        (93, 95, 93, 94),      # 7 (low 93 > 92, чтобы bar6 остался пивот-лоу)
        (94, 96, 91, 92),      # 8
    ]
    return make(seq)


def strong_bear_ob_scene() -> List[Candle]:
    """Сцена, дающая СИЛЬНЫЙ медвежий OB (score=4) на bar5.

    bar1 swing high 112, bar3 swing low 96. bar5 — бычья свеча-блок, чей хай (115)
    снимает ликвидность над 112; импульс bar6-8 поглощает блок, оставляет bearish FVG
    и закрывается ниже swing low 96 (BOS).
    """
    seq: List[OHLC] = [
        (100, 103, 99, 102),   # 0
        (102, 112, 101, 111),  # 1 swing high 112
        (111, 111, 105, 106),  # 2
        (106, 107, 96, 97),    # 3 swing low 96
        (97, 100, 97, 99),     # 4
        (99, 115, 99, 114),    # 5 бычья свеча-блок: хай 115 снимает 112 (sweep)
        (100, 101, 90, 91),    # 6 импульс вниз: close 91 < swing low 96 -> BOS, поглощение
        (91, 94, 84, 85),      # 7 high 94 < 99 -> bearish FVG (5,6,7)
        (85, 89, 83, 87),      # 8
    ]
    return make(seq)


def downtrend_series(cycles: int = 8, drop: float = 12.0, start: float = 300.0) -> List[Candle]:
    """Длинный нисходящий ряд из повторяющихся циклов «сетапа»:
    ралли в медвежий OB (снятие хая) -> импульс вниз с FVG и BOS -> двойное дно (SSL).

    Каждый цикл смещён вниз на `drop`, что даёт устойчивый нисходящий тренд и
    несколько торгуемых сетапов для интеграционного бэктеста.
    """
    seq: List[OHLC] = []
    base = start
    for _ in range(cycles):
        # относительная форма цикла (12 баров)
        pattern = [
            (base + 0, base + 3, base - 1, base + 2),      # 0
            (base + 2, base + 12, base + 1, base + 11),    # 1 swing high (локальный)
            (base + 11, base + 11, base + 5, base + 6),    # 2
            (base + 6, base + 7, base - 4, base - 3),      # 3 swing low
            (base - 3, base + 0, base - 3, base - 1),      # 4 коррекция вверх (в OB зону)
            (base - 1, base + 15, base - 1, base + 14),    # 5 бычья свеча-блок (снимает хай 12)
            (base + 0, base + 1, base - 10, base - 9),     # 6 импульс вниз: BOS ниже swing low
            (base - 9, base - 6, base - 16, base - 15),    # 7 FVG + продолжение
            (base - 15, base - 12, base - 20, base - 19),  # 8 двойное дно (SSL) низ
            (base - 19, base - 14, base - 20, base - 15),  # 9 равный лой (SSL)
            (base - 15, base - 10, base - 17, base - 12),  # 10
            (base - 12, base - 8, base - 16, base - 14),   # 11
        ]
        seq.extend(pattern)
        base -= drop
    return make(seq)


def bearish_ob_scene() -> List[Candle]:
    """Сцена с чётким медвежьим OB: бычья свеча снимает хай, затем импульс вниз с FVG и BOS."""
    seq: List[OHLC] = [
        (100, 101, 99, 100),   # 0
        (100, 106, 100, 105),  # 1 swing high 106
        (105, 105, 101, 102),  # 2
        (102, 103, 97, 98),    # 3 swing low 97
        (98, 100, 97, 99),     # 4
        (99, 108, 99, 107),    # 5 БЫЧЬЯ свеча-блок: снимает хай 106 (sweep)
        (100, 100, 92, 93),    # 6 импульс вниз, поглощает блок, FVG (low[5]=99 > high[7]?)
        (92, 94, 85, 86),      # 7 продолжение вниз, BOS ниже 97
        (86, 90, 84, 88),      # 8
    ]
    return make(seq)
