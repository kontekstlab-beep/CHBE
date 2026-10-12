"""M9-3a: sanity of the 15m candidate on FRESH12v2 (secondary tuning, NOT a verdict).

Frozen candidate from the EXPL18 TF map:
  CAND-15m = C6 logic on 15m, n=192 (=SMA48@1h), entry_z=-2.5, hold=32 (=8h),
             stop -8%, ladder z<-3, BTC gate z192(15m)<-1, fill_window 3x15m.
Reference: C6@1h (n=48, z=-2.0, hold=8).

If the direction does not hold on v2, the single FRESH12v3 validation is NOT spent.

All prints ASCII-only.
"""
from __future__ import annotations

import math
from statistics import mean, pstdev

import explore_m6_lib as lib
from explore_m6_lib import Cfg, basic_stats, portfolio, run_set
from explore_m9_lib import run_tf

C6 = dict(ladder_z=-3.0, btc_mode="req_z", btc_z=-1.0)
H1 = Cfg(n=48, entry_z=-2.0, max_hold=8, **C6)                      # C6@1h
CAND = Cfg(n=192, entry_z=-2.5, max_hold=32, **C6)                  # candidate 15m

FRESH12V2 = ["WIF", "JUP", "PYTH", "JTO", "WLD", "STX",
             "KAS", "LDO", "MKR", "ETHFI", "ENA", "AUCTION"]


def run(cfg, tf, total, symbols, fm):
    c = Cfg(**{**cfg.__dict__, "fee_model": fm})
    if tf == "1h":
        # CACHE может содержать 15m-данные от run_tf -> принудительно перечитать 1h
        for s in list(symbols) + ["BTC"]:
            lib.CACHE.pop(s, None)
        lib._BTC = None
        return run_set(symbols, c)
    return run_tf(symbols, tf, total, c)


def paired(symbols, fm):
    diffs = []
    for s in symbols:
        t1 = run(H1, "1h", 4000, [s], fm)
        t2 = run(CAND, "15m", 16000, [s], fm)
        if t1 and t2:
            diffs.append(mean(t.net for t in t2) - mean(t.net for t in t1))
    md = mean(diffs)
    sd = pstdev(diffs) or 1e-9
    return md, md / (sd / math.sqrt(len(diffs))), len(diffs)


def line(name, cfg, tf, total, fm):
    tr = run(cfg, tf, total, FRESH12V2, fm)
    s = basic_stats(tr)
    pnl, mdd = portfolio(tr)
    print(f"{name:16s} [{fm:8s}] n={s['n']:4d} win={s['win']:5.1f}% "
          f"net={s['net']*100:+6.3f}% med={s['med']*100:+6.3f}% "
          f"P&L={pnl*100:+6.2f}% MDD={mdd*100:5.2f}%")


def main() -> None:
    print("=== M9-3a. 15m candidate sanity on FRESH12v2 (informational) ===")
    for fm in ("SPOT_BNB", "FUTURES"):
        line("C6@1h", H1, "1h", 4000, fm)
        line("CAND@15m", CAND, "15m", 16000, fm)
    md, t, k = paired(FRESH12V2, "SPOT_BNB")
    print(f"\npaired across {k} coins (SPOT_BNB): CAND-C6@1h = {md*100:+.3f} pp/trade, "
          f"t={t:+.2f}")
    print("(informational only; FRESH12v3 spending decision follows)")


if __name__ == "__main__":
    main()
