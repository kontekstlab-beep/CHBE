"""M9-0: download 15m and 5m candles (USDT-M futures) for EXPL18 + FRESH12v3 + BTC.

Same ~166 day window as the 1h data:
  15m = 16000 bars, 5m = 48000 bars per coin.
Files: data/<SYM>USDT_15m_16000.csv, data/<SYM>USDT_5m_48000.csv.
NEVER overwrites existing files. Respects ccxt rate limits (load_binance_paged
already sleeps between paged requests).

If 5m proves too heavy, halve to 24000 bars (~83 days) and record the decision
in the report.

All prints ASCII-only.
"""
from __future__ import annotations

import os
import sys
import time

from smartmoney.data import load_binance_paged, save_csv

EXPL18 = ["SOL", "LINK", "NEAR", "FIL", "APE", "XRP", "BNB", "CRV", "1INCH",
          "GALA", "CHR", "ETH", "ADA", "DOGE", "AVAX", "DOT", "LTC", "ATOM"]
FRESH12V3 = ["SAND", "MANA", "ENJ", "CHZ", "AXS", "SUSHI",
             "SNX", "COMP", "LRC", "ZIL", "QTUM", "DASH"]
COINS = ["BTC"] + EXPL18 + FRESH12V3

JOBS = [("15m", 16000), ("5m", 48000)]


def fetch(base, tf, total):
    path = os.path.join("data", f"{base}USDT_{tf}_{total}.csv")
    if os.path.exists(path):
        print(f"{base:8s} {tf} exists -> skip", flush=True)
        return True
    try:
        cs = load_binance_paged(base + "/USDT", tf, total, futures=True)
    except Exception as e:
        print(f"{base:8s} {tf} FAILED: {e}", flush=True)
        return False
    if len(cs) < total:
        print(f"{base:8s} {tf} only {len(cs)}/{total} bars -> skip", flush=True)
        return False
    save_csv(cs, path)
    print(f"{base:8s} {tf} saved {len(cs)} bars", flush=True)
    return True


def main() -> None:
    only = sys.argv[1] if len(sys.argv) > 1 else None   # '15m' | '5m' | None
    t0 = time.time()
    for tf, total in JOBS:
        if only and tf != only:
            continue
        for base in COINS:
            fetch(base, tf, total)
        print(f"--- {tf} done, elapsed {time.time()-t0:.0f}s ---", flush=True)


if __name__ == "__main__":
    main()
