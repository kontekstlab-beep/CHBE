"""M3.5: связка 1D->1h + тюнинг HTF-порогов, сравнение с 4h->1h и одно-ТФ.

Метрика — walk-forward по 5 окнам (плюс в скольких окнах).
Тюнинг HTF показан полностью (маленькая сетка) с оговоркой о риске подгонки.

    python explore_mtf_1d.py
"""
from __future__ import annotations

from typing import List

from smartmoney.backtest import Backtester, BacktestConfig
from smartmoney.data import _TF_MS, get_cached
from smartmoney.models import Candle
from smartmoney.mtf import MultiTFStrategy
from smartmoney.presets import backtest_v1, mtf_v1
from smartmoney.strategy import SmartMoneyStrategy
from calibrate import SYMBOLS, TOTAL_BARS

K = 5
LTF = "1h"


def reindex(seq):
    return [Candle(i, c.ts, c.open, c.high, c.low, c.close, c.volume) for i, c in enumerate(seq)]


def stats(R: List[float]):
    n = len(R)
    exp = sum(R) / n if n else 0.0
    wr = sum(1 for r in R if r > 0) / n * 100 if n else 0.0
    gw = sum(r for r in R if r > 0)
    gl = -sum(r for r in R if r < 0)
    pf = gw / gl if gl > 0 else float("inf")
    return n, wr, exp, pf


def mtf_cfg(trend_ps: int, pivot_ps: int, min_score: int):
    cfg = backtest_v1()
    cfg.structure.trend_pivot_strength = trend_ps
    cfg.structure.pivot_strength = pivot_ps
    cfg.structure.confirm_pivot_strength = 1
    cfg.orderblock.min_ob_score = min_score
    return cfg


def main() -> None:
    ltf_all = {s: get_cached(s, LTF, TOTAL_BARS) for s in SYMBOLS}
    htf_4h = {s: get_cached(s, "4h", 1500) for s in SYMBOLS}
    htf_1d = {s: get_cached(s, "1d", 1000) for s in SYMBOLS}

    folds = [[] for _ in range(K)]
    for s in SYMBOLS:
        c = ltf_all[s]
        n = len(c) // K
        for k in range(K):
            folds[k].append((s, reindex(c[k * n:(k + 1) * n])))

    def wf(runner):
        pos = 0
        allR: List[float] = []
        per = []
        for k in range(K):
            R = runner(folds[k])
            allR += R
            _, _, e, _ = stats(R)
            per.append(e)
            if e > 0:
                pos += 1
        n, wr, exp, pf = stats(allR)
        return n, wr, exp, pf, pos, per

    def run_single(fold):
        R = []
        for _, cs in fold:
            st = SmartMoneyStrategy(backtest_v1(), allow_longs=True, arm_ttl_bars=30)
            R += [t.r_multiple for t in Backtester(backtest_v1(), BacktestConfig()).run(cs, st).trades]
        return R

    def make_mtf_runner(htf_map, htf_tf, cfg_factory):
        def runner(fold):
            R = []
            for s, cs in fold:
                cfg = cfg_factory()
                st = MultiTFStrategy(htf_map[s], _TF_MS[htf_tf], _TF_MS[LTF], cfg,
                                     allow_longs=True, arm_ttl_bars=30)
                R += [t.r_multiple for t in Backtester(cfg, BacktestConfig()).run(cs, st).trades]
            return R
        return runner

    def line(name, res):
        n, wr, exp, pf, pos, per = res
        pfs = "inf" if pf == float("inf") else f"{pf:.2f}"
        cells = " ".join(f"{e:+.2f}" for e in per)
        print(f"{name:26s}: сделок={n:4d} win={wr:4.1f}% exp={exp:+.3f}R pf={pfs} "
              f"+окон={pos}/{K}  [{cells}]")

    print("=== База ===")
    line("одно-ТФ v1 (1h)", wf(run_single))
    line("мультиТФ 4h->1h (mtf_v1)", wf(make_mtf_runner(htf_4h, "4h", mtf_v1)))

    print("\n=== 1D->1h: тюнинг HTF-порогов (trend_ps / pivot_ps / min_score) ===")
    grid = [(2, 2, 3), (2, 2, 2), (3, 2, 3), (2, 1, 3), (3, 2, 2)]
    best = None
    for tps, pps, sc in grid:
        res = wf(make_mtf_runner(htf_1d, "1d", lambda tps=tps, pps=pps, sc=sc: mtf_cfg(tps, pps, sc)))
        line(f"1D->1h ts{tps}/ps{pps}/sc{sc}", res)
        if best is None or (res[4], res[2]) > (best[1][4], best[1][2]):
            best = ((tps, pps, sc), res)

    print("\n=== Итог ===")
    (tps, pps, sc), res = best
    print(f"Лучшая 1D->1h: ts{tps}/ps{pps}/sc{sc} -> exp={res[2]:+.3f}R, +окон={res[4]}/{K}, win={res[1]:.1f}%")
    print("Оговорка: HTF-пороги подобраны на тех же 5 окнах -> есть риск подгонки; "
          "нужна проверка на новых данных/монетах.")


if __name__ == "__main__":
    main()
