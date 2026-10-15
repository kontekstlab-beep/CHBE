"""M9-0b: download 15m candles for FRESH12v2 (sanity checks only, set is exposed).

FRESH12v2 was exposed in M7 and is allowed as a SECONDARY tuning set.
15m data for it was not part of the M9-0 priority batch - fetch here.

All prints ASCII-only.
"""
from __future__ import annotations

from explore_m9_download import fetch

FRESH12V2 = ["WIF", "JUP", "PYTH", "JTO", "WLD", "STX",
             "KAS", "LDO", "MKR", "ETHFI", "ENA", "AUCTION"]


def main() -> None:
    for base in FRESH12V2:
        fetch(base, "15m", 16000)


if __name__ == "__main__":
    main()
