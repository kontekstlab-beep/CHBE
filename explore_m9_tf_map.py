"""M9-1: clean timeframe map (EXPL18).

C6 logic recomputed on 15m and 5m. Equivalents of the 1h production config:
  SMA48@1h (2 days)  -> SMA192@15m, SMA576@5m
  max_hold 8@1h (8h) -> 32@15m, 96@5m
  stop -8% unchanged; ladder z<-3; BTC gate z(n)<-1 on the SAME timeframe;
  fill_window=3 bars of the TF (production TTL semantics).
Grid around the equivalent: window {0.5x, 1x, 2x}, z {-2.0, -2.5},
hold {4h, 8h, 16h in TF bars}. Question: where does the edge live after fees?

All prints ASCII-only.
"""
from __future__ import annotations

from explore_m6_lib import EXPL18, Cfg, basic_stats, portfolio
from explore_m9_lib import run_tf

C6 = dict(ladder_z=-3.0, btc_mode="req_z", btc_z=-1.0)

GRID = {
    "1h":  dict(total=4000,  ns=(24, 48, 96),      holds=(4, 8, 16)),
    "15m": dict(total=16000, ns=(96, 192, 384),    holds=(16, 32, 64)),
    "5m":  dict(total=48000, ns=(288, 576, 1152),  holds=(48, 96, 192)),
}


def one(tf, n, ez, hold, fm):
    g = GRID[tf]
    cfg = Cfg(n=n, entry_z=ez, max_hold=hold, fee_model=fm, **C6)
    tr = run_tf(EXPL18, tf, g["total"], cfg)
    s = basic_stats(tr)
    pnl, mdd = portfolio(tr)
    return s, pnl, mdd


def main() -> None:
    import sys
    only = sys.argv[1] if len(sys.argv) > 1 else None   # '1h' | '15m' | '5m'
    for tf in ("1h", "15m", "5m"):
        if only and tf != only:
            continue
        g = GRID[tf]
        for fm in ("SPOT_BNB", "FUTURES"):
            print(f"\n=== TF {tf} [{fm}] (window/z/hold -> net%/trade, n, med, MDD) ===")
            for n in g["ns"]:
                for ez in (-2.0, -2.5):
                    for hold in g["holds"]:
                        s, pnl, mdd = one(tf, n, ez, hold, fm)
                        pfs = "inf" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
                        print(f"n={n:4d} z={ez:4.1f} h={hold:4d} | "
                              f"trades={s['n']:4d} win={s['win']:5.1f}% "
                              f"net={s['net']*100:+7.3f}% pf={pfs:>5s} "
                              f"med={s['med']*100:+6.3f}% "
                              f"P&L={pnl*100:+6.2f}% MDD={mdd*100:5.2f}%")


if __name__ == "__main__":
    main()
