"""Истинный out-of-sample: замороженный пресет mtf_1d_v1 на НОВЫХ монетах,
которых не было в тюнинге. Никакой подгонки — конфиг берётся как есть.

    python oos_test.py
"""
from __future__ import annotations

from typing import List

from smartmoney.backtest import Backtester, BacktestConfig
from smartmoney.data import _TF_MS, get_cached
from smartmoney.models import Candle
from smartmoney.mtf import MultiTFStrategy
from smartmoney.presets import mtf_1d_v1

# монеты, НЕ участвовавшие в тюнинге (тюнили на: SOL,LINK,NEAR,FIL,APE,XRP,BNB,CRV)
NEW_SYMBOLS = ["1INCH/USDT", "GALA/USDT", "CHR/USDT", "ETH/USDT", "ADA/USDT",
               "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "LTC/USDT", "ATOM/USDT"]
LTF, HTF = "1h", "1d"
K = 5


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


def run(ltf, htf):
    st = MultiTFStrategy(htf, _TF_MS[HTF], _TF_MS[LTF], mtf_1d_v1(),
                         allow_longs=True, arm_ttl_bars=30)
    res = Backtester(mtf_1d_v1(), BacktestConfig()).run(ltf, st)
    return [t.r_multiple for t in res.trades]


def main() -> None:
    print("=== ИСТИННЫЙ OUT-OF-SAMPLE: mtf_1d_v1 (заморожен) на новых монетах ===\n")
    print(f"{'монета':12s} {'сделок':>6s} {'win%':>6s} {'exp,R':>7s} {'pf':>5s}")
    print("-" * 40)
    allR: List[float] = []
    pos = 0
    per_symbol = []
    ltf_map, htf_map = {}, {}
    for s in NEW_SYMBOLS:
        ltf_map[s] = get_cached(s, LTF, 4000)
        htf_map[s] = get_cached(s, HTF, 1000)
        R = run(ltf_map[s], htf_map[s])
        allR += R
        n, wr, exp, pf = stats(R)
        per_symbol.append((s, n, wr, exp))
        if exp > 0:
            pos += 1
        pfs = "inf" if pf == float("inf") else f"{pf:.2f}"
        print(f"{s:12s} {n:6d} {wr:6.1f} {exp:+7.3f} {pfs:>5s}")

    n, wr, exp, pf = stats(allR)
    pfs = "inf" if pf == float("inf") else f"{pf:.2f}"
    print("-" * 40)
    print(f"{'ПУЛ':12s} {n:6d} {wr:6.1f} {exp:+7.3f} {pfs:>5s}   монет в плюсе: {pos}/{len(NEW_SYMBOLS)}")

    # walk-forward по 5 окнам на новых монетах (контекст стабильности)
    folds = [[] for _ in range(K)]
    for s in NEW_SYMBOLS:
        c = ltf_map[s]
        m = len(c) // K
        for k in range(K):
            folds[k].append((s, reindex(c[k * m:(k + 1) * m])))
    print("\nWalk-forward по окнам (новые монеты):")
    wpos = 0
    for k in range(K):
        R = []
        for s, cs in folds[k]:
            R += run(cs, htf_map[s])
        _, wwr, wexp, _ = stats(R)
        if wexp > 0:
            wpos += 1
        print(f"  окно {k+1}: сделок={len(R):3d} win={wwr:4.1f}% exp={wexp:+.3f}R")
    print(f"  плюсовых окон: {wpos}/{K}")

    print("\n=== Вердикт ===")
    if exp > 0 and pos >= len(NEW_SYMBOLS) * 0.6:
        print(f"Edge ПОДТВЕРЖДЁН на новых монетах: пул {exp:+.3f}R, {pos}/{len(NEW_SYMBOLS)} в плюсе.")
    elif exp > 0:
        print(f"Пул положительный ({exp:+.3f}R), но разброс по монетам большой — edge слабый.")
    else:
        print(f"Edge НЕ подтвердился out-of-sample (пул {exp:+.3f}R) — вероятна подгонка.")


if __name__ == "__main__":
    main()
