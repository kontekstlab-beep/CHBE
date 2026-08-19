from smartmoney import synth
from smartmoney.config import StructureConfig
from smartmoney.models import SwingType, Trend
from smartmoney.structure import (atr, classify_trend, detect_bos, find_swings,
                                   is_liquidity_grab)


def test_find_swings_detects_high_and_low():
    candles = synth.zigzag_down()
    swings = find_swings(candles, strength=1)
    highs = [s for s in swings if s.type == SwingType.HIGH]
    lows = [s for s in swings if s.type == SwingType.LOW]
    assert highs and lows
    # первый заметный хай около бара 1 (high 105)
    assert any(s.index == 1 for s in highs)


def test_swing_confirmed_after_strength_bars():
    candles = synth.zigzag_down()
    strength = 2
    swings = find_swings(candles, strength=strength)
    for s in swings:
        assert s.confirmed_at == s.index + strength


def test_atr_positive():
    candles = synth.zigzag_down()
    a = atr(candles, period=3)
    assert len(a) == len(candles)
    assert all(x > 0 for x in a[1:])


def test_trend_down():
    candles = synth.zigzag_down()
    swings = find_swings(candles, strength=1)
    trend = classify_trend(swings, upto_index=len(candles) - 1, cfg=StructureConfig())
    assert trend == Trend.DOWN


def test_bos_down_requires_body_close():
    candles = synth.zigzag_down()
    swings = find_swings(candles, strength=1)
    # бар 6 закрывается на 91, ниже swing low 94 -> BOS вниз
    bos = detect_bos(candles, swings, at_index=6, direction=Trend.DOWN)
    assert bos is not None
    assert bos.direction == Trend.DOWN
    assert bos.break_level <= 99


def test_no_bos_without_swing():
    candles = synth.zigzag_down()
    swings = find_swings(candles, strength=1)
    bos = detect_bos(candles, swings, at_index=0, direction=Trend.DOWN)
    assert bos is None
