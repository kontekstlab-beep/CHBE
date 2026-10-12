"""M8-4: selection. Candidate from M8-2: E3 = C6 + partial 50% at z>=-1.

Before spending the FRESH12v3 validation, a sanity check on FRESH12v2
(already exposed in M7 - allowed as secondary tuning, NOT a verdict):
does the E3 direction hold there? If it fails even on v2, v3 is not spent.

All prints ASCII-only.
"""
from __future__ import annotations

import math
from statistics import mean, pstdev

from explore_m6_lib import Cfg, backtest_coin, load, run_set, report

C6 = dict(ladder_z=-3.0, btc_mode="req_z", btc_z=-1.0)
E0 = Cfg(**C6)
E3 = Cfg(**C6, partial_z=-1.0)

FRESH12V2 = ["WIF", "JUP", "PYTH", "JTO", "WLD", "STX",
             "KAS", "LDO", "MKR", "ETHFI", "ENA", "AUCTION"]


def paired(symbols, cfg1, cfg2, fm):
    diffs = []
    for s in symbols:
        t1 = backtest_coin(load(s), Cfg(**{**cfg1.__dict__, "fee_model": fm}))
        t2 = backtest_coin(load(s), Cfg(**{**cfg2.__dict__, "fee_model": fm}))
        if t1 and t2:
            diffs.append(mean(t.net for t in t2) - mean(t.net for t in t1))
    md = mean(diffs)
    sd = pstdev(diffs) or 1e-9
    return md, md / (sd / math.sqrt(len(diffs))), len(diffs)


def main() -> None:
    print("=== M8-4. E3 sanity on FRESH12v2 (secondary tuning, NOT a verdict) ===")
    for name, cfg in (("E0 C6", E0), ("E3 C6+partial@-1", E3)):
        for fm in ("SPOT_BNB", "FUTURES"):
            report(f"{name} [{fm}]",
                   run_set(FRESH12V2, Cfg(**{**cfg.__dict__, "fee_model": fm})))
    md, t, k = paired(FRESH12V2, E0, E3, "SPOT_BNB")
    print(f"\npaired across {k} coins (SPOT_BNB): E3-E0 = {md*100:+.3f} pp/trade, t={t:+.2f}")
    print("(informational only; decision to spend FRESH12v3 follows)")


if __name__ == "__main__":
    main()
