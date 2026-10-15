"""M10 shared helpers: trend/momentum SHORT research (hedge for the C6 long bot).

Data: cached 1h files end ~2026-10-09, i.e. BEFORE the Oct 12-13 crash week.
To cover it, each series is extended IN MEMORY with fresh bars fetched via
load_binance_paged (nothing is written to data/, cached files untouched).
NOTE: this extends the M6-M9 window; M10 numbers are therefore not directly
comparable to M6-M8 tables (they have ~6 extra days, including a crash).

Short engine: momentum entries need immediacy -> entry at NEXT BAR OPEN,
taker fee; exits at close (taker) or stop price (taker). FUTURES fees
(taker 0.05%). Funding ~0 on average (discussed in the report).

All prints ASCII-only.
"""
from __future__ import annotations

from statistics import mean
from typing import Dict, List, Optional

import explore_m6_lib as lib
from explore_m6_lib import FEES, basic_stats, portfolio
from smartmoney.data import load_binance_paged

DAY = 86_400_000
TAKER = FEES["FUTURES"][1]      # 0.0005

_EXT: Dict[str, dict] = {}


def load_ext(base: str, fresh_tail: int = 250) -> dict:
    """Cached 4000-bar 1h series + fresh tail (in memory only)."""
    if base in _EXT:
        return _EXT[base]
    old = lib.load(base)                      # cached file (read-only)
    d = {k: list(v) if isinstance(v, list) else v for k, v in old.items()}
    sym = base + "/USDT"
    try:
        cs = load_binance_paged(sym, "1h", fresh_tail, futures=True)
        last = d["ts"][-1]
        add = [c for c in cs if c.ts > last]
        for c in add:
            d["ts"].append(c.ts)
            d["o"].append(c.open)
            d["h"].append(c.high)
            d["lo"].append(c.low)
            d["c"].append(c.close)
            d["v"].append(c.volume)
    except Exception as e:                    # pragma: no cover - сеть
        print(f"WARN {base}: fresh tail failed ({e}), using cached only")
    _EXT[base] = d
    return d


def sma_series(c: List[float], n: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(c)
    s = 0.0
    for i, x in enumerate(c):
        s += x
        if i >= n:
            s -= c[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


class STrade:
    __slots__ = ("sym", "entry_i", "exit_i", "entry", "exit", "reason",
                 "gross", "net")

    def __init__(self, sym, entry_i, exit_i, entry, exit_, reason, fee_rt):
        self.sym = sym
        self.entry_i = entry_i
        self.exit_i = exit_i
        self.entry = entry
        self.exit = exit_
        self.reason = reason
        self.gross = entry / exit_ - 1 if exit_ else 0.0   # short
        self.net = self.gross - fee_rt


def short_bt(d: dict, enter, exit_fn, stop: float, hold: int,
             fee_rt: float = 2 * TAKER, start: int = 96) -> List[STrade]:
    """Short: enter(i) at close[i] -> fill at OPEN of bar i+1 (taker);
    manage from i+1: stop (+stop vs entry, by high), exit_fn(k) at close,
    time stop after `hold` bars. Non-overlapping per coin."""
    c, o, h, lo, ts = d["c"], d["o"], d["h"], d["lo"], d["ts"]
    L = len(c)
    trades: List[STrade] = []
    i = start
    while i < L - 1:
        if not enter(i):
            i += 1
            continue
        entry = o[i + 1]                     # taker at next bar open
        entry_i = i + 1
        stop_px = entry * (1 + stop)
        exit_px = reason = None
        k = entry_i
        while k < L:
            if stop > 0 and h[k] >= stop_px:
                exit_px, reason = stop_px, "stop"
                break
            if k > entry_i and exit_fn(k):
                exit_px, reason = c[k], "signal"
                break
            if (k - entry_i) >= hold:
                exit_px, reason = c[k], "time"
                break
            k += 1
        if exit_px is None:
            exit_px, reason, k = c[L - 1], "end", L - 1
        trades.append(STrade(d["sym"], entry_i, k, entry, exit_px, reason, fee_rt))
        i = k + 1
    return trades


def stats_str(trades: List[STrade]) -> dict:
    R = [t.net for t in trades]
    n = len(R)
    if not n:
        return dict(n=0, win=0.0, net=0.0, pf=0.0, med=0.0, worst=0.0)
    m = mean(R)
    wr = sum(1 for r in R if r > 0) / n * 100
    gw = sum(r for r in R if r > 0)
    gl = -sum(r for r in R if r < 0)
    pf = gw / gl if gl > 0 else float("inf")
    per: Dict[str, List[float]] = {}
    for t in trades:
        per.setdefault(t.sym, []).append(t.net)
    from statistics import median
    med = median(mean(v) for v in per.values())
    return dict(n=n, win=wr, net=m, pf=pf, med=med, worst=min(R))


def report(label: str, trades: List[STrade]) -> dict:
    s = stats_str(trades)
    # портфель: 5% капитала на позицию, без компаундинга (как в M6-M9)
    fake = [type("T", (), {"exit_i": t.exit_i, "net": t.net}) for t in trades]
    pnl, mdd = portfolio(fake)
    pfs = "inf" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    print(f"{label:34s} n={s['n']:4d} win={s['win']:5.1f}% net={s['net']*100:+7.3f}% "
          f"pf={pfs:>5s} med={s['med']*100:+6.3f}% worst={s['worst']*100:6.2f}% "
          f"P&L={pnl*100:+6.2f}% MDD={mdd*100:5.2f}%")
    return {**s, "pnl": pnl, "mdd": mdd}


def daily_pnl(trades, d_map: Dict[str, dict]) -> Dict[int, float]:
    """day-of-exit -> sum of per-trade net (fractions)."""
    out: Dict[int, float] = {}
    for t in trades:
        day = d_map[t.sym]["ts"][t.exit_i] // DAY
        out[day] = out.get(day, 0.0) + t.net
    return out


def pearson(x: List[float], y: List[float]) -> float:
    n = len(x)
    mx, my = mean(x), mean(y)
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y))
    vx = sum((a - mx) ** 2 for a in x)
    vy = sum((b - my) ** 2 for b in y)
    return cov / (vx * vy) ** 0.5 if vx > 0 and vy > 0 else 0.0
