"""M7-4b: FRESH12v2 validation - FIRST and ONLY use of this set.

Frozen BEFORE the run (from EXPL18-only analysis in M7-1..3):
  H1 = C6 production config: SMA48, entry z<-2, exit z>=0, hold 8, stop 8%,
       maker limit @close, ladder z<-3 (5% extra), BTC z48<-1 gate;
  H2 = C6 + hour filter: NO new entries triggered at UTC hours {1,6,19}
       (ladders of already-open positions are NOT affected - M7-3 showed
       identical results with/without ladder blocking, simpler is better).

Exactly 2 runs. Comparison: paired test across 12 coins (per-coin mean net),
SPOT_BNB fees primary (live bot is spot), FUTURES reference.
Verdict rule (pre-specified): filter CONFIRMED iff diff > +0.03 pp/trade AND t > 2.

All prints ASCII-only.
"""
from __future__ import annotations

import math
from statistics import mean, pstdev

from explore_m6_lib import Cfg, backtest_coin, basic_stats, load, portfolio, report

FRESH12V2 = ["WIF", "JUP", "PYTH", "JTO", "WLD", "STX",
             "KAS", "LDO", "MKR", "ETHFI", "ENA", "AUCTION"]

H1 = ("H1 C6", Cfg(ladder_z=-3.0, btc_mode="req_z", btc_z=-1.0))
H2 = ("H2 C6+no{1,6,19}", Cfg(ladder_z=-3.0, btc_mode="req_z", btc_z=-1.0,
                              hours=set(range(24)) - {1, 6, 19}))


def run(cfg: Cfg):
    tr = []
    for s in FRESH12V2:
        tr += backtest_coin(load(s), cfg)
    return tr


def paired(cfg1: Cfg, cfg2: Cfg, fee_model: str):
    diffs = []
    for s in FRESH12V2:
        t1 = backtest_coin(load(s), Cfg(**{**cfg1.__dict__, "fee_model": fee_model}))
        t2 = backtest_coin(load(s), Cfg(**{**cfg2.__dict__, "fee_model": fee_model}))
        if t1 and t2:
            diffs.append(mean(t.net for t in t2) - mean(t.net for t in t1))
    md = mean(diffs)
    sd = pstdev(diffs) or 1e-9
    t = md / (sd / math.sqrt(len(diffs)))
    return md, t, len(diffs)


def main() -> None:
    print("=== M7-4b. FRESH12v2 (2 frozen runs: H1, H2) ===")
    for name, cfg in (H1, H2):
        for fm in ("SPOT_BNB", "FUTURES"):
            report(f"FRESH12v2 {name} [{fm}]",
                   run(Cfg(**{**cfg.__dict__, "fee_model": fm})))
    md, t, k = paired(H1[1], H2[1], "SPOT_BNB")
    print(f"\npaired test across {k} coins (SPOT_BNB): H2-H1 = {md*100:+.3f} pp/trade, "
          f"t = {t:+.2f}")
    eco = md > 0.0003
    stat = t > 2
    print(f"economic threshold +0.03pp: {'PASS' if eco else 'FAIL'}; "
          f"statistical t>2: {'PASS' if stat else 'FAIL'}")
    print(f"VERDICT: hour filter {'CONFIRMED' if eco and stat else 'REJECTED'} "
          f"on FRESH12v2")


if __name__ == "__main__":
    main()
