"""Демо: прогоняет примитивы по синтетической сцене и печатает разметку.

Запуск:  python demo.py
"""
from smartmoney import synth
from smartmoney.config import Config
from smartmoney.imbalance import find_fvgs
from smartmoney.liquidity import find_pools, mark_swept
from smartmoney.orderblocks import find_order_blocks, update_mitigation
from smartmoney.structure import classify_trend, detect_bos, find_swings
from smartmoney.models import Trend


def main() -> None:
    cfg = Config()
    # короткая демо-сцена -> берём чувствительный pivot_strength=1
    cfg.structure.pivot_strength = 1
    cfg.orderblock.atr_period = 3
    cfg.orderblock.displacement_atr = 1.0
    candles = synth.strong_bear_ob_scene()

    swings = find_swings(candles, cfg.structure.pivot_strength)
    trend = classify_trend(swings, len(candles) - 1, cfg.structure)
    fvgs = find_fvgs(candles)
    pools = mark_swept(find_pools(swings, cfg.liquidity), candles)
    blocks = find_order_blocks(candles, swings, cfg.orderblock)
    update_mitigation(blocks, candles)

    print("=== Демо разметки (медвежья сцена) ===")
    print(f"Свечей: {len(candles)}  |  Тренд: {trend.value}")
    print(f"\nСвинги ({len(swings)}):")
    for s in swings:
        print(f"  {s.type.value:5s} @bar{s.index} price={s.price:.1f} confirmed@{s.confirmed_at}")

    print(f"\nПулы ликвидности ({len(pools)}):")
    for p in pools:
        print(f"  {p.type.value.upper()} price={p.price:.1f} touches={p.touches} swept={p.swept}")

    print(f"\nFVG ({len(fvgs)}):")
    for f in fvgs:
        kind = "bear" if f.bearish else "bull"
        print(f"  {kind} zone=[{f.low:.1f}, {f.high:.1f}] mid={f.mid:.1f} @bar{f.index}")

    print(f"\nБлоки заказов ({len(blocks)}):")
    for b in sorted(blocks, key=lambda x: -x.score):
        flags = f"swept={int(b.swept_liquidity)} engulf={int(b.engulfed)} fvg={int(b.has_fvg)} bos={int(b.caused_bos)}"
        print(f"  {b.side.value:5s} @bar{b.index} zone=[{b.low:.1f},{b.high:.1f}] "
              f"score={b.score} strong={b.is_strong} {flags} invalidated@{b.invalidated_at}")

    print("\nBOS-проверка по барам:")
    for i in range(1, len(candles)):
        bos = detect_bos(candles, swings, i, Trend.DOWN)
        if bos:
            print(f"  bar{i}: BOS вниз, пробит уровень {bos.break_level:.1f}, "
                  f"OB-свеча @bar{bos.ob_candle_index}")


if __name__ == "__main__":
    main()
