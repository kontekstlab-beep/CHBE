"""M9 shared helpers: multi-timeframe data loading + fast z-series.

Reuses the M6 research engine (explore_m6_lib.backtest_coin etc.) unchanged:
data for any timeframe is injected into explore_m6_lib.CACHE, and the BTC gate
context (lib._BTC) is rebuilt per (timeframe, n) so that the BTC filter uses
z(n) on the SAME timeframe, exactly like production (paper engine computes the
BTC gate with cfg.sma_n on its working timeframe).

fast zseries: rolling sums, O(L) instead of O(L*n) - required for 16000/48000
bar series. Verified to reproduce the 1h baseline (see regression in M9 report).
"""
from __future__ import annotations

import csv
import os
from typing import Dict, List

import explore_m6_lib as lib


def zseries_fast(c: List[float], n: int):
    z = [None] * len(c)
    s = sq = 0.0
    for i, x in enumerate(c):
        s += x
        sq += x * x
        if i >= n:
            y = c[i - n]
            s -= y
            sq -= y * y
        if i >= n - 1:
            m = s / n
            var = sq / n - m * m
            sd = var ** 0.5 if var > 1e-18 else 1e-9
            z[i] = (x - m) / sd
    return z


# подменяем медленный O(L*n) zseries в движке M6 на быстрый
lib.zseries = zseries_fast

_TF_CACHE: Dict[str, dict] = {}

# bars per 24h per timeframe (for the BTC 24h return used by 'block_crash' mode)
_BARS_24H = {"1h": 24, "15m": 96, "5m": 288}


def load_tf(base: str, tf: str, total: int) -> dict:
    key = f"{base}_{tf}_{total}"
    if key in _TF_CACHE:
        return _TF_CACHE[key]
    path = os.path.join("data", f"{base}USDT_{tf}_{total}.csv")
    ts, o, h, lo, c, v = [], [], [], [], [], []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ts.append(int(float(r["ts"])))
            o.append(float(r["open"]))
            h.append(float(r["high"]))
            lo.append(float(r["low"]))
            c.append(float(r["close"]))
            v.append(float(r["volume"]))
    d = dict(sym=base, ts=ts, o=o, h=h, lo=lo, c=c, v=v)
    _TF_CACHE[key] = d
    return d


def setup_tf(symbols: List[str], tf: str, total: int, n: int) -> None:
    """Inject TF data into the M6 engine and rebuild the BTC gate context
    with z(n) on this timeframe (production-consistent)."""
    for s in symbols:
        lib.CACHE[s] = load_tf(s, tf, total)
    btc = load_tf("BTC", tf, total)
    z = zseries_fast(btc["c"], n)
    b24 = _BARS_24H[tf]
    ctx = {}
    for i, t in enumerate(btc["ts"]):
        r24 = btc["c"][i] / btc["c"][i - b24] - 1 if i >= b24 else 0.0
        ctx[t] = (z[i] if z[i] is not None else 0.0, r24)
    lib._BTC = ctx


def run_tf(symbols: List[str], tf: str, total: int, cfg: lib.Cfg):
    setup_tf(symbols, tf, total, cfg.n)
    return lib.run_set(symbols, cfg)
