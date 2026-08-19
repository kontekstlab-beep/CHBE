"""Хвостовой риск: влияние стоп-лосса на mean-reversion.

Дилемма: стоп режет катастрофические проливы, НО у mean-reversion часто выбивает
перед самым отскоком. Меряем и доходность, и хвост (худшая сделка, 5%-хвост,
волатильность, просадка, risk-adjusted). Разработка на DEV -> заморозка -> HOLDOUT.

    python tail_risk.py
"""
from __future__ import annotations

from statistics import mean, pstdev
from typing import List

from meanrev import zseries
from meanrev_maker import load_ohlc
from smartmoney.datasets import HOLDOUT, OOS_USED, TUNING

N, ENTRY_Z, EXIT_Z, HOLD = 48, -2.0, 0.0, 8
MAKER, TAKER = 0.0002, 0.0005


def backtest(closes, lows, stop_frac: float, fill_window: int = 3) -> List[float]:
    z = zseries(closes, N)
    out: List[float] = []
    i = N
    n = len(closes)
    while i < n - 1:
        if z[i] is None or z[i] >= ENTRY_Z:
            i += 1
            continue
        limit = closes[i]
        entry_bar = None
        for jj in range(i + 1, min(i + 1 + fill_window, n)):
            if lows[jj] <= limit:
                entry_bar = jj
                break
        if entry_bar is None:
            i += 1
            continue
        entry = limit
        stop_px = entry * (1 - stop_frac) if stop_frac > 0 else None
        k = entry_bar + 1
        exit_px = None
        while k < n:
            if stop_px is not None and lows[k] <= stop_px:   # стоп (adverse-first)
                exit_px = stop_px
                break
            if z[k] is not None and z[k] >= EXIT_Z:          # возврат к среднему
                exit_px = closes[k]
                break
            if (k - entry_bar) >= HOLD:                       # тайм-стоп
                exit_px = closes[k]
                break
            k += 1
        if exit_px is None:
            exit_px = closes[min(k, n - 1)]
        out.append(exit_px / entry - 1 - MAKER - TAKER)
        i = min(k, n - 1) + 1
    return out


def metrics(R: List[float]):
    n = len(R)
    if not n:
        return {}
    m = mean(R)
    sd = pstdev(R) or 1e-9
    sr = sorted(R)
    p05 = sr[max(0, int(0.05 * n) - 1)]
    worst = sr[0]
    wr = sum(1 for x in R if x > 0) / n * 100
    gw = sum(x for x in R if x > 0)
    gl = -sum(x for x in R if x < 0)
    pf = gw / gl if gl > 0 else float("inf")
    # просадка кумулятивной суммы (в R-независимых %)
    cum = 0.0
    peak = 0.0
    mdd = 0.0
    for x in R:
        cum += x
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
    return dict(n=n, win=wr, net=m, pf=pf, sharpe=m / sd, worst=worst, p05=p05,
                std=sd, mdd=mdd)


def run(symbols, stop_frac):
    R: List[float] = []
    for s in symbols:
        closes, lows = load_ohlc(s)
        R += backtest(closes, lows, stop_frac)
    return R


def show(label, symbols, stops):
    print(f"\n-- {label} --")
    print(f"{'стоп':>6s} {'сделок':>6s} {'win%':>5s} {'нетто%':>7s} {'pf':>5s} "
          f"{'sharpe':>6s} {'худш%':>7s} {'5%хв%':>7s} {'просадка%':>9s}")
    for sf in stops:
        M = metrics(run(symbols, sf))
        pfs = "inf" if M['pf'] == float("inf") else f"{M['pf']:.2f}"
        lab = "нет" if sf == 0 else f"{sf*100:.0f}%"
        print(f"{lab:>6s} {M['n']:6d} {M['win']:5.1f} {M['net']*100:+7.3f} {pfs:>5s} "
              f"{M['sharpe']:6.3f} {M['worst']*100:7.2f} {M['p05']*100:7.2f} {M['mdd']*100:9.2f}")


def main() -> None:
    stops = [0, 0.02, 0.03, 0.05, 0.08]
    show("DEV (TUNING+OOS) — подбор стопа", TUNING + OOS_USED, stops)
    show("HOLDOUT (заморожено)", HOLDOUT, stops)
    print("\nЧитать так: ищем стоп, который сильно уменьшает |худшую| и просадку, "
          "не убивая нетто/сделку и sharpe.")


if __name__ == "__main__":
    main()
