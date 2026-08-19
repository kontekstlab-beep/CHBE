"""Фильтр монет для mean-reversion — БЕЗ отбора по результату на holdout.

Идея: стратегия mean-reversion должна работать на склонных к возврату монетах.
Мерило «возвратности», вычислимое заранее, — лаг-1 автокорреляция 1h-доходностей
(отрицательная = mean-reverting). Проверяем:
  1) предсказывает ли автокорреляция успех стратегии по монетам (на TUNING+OOS);
  2) реалистичный ТРЕЙЛИНГ-фильтр: торговать монету в периоде k, только если она
     проходила фильтр по данным ДО k (walk-forward, без look-ahead);
  3) заморозка -> HOLDOUT.

    python coin_filter.py
"""
from __future__ import annotations

from statistics import mean, pstdev
from typing import Dict, List

from meanrev_maker import backtest, load_ohlc
from smartmoney.datasets import HOLDOUT, OOS_USED, TUNING

MAKER, TAKER = 0.0002, 0.0005
# frozen strategy execution (maker-вход, taker-выход — консервативно)
KW = dict(entry_mode="maker", offset=0.0, fill_window=3, fee_in=MAKER, fee_out=TAKER)


def autocorr1(closes: List[float]) -> float:
    rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
    a, b = rets[:-1], rets[1:]
    ma, mb = mean(a), mean(b)
    cov = mean((x - ma) * (y - mb) for x, y in zip(a, b))
    sa, sb = pstdev(a), pstdev(b)
    return cov / (sa * sb) if sa and sb else 0.0


def net_of(closes, lows) -> tuple:
    tr, sig, fil = backtest(closes, lows, **KW)
    return (mean(tr) if tr else 0.0), len(tr)


def pearson(xs, ys):
    mx, my = mean(xs), mean(ys)
    cov = mean((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx, sy = pstdev(xs), pstdev(ys)
    return cov / (sx * sy) if sx and sy else 0.0


def measure_relationship():
    print("=== 1) Автокорреляция vs успех стратегии (TUNING+OOS, per coin) ===")
    print(f"{'монета':11s} {'autocorr1':>10s} {'нетто%/сд':>10s} {'сделок':>6s}")
    acs, nets = [], []
    for s in TUNING + OOS_USED:
        closes, lows = load_ohlc(s)
        ac = autocorr1(closes)
        net, n = net_of(closes, lows)
        acs.append(ac)
        nets.append(net)
        print(f"{s:11s} {ac:+10.4f} {net*100:+10.3f} {n:6d}")
    r = pearson(acs, nets)
    print(f"\nКорреляция(autocorr, нетто) = {r:+.3f}  "
          f"(<0 => более mean-reverting монеты прибыльнее — фильтр осмыслен)")
    return r


def walkforward_filter(symbols, mode, K=6):
    """mode: None (без фильтра) | 'autocorr' (trailing autocorr<0) |
    'perf' (trailing нетто стратегии > 0). Все режимы пропускают блок 0."""
    R: List[float] = []
    for s in symbols:
        closes, lows = load_ohlc(s)
        m = len(closes) // K
        for k in range(1, K):
            block_c = closes[k * m:(k + 1) * m]
            block_l = lows[k * m:(k + 1) * m]
            if mode == "autocorr":
                trail = closes[:k * m]
                if len(trail) < 50 or autocorr1(trail) >= 0:
                    continue
            elif mode == "perf":
                # доходность стратегии на этой монете по прошлым блокам
                pt, _, _ = backtest(closes[:k * m], lows[:k * m], **KW)
                if len(pt) < 5 or mean(pt) <= 0:
                    continue
            tr, _, _ = backtest(block_c, block_l, **KW)
            R += tr
    n = len(R)
    net = mean(R) if R else 0.0
    wr = sum(1 for x in R if x > 0) / n * 100 if n else 0.0
    gw = sum(x for x in R if x > 0)
    gl = -sum(x for x in R if x < 0)
    pf = gw / gl if gl > 0 else float("inf")
    return n, wr, net, pf


def line(label, symbols, mode):
    n, wr, net, pf = walkforward_filter(symbols, mode)
    pfs = "inf" if pf == float("inf") else f"{pf:.2f}"
    print(f"{label:28s} сделок={n:4d} win={wr:4.1f}% нетто={net*100:+.3f}% pf={pfs}")


def main() -> None:
    measure_relationship()

    print("\n=== 2) Трейлинг-фильтры на DEV (TUNING+OOS) — решаем, стоит ли тратить holdout ===")
    line("без фильтра", TUNING + OOS_USED, None)
    line("autocorr<0", TUNING + OOS_USED, "autocorr")
    line("perf>0 (прошлая доходность)", TUNING + OOS_USED, "perf")

    print("\n=== 3) HOLDOUT (заморожено) — только базовая стратегия ===")
    line("без фильтра", HOLDOUT, None)


if __name__ == "__main__":
    main()
