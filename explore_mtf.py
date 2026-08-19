"""M3.4: сравнение одно-ТФ vs настоящий мультиТФ на walk-forward.

- одно-ТФ: SmartMoneyStrategy(backtest_v1) на 1h (тренд/зона/вход — одна серия).
- мультиТФ: MultiTFStrategy — контекст с 4h, подтверждение/вход на 1h.

Метрика робастности — плюс в скольких из 5 окон.

    python explore_mtf.py
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
HTF = "4h"


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


def main() -> None:
    ltf_all, htf_all = {}, {}
    for s in SYMBOLS:
        ltf_all[s] = get_cached(s, LTF, TOTAL_BARS)
        htf_all[s] = get_cached(s, HTF, 1500)

    # окна на LTF (1h)
    folds = [[] for _ in range(K)]
    for s in SYMBOLS:
        c = ltf_all[s]
        n = len(c) // K
        for k in range(K):
            folds[k].append((s, reindex(c[k * n:(k + 1) * n])))

    def run_single(fold):
        R = []
        for _, cs in fold:
            st = SmartMoneyStrategy(backtest_v1(), allow_longs=True, arm_ttl_bars=30)
            res = Backtester(backtest_v1(), BacktestConfig()).run(cs, st)
            R += [t.r_multiple for t in res.trades]
        return R

    def run_mtf(fold):
        R = []
        for s, cs in fold:
            st = MultiTFStrategy(htf_all[s], _TF_MS[HTF], _TF_MS[LTF],
                                 mtf_v1(), allow_longs=True, arm_ttl_bars=30)
            res = Backtester(mtf_v1(), BacktestConfig()).run(cs, st)
            R += [t.r_multiple for t in res.trades]
        return R

    print(f"=== одно-ТФ (1h) vs мультиТФ ({HTF} контекст + {LTF} вход) — walk-forward ===\n")
    for name, runner in (("одно-ТФ v1", run_single), ("мультиТФ", run_mtf)):
        pos = 0
        allR: List[float] = []
        per = []
        for k in range(K):
            R = runner(folds[k])
            allR += R
            _, wr, exp, _ = stats(R)
            per.append(exp)
            if exp > 0:
                pos += 1
        n, wr, exp, pf = stats(allR)
        pfs = "inf" if pf == float("inf") else f"{pf:.2f}"
        cells = " ".join(f"{e:+.2f}" for e in per)
        print(f"{name:12s}: сделок={n:4d} win={wr:4.1f}% exp={exp:+.3f}R pf={pfs} "
              f"+окон={pos}/{K}  [{cells}]")

    print("\nПрим.: пороги не переоптимизировались под мультиТФ (mtf_v1 ≈ v1). "
          "Сравнение показывает эффект самой мультиТФ-архитектуры.")


if __name__ == "__main__":
    main()
