"""M8-2: exit hypotheses on top of C6 (EXPL18, FUTURES + SPOT_BNB).

  E0  C6 reference (exit z>=0 at close)
  E1  limit target at SMA*k, k in {0.97, 1.00, 1.03} (catch bounce earlier/later)
  E2  time-stop 8 vs 12 bars (MFE-informed)
  E3  partial 50% at z>=-1 (recheck on C6; was neutral on baseline in M6)
  E4  trailing after touching z>=0: hold 1-2 more bars, exit on first down bar

All prints ASCII-only.
"""
from __future__ import annotations

from explore_m6_lib import EXPL18, Cfg, basic_stats, portfolio, run_set

C6 = dict(ladder_z=-3.0, btc_mode="req_z", btc_z=-1.0)

CANDS = [
    ("E0 C6 reference",        Cfg(**C6)),
    ("E1a target SMA*0.97",    Cfg(**C6, target_mult=0.97)),
    ("E1b target SMA*1.00",    Cfg(**C6, target_mult=1.00)),
    ("E1c target SMA*1.03",    Cfg(**C6, target_mult=1.03)),
    ("E2  hold12",             Cfg(**C6, max_hold=12)),
    ("E3  partial50@z>=-1",    Cfg(**C6, partial_z=-1.0)),
    ("E4a trail 1 bar",        Cfg(**C6, trail_bars=1)),
    ("E4b trail 2 bars",       Cfg(**C6, trail_bars=2)),
]


def line(name, cfg, fm):
    c = Cfg(**{**cfg.__dict__, "fee_model": fm})
    tr = run_set(EXPL18, c)
    s = basic_stats(tr)
    pnl, mdd = portfolio(tr)
    pfs = "inf" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    print(f"{name:22s} [{fm:8s}] n={s['n']:4d} win={s['win']:5.1f}% "
          f"net={s['net']*100:+6.3f}% pf={pfs:>5s} med={s['med']*100:+6.3f}% "
          f"P&L={pnl*100:+6.2f}% MDD={mdd*100:5.2f}% worst={s['worst']*100:6.2f}%")


def main() -> None:
    print("=== M8-2. Exit hypotheses on C6 (EXPL18) ===")
    for name, cfg in CANDS:
        for fm in ("FUTURES", "SPOT_BNB"):
            line(name, cfg, fm)


if __name__ == "__main__":
    main()
