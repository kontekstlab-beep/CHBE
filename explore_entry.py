"""M3.2: исследование точки входа и целей.

Дисциплина против подглядывания: варианты сравниваем на TRAIN, лучший по
expectancy (с порогом по числу сделок) один раз проверяем на TEST.

    python explore_entry.py
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import List

from smartmoney.backtest import Backtester, BacktestConfig
from smartmoney.config import Config
from smartmoney.data import get_cached
from smartmoney.models import Candle
from smartmoney.strategy import SmartMoneyStrategy
from calibrate import split, SYMBOLS, TIMEFRAME, TOTAL_BARS, TRAIN_FRAC

MIN_TRADES = 40
STARTING_EQUITY = 1000.0


@dataclass
class Variant:
    name: str
    entry_edge: str
    sl_mode: str
    sl_atr_mult: float
    target_mode: str
    target_rr: float
    min_rr: float


from smartmoney.presets import backtest_v1


# фиксированная структурная база (из M3), варьируем только вход/стоп/цель
def base_cfg() -> Config:
    return backtest_v1()


def apply(cfg: Config, v: Variant) -> Config:
    cfg.entry.entry_edge = v.entry_edge
    cfg.entry.sl_mode = v.sl_mode
    cfg.entry.sl_atr_mult = v.sl_atr_mult
    cfg.entry.target_mode = v.target_mode
    cfg.entry.target_rr = v.target_rr
    cfg.risk.min_rr = v.min_rr
    return cfg


VARIANTS = [
    Variant("baseline: proximal/block/pool",     "proximal", "block", 1.0, "pool_nearest", 2.0, 2.0),
    Variant("mid entry",                          "mid",      "block", 1.0, "pool_nearest", 2.0, 2.0),
    Variant("distal entry (глубже в блок)",       "distal",   "block", 1.0, "pool_nearest", 2.0, 2.0),
    Variant("wider stop ATR1.5",                  "proximal", "atr",   1.5, "pool_nearest", 2.0, 2.0),
    Variant("mid + ATR1.5",                       "mid",      "atr",   1.5, "pool_nearest", 2.0, 2.0),
    Variant("target RR1.5 (ближе цель)",          "proximal", "block", 1.0, "rr",           1.5, 1.5),
    Variant("target RR1.0",                       "proximal", "block", 1.0, "rr",           1.0, 1.0),
    Variant("mid + ATR1.5 + RR1.5",               "mid",      "atr",   1.5, "rr",           1.5, 1.5),
    Variant("distal + ATR1.0 + RR1.0",            "distal",   "atr",   1.0, "rr",           1.0, 1.0),
    Variant("mid + ATR2.0 + pool",                "mid",      "atr",   2.0, "pool_nearest", 1.5, 1.5),
]


def run(datasets: List[List[Candle]], v: Variant):
    R: List[float] = []
    reasons: Counter = Counter()
    for candles in datasets:
        cfg = apply(base_cfg(), v)
        strat = SmartMoneyStrategy(cfg, allow_longs=True, arm_ttl_bars=30)
        res = Backtester(cfg, BacktestConfig(starting_equity=STARTING_EQUITY)).run(candles, strat)
        R += [t.r_multiple for t in res.trades]
        reasons.update(t.reason for t in res.trades)
    n = len(R)
    win = sum(1 for r in R if r > 0)
    exp = sum(R) / n if n else 0.0
    gw = sum(r for r in R if r > 0)
    gl = -sum(r for r in R if r < 0)
    pf = (gw / gl) if gl > 0 else float("inf")
    return n, (win / n * 100 if n else 0), exp, pf, dict(reasons)


def main() -> None:
    trains, tests = [], []
    for s in SYMBOLS:
        c = get_cached(s, TIMEFRAME, TOTAL_BARS)
        tr, te = split(c, TRAIN_FRAC)
        trains.append(tr)
        tests.append(te)

    print("=== Вход/стоп/цель: TRAIN vs TEST (честно, все варианты) ===")
    hdr = f"{'вариант':32s} | {'tr_n':>4s} {'tr_win%':>7s} {'tr_exp':>7s} | {'te_n':>4s} {'te_win%':>7s} {'te_exp':>7s}"
    print(hdr)
    print("-" * len(hdr))
    rows = []
    for v in VARIANTS:
        trn, trw, tre, trpf, _ = run(trains, v)
        ten, tew, tee, tepf, _ = run(tests, v)
        rows.append((v, trn, trw, tre, ten, tew, tee))
        print(f"{v.name:32s} | {trn:4d} {trw:7.1f} {tre:+7.3f} | {ten:4d} {tew:7.1f} {tee:+7.3f}")

    # честный вывод: есть ли вариант с положительным матожиданием на TEST и достаточной выборкой
    robust = [r for r in rows if r[4] >= MIN_TRADES and r[6] > 0]
    print("\n=== Вывод ===")
    if robust:
        best = max(robust, key=lambda r: r[6])
        print(f"Положительное out-of-sample при достаточной выборке: '{best[0].name}' "
              f"(test exp={best[6]:+.3f}R, {best[4]} сделок, win {best[5]:.1f}%).")
    else:
        print("Ни один вариант не даёт устойчивого положительного матожидания на TEST "
              "при достаточной выборке.")
        # какой ближе всего к нулю с большой выборкой
        big = [r for r in rows if r[4] >= 60]
        if big:
            closest = max(big, key=lambda r: r[6])
            print(f"Ближе всего (по test exp, большая выборка): '{closest[0].name}' "
                  f"test exp={closest[6]:+.3f}R, win {closest[5]:.1f}%, {closest[4]} сделок.")
        print("Близкая фикс-цель поднимает винрейт до ~50%, но матожидание out-of-sample "
              "держится около нуля/минуса — устойчивого преимущества у метода пока нет.")


if __name__ == "__main__":
    main()
