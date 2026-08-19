from smartmoney import synth
from smartmoney.config import LiquidityConfig, OrderBlockConfig
from smartmoney.imbalance import find_fvgs, is_filled
from smartmoney.liquidity import find_pools, mark_swept
from smartmoney.models import PoolType, Side
from smartmoney.orderblocks import (find_order_blocks, strong_blocks,
                                    update_mitigation)
from smartmoney.structure import find_swings


def test_fvg_detection():
    candles = synth.bearish_ob_scene()
    fvgs = find_fvgs(candles)
    assert any(f.bearish for f in fvgs), "должен найтись хотя бы один медвежий FVG"


def test_fvg_zone_ordering():
    candles = synth.bearish_ob_scene()
    for f in find_fvgs(candles):
        assert f.low < f.high
        assert f.low < f.mid < f.high


def test_liquidity_pool_double_bottom():
    # два почти равных лоя (строгие пивоты) -> SSL пул
    seq = [
        (100, 101, 97, 100),
        (100, 100, 95, 99),   # low 95 (строгий минимум: соседи 97 и 98)
        (99, 100, 98, 99),    # low 98
        (99, 100, 95, 99),    # low 95 (равный, строгий минимум: соседи 98 и 97)
        (99, 101, 97, 100),
    ]
    candles = synth.make(seq)
    swings = find_swings(candles, strength=1)
    pools = find_pools(swings, LiquidityConfig(equal_level_tol=0.02))
    assert any(p.type == PoolType.SSL and p.touches >= 2 for p in pools)


def test_pool_marked_swept():
    seq = [
        (100, 101, 97, 100),
        (100, 100, 95, 99),   # low 95 (строгий минимум)
        (99, 100, 98, 99),    # low 98
        (99, 100, 95, 99),    # low 95 (равный)
        (99, 101, 97, 100),
        (100, 101, 90, 92),   # пробили низ 95 -> sweep SSL
    ]
    candles = synth.make(seq)
    swings = find_swings(candles, strength=1)
    pools = mark_swept(find_pools(swings, LiquidityConfig(equal_level_tol=0.02)), candles)
    ssl = [p for p in pools if p.type == PoolType.SSL]
    assert ssl and any(p.swept for p in ssl)


def test_order_block_detected_and_scored():
    candles = synth.bearish_ob_scene()
    swings = find_swings(candles, strength=1)
    blocks = find_order_blocks(candles, swings, OrderBlockConfig(atr_period=3, displacement_atr=1.0))
    bear = [b for b in blocks if b.side == Side.SHORT]
    assert bear, "должен найтись медвежий OB"
    best = max(bear, key=lambda b: b.score)
    assert best.score >= 2  # как минимум пара условий выполнена
    assert best.high >= best.low


def test_strong_order_block_score_four():
    candles = synth.strong_bear_ob_scene()
    swings = find_swings(candles, strength=1)
    cfg = OrderBlockConfig(atr_period=3, displacement_atr=1.0)
    blocks = find_order_blocks(candles, swings, cfg)
    bear = [b for b in blocks if b.side == Side.SHORT]
    best = max(bear, key=lambda b: b.score)
    assert best.index == 5
    assert best.score == 4 and best.is_strong
    strong = strong_blocks(blocks, cfg)
    assert any(b.index == 5 for b in strong)


def test_order_block_invalidation():
    candles = synth.bearish_ob_scene()
    swings = find_swings(candles, strength=1)
    blocks = find_order_blocks(candles, swings, OrderBlockConfig(atr_period=3, displacement_atr=1.0))
    update_mitigation(blocks, candles)
    # score фильтр не должен падать
    strong = strong_blocks(blocks, OrderBlockConfig(atr_period=3, min_ob_score=3))
    assert isinstance(strong, list)
