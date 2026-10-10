"""M7-4a: download FRESH12v2 data (NO validation here, data acquisition only).

FRESH12v2 = 12 coins absent from ALL prior sets (TUNING/OOS_USED/HOLDOUT from
smartmoney/datasets.py + EXPL18/FRESH12 from M6). Primary list:
PEPE WIF BONK FLOKI JUP PYTH JTO WLD STX KAS LDO MKR; replacements (if history
< 4000 1h bars on binanceusdm): ETHFI ENA AUCTION AR.

Saves data/<SYM>USDT_1h_4000.csv via smartmoney.data.save_csv.
NEVER overwrites existing files (data/ is append-only per project rules).

All prints ASCII-only.
"""
from __future__ import annotations

import os

from smartmoney.data import load_binance_paged, save_csv
from smartmoney.datasets import HOLDOUT, OOS_USED, TUNING

EXPL18 = ["SOL", "LINK", "NEAR", "FIL", "APE", "XRP", "BNB", "CRV", "1INCH",
          "GALA", "CHR", "ETH", "ADA", "DOGE", "AVAX", "DOT", "LTC", "ATOM"]
FRESH12 = ["TON", "HBAR", "XLM", "ALGO", "ICP", "ETC",
           "FET", "RENDER", "TIA", "SEI", "ONDO", "IMX"]
USED = {s.split("/")[0] for s in TUNING + OOS_USED + HOLDOUT} | set(EXPL18) | set(FRESH12)

PRIMARY = ["PEPE", "WIF", "BONK", "FLOKI", "JUP", "PYTH",
           "JTO", "WLD", "STX", "KAS", "LDO", "MKR"]
REPLACEMENTS = ["ETHFI", "ENA", "AUCTION", "AR"]


def main() -> None:
    picked = []
    queue = PRIMARY + REPLACEMENTS
    for base in queue:
        if len(picked) >= 12:
            break
        assert base not in USED, f"{base} уже использовался в наборах!"
        sym = base + "/USDT"
        path = os.path.join("data", base + "USDT_1h_4000.csv")
        if os.path.exists(path):
            print(f"{base:8s} exists in data/ -> reuse")
            picked.append(base)
            continue
        try:
            cs = load_binance_paged(sym, "1h", 4000, futures=True)
        except Exception as e:
            print(f"{base:8s} DOWNLOAD FAILED: {e} -> skip")
            continue
        if len(cs) < 4000:
            print(f"{base:8s} only {len(cs)} bars (<4000) -> skip")
            continue
        save_csv(cs, path)
        print(f"{base:8s} saved {len(cs)} bars -> {path}")
        picked.append(base)
    print(f"\nFRESH12v2 = {picked}")
    assert len(picked) == 12, "not enough coins with full history!"


if __name__ == "__main__":
    main()
