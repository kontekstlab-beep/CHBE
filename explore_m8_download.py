"""M8-4a: download FRESH12v3 data (NO validation here, data acquisition only).

FRESH12v3 = 12 coins absent from ALL prior sets:
  TUNING, OOS_USED, HOLDOUT (smartmoney/datasets.py),
  EXPL18, FRESH12 (M6), FRESH12v2 (M7).
Candidates (long binanceusdm history): SAND MANA ENJ CHZ AXS SUSHI SNX COMP
LRC ZIL QTUM DASH ZEC WAVES KAVA ROSE ONE FTM GMX DYDX; first 12 with the full
4000 1h bars are taken.

Saves data/<SYM>USDT_1h_4000.csv; NEVER overwrites existing files.
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
FRESH12V2 = ["WIF", "JUP", "PYTH", "JTO", "WLD", "STX",
             "KAS", "LDO", "MKR", "ETHFI", "ENA", "AUCTION"]
USED = ({s.split("/")[0] for s in TUNING + OOS_USED + HOLDOUT}
        | set(EXPL18) | set(FRESH12) | set(FRESH12V2))

CANDIDATES = ["SAND", "MANA", "ENJ", "CHZ", "AXS", "SUSHI", "SNX", "COMP",
              "LRC", "ZIL", "QTUM", "DASH", "ZEC", "WAVES", "KAVA", "ROSE",
              "ONE", "FTM", "GMX", "DYDX"]


def main() -> None:
    picked = []
    for base in CANDIDATES:
        if len(picked) >= 12:
            break
        assert base not in USED, f"{base} already used in a dataset!"
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
    print(f"\nFRESH12v3 = {picked}")
    assert len(picked) == 12, "not enough coins with full history!"


if __name__ == "__main__":
    main()
