"""ОДНОРАЗОВАЯ финальная проверка гипотезы на свежем HOLDOUT-наборе.

  ⚠️  ЗАПУСКАТЬ ТОЛЬКО КОГДА ГИПОТЕЗА ПОЛНОСТЬЮ ЗАМОРОЖЕНА.
  ⚠️  Каждый запуск «тратит» независимость holdout. Не подбирай параметры по нему.

Использование:
    python validate_holdout.py                 # проверяет пресет mtf_1d_v1
    python validate_holdout.py <preset_name>   # любой пресет из smartmoney.presets

Конфиг берётся как есть (никакого тюнинга). Печатает пул + разбивку по монетам.
"""
from __future__ import annotations

import sys
from typing import List

from smartmoney.backtest import Backtester, BacktestConfig
from smartmoney.data import _TF_MS, get_cached
from smartmoney.datasets import HOLDOUT, HTF, HTF_BARS, LTF, LTF_BARS
from smartmoney.mtf import MultiTFStrategy
from smartmoney import presets


def stats(R: List[float]):
    n = len(R)
    exp = sum(R) / n if n else 0.0
    wr = sum(1 for r in R if r > 0) / n * 100 if n else 0.0
    gw = sum(r for r in R if r > 0)
    gl = -sum(r for r in R if r < 0)
    pf = gw / gl if gl > 0 else float("inf")
    return n, wr, exp, pf


def main(argv: List[str]) -> None:
    preset_name = argv[0] if argv else "mtf_1d_v1"
    cfg_factory = getattr(presets, preset_name)

    print("=" * 60)
    print("  ФИНАЛЬНАЯ HOLDOUT-ПРОВЕРКА (одноразовая!)  пресет:", preset_name)
    print("=" * 60)
    print(f"{'монета':11s} {'сделок':>6s} {'win%':>6s} {'exp,R':>7s} {'pf':>5s}")
    print("-" * 40)
    allR: List[float] = []
    pos = 0
    for s in HOLDOUT:
        ltf = get_cached(s, LTF, LTF_BARS)
        htf = get_cached(s, HTF, HTF_BARS)
        st = MultiTFStrategy(htf, _TF_MS[HTF], _TF_MS[LTF], cfg_factory(),
                             allow_longs=True, arm_ttl_bars=30)
        R = [t.r_multiple for t in Backtester(cfg_factory(), BacktestConfig()).run(ltf, st).trades]
        allR += R
        n, wr, exp, pf = stats(R)
        if exp > 0:
            pos += 1
        pfs = "inf" if pf == float("inf") else f"{pf:.2f}"
        print(f"{s:11s} {n:6d} {wr:6.1f} {exp:+7.3f} {pfs:>5s}")

    n, wr, exp, pf = stats(allR)
    pfs = "inf" if pf == float("inf") else f"{pf:.2f}"
    print("-" * 40)
    print(f"{'ПУЛ':11s} {n:6d} {wr:6.1f} {exp:+7.3f} {pfs:>5s}   монет+={pos}/{len(HOLDOUT)}")
    print("\nНапоминание: это одноразовый результат. Дальнейший тюнинг под holdout запрещён.")


if __name__ == "__main__":
    main(sys.argv[1:])
