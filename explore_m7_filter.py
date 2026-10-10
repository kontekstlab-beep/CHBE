"""M7-3: hour filter design (EXPL18 only; winner frozen before FRESH12v2).

Candidates (C6 = production: ladder z<-3 + BTC z48<-1):
  F0  C6 without hour filter (reference)
  F1  C6 + block entries at hours {1,6} UTC
  F2  C6 + block entries at hours {1,6,19} UTC (19 added per M7-1 data)
  F3  F1 + ladder also blocked at bad hours (ladder_hours=True)
  F4  F2 + ladder also blocked at bad hours

Criterion: net/trade and portfolio P&L/MDD must improve; lost trades must pay
for themselves (P&L up, not just net/trade). Fees: FUTURES and SPOT_BNB
(the live bot is on spot).

All prints ASCII-only.
"""
from __future__ import annotations

from explore_m6_lib import EXPL18, Cfg, basic_stats, portfolio, run_set

C6 = dict(ladder_z=-3.0, btc_mode="req_z", btc_z=-1.0)

CANDS = [
    ("F0 C6 no filter",          Cfg(**C6)),
    ("F1 block {1,6}",           Cfg(**C6, hours=set(range(24)) - {1, 6})),
    ("F2 block {1,6,19}",        Cfg(**C6, hours=set(range(24)) - {1, 6, 19})),
    ("F3 F1+ladder too",         Cfg(**C6, hours=set(range(24)) - {1, 6},
                                     ladder_hours=True)),
    ("F4 F2+ladder too",         Cfg(**C6, hours=set(range(24)) - {1, 6, 19},
                                     ladder_hours=True)),
]


def line(name, cfg, fm):
    c = Cfg(**{**cfg.__dict__, "fee_model": fm})
    tr = run_set(EXPL18, c)
    s = basic_stats(tr)
    pnl, mdd = portfolio(tr)
    pfs = "inf" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    print(f"{name:20s} [{fm:8s}] n={s['n']:4d} win={s['win']:5.1f}% "
          f"net={s['net']*100:+6.3f}% pf={pfs:>5s} med={s['med']*100:+6.3f}% "
          f"P&L={pnl*100:+6.2f}% MDD={mdd*100:5.2f}% worst={s['worst']*100:6.2f}%")
    return s, pnl, mdd


def main() -> None:
    print("=== M7-3. Filter design on EXPL18 ===")
    base_n = None
    for name, cfg in CANDS:
        for fm in ("FUTURES", "SPOT_BNB"):
            s, pnl, mdd = line(name, cfg, fm)
            if base_n is None:
                base_n = s["n"]
        print(f"    trades vs F0: n={s['n']} (lost {base_n - s['n']})")


if __name__ == "__main__":
    main()
