"""M8-1: exit audit via MFE/MAE for C6 on EXPL18.

Questions:
  A) MFE distribution vs captured P&L: how much of the bounce do we capture?
  B) what fraction of trades bounced BEYOND our SMA target (money left)?
  C) time-stops: how many were already green at exit / had a bounce during life
     but closed red (exit too early vs no bounce)?
  D) stop-outs (-8%): how many bounced back above entry within 24h after exit
     (false breakdowns the stop threw away)?

All prints ASCII-only.
"""
from __future__ import annotations

from statistics import mean, median

from explore_m6_lib import EXPL18, Cfg, basic_stats, load, run_set

C6 = Cfg(ladder_z=-3.0, btc_mode="req_z", btc_z=-1.0)


def pct(x):
    return f"{x*100:.1f}%"


def main() -> None:
    trades = run_set(EXPL18, C6)
    s = basic_stats(trades)
    print(f"=== M8-1. Exit audit: C6 on EXPL18 (n={s['n']}, net={s['net']*100:+.3f}%/trade) ===")

    print("\n--- A. MFE vs captured ---")
    mfe = sorted(t.mfe for t in trades)
    n = len(mfe)
    print(f"MFE percentiles: p10={mfe[n//10]*100:+.2f}% p25={mfe[n//4]*100:+.2f}% "
          f"p50={mfe[n//2]*100:+.2f}% p75={mfe[3*n//4]*100:+.2f}% p90={mfe[9*n//10]*100:+.2f}%")
    print(f"gross captured: mean={mean(t.gross for t in trades)*100:+.3f}%")
    util = [t.gross / t.mfe for t in trades if t.mfe > 0.003]
    print(f"utilization gross/MFE (trades with MFE>0.3%): mean={mean(util)*100:.0f}% "
          f"median={median(util)*100:.0f}%")
    left = sum(1 for t in trades if t.mfe > t.gross + 0.005) / n
    print(f"trades that left >0.5pp on the table (MFE > gross + 0.5pp): {pct(left)}")

    print("\n--- B. bounce beyond SMA target ---")
    rev = [t for t in trades if t.reason == "reversion"]
    nonrev = [t for t in trades if t.reason != "reversion"]
    print(f"reversion exits: {len(rev)} ({pct(len(rev)/n)}), time: "
          f"{sum(1 for t in trades if t.reason=='time')}, stop: "
          f"{sum(1 for t in trades if t.reason=='stop')}")
    past = sum(1 for t in rev if t.mfe > t.gross + 0.005)
    print(f"reversion exits where price went >0.5pp ABOVE our SMA target: "
          f"{past}/{len(rev)} = {pct(past/len(rev))}")
    would_rev = sum(1 for t in nonrev if t.mfe > 0.003)
    print(f"NON-reversion exits that still saw a >0.3% bounce during life: "
          f"{would_rev}/{len(nonrev)} = {pct(would_rev/len(nonrev))}")

    print("\n--- C. time-stop anatomy ---")
    tim = [t for t in trades if t.reason == "time"]
    green = sum(1 for t in tim if t.gross > 0)
    had_bounce_red = sum(1 for t in tim if t.mfe > 0.005 and t.gross <= 0)
    no_bounce = sum(1 for t in tim if t.mfe <= 0.003)
    print(f"time exits: n={len(tim)} | green at exit: {pct(green/len(tim))} | "
          f"bounce>0.5% existed but closed red: {pct(had_bounce_red/len(tim))} | "
          f"no bounce at all (MFE<=0.3%): {pct(no_bounce/len(tim))}")
    print(f"time exits net: mean={mean(t.net for t in tim)*100:+.3f}%")

    print("\n--- D. stop-out aftermath (bounce above entry within 24 bars) ---")
    stops = [t for t in trades if t.reason == "stop"]
    rec = 0
    for t in stops:
        d = load(t.sym)
        hi = d["h"]
        k0 = t.exit_i + 1
        fut = hi[k0:k0 + 24]
        if fut and max(fut) > t.entry_px:
            rec += 1
    print(f"stop exits: n={len(stops)} | bounced back above entry within 24h: "
          f"{rec} = {pct(rec/len(stops)) if stops else '-'}")
    print(f"stop exits net: mean={mean(t.net for t in stops)*100:+.3f}%" if stops
          else "no stops")


if __name__ == "__main__":
    main()
