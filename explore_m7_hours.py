"""M7-1: hour-of-entry anomaly - confirmation and refinement (EXPL18).

M6-E4 finding: trades OPENED at hours 1 and 6 UTC are systematically losing
(n=102, win 19.6%, -1.388%/trade, negative across all 18 coins).

Here:
  A) full 24h map (net/trade, n, winrate, PF) for baseline AND C6
     (production config: ladder z<-3 + BTC z48<-1);
  B) boundaries of the effect: exact bad-hour set {1,6} vs wider blocks
     {0,1,2} / {5,6,7};
  C) robustness to parameters: z in {-2,-2.5,-3} x SMA in {24,48}.

All prints ASCII-only (cp1251-safe).
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean

from explore_m6_lib import EXPL18, Cfg, basic_stats, run_set

C6 = Cfg(ladder_z=-3.0, btc_mode="req_z", btc_z=-1.0)
BASE = Cfg()


def hour_table(label: str, trades) -> dict:
    by_h = defaultdict(list)
    for t in trades:
        by_h[t.hour].append(t)
    print(f"\n--- {label} ---")
    print(f"{'hr':>3s} {'n':>4s} {'win%':>6s} {'net%':>8s} {'pf':>6s}")
    out = {}
    for h in range(24):
        s = basic_stats(by_h.get(h, []))
        out[h] = s
        if s["n"] < 5:
            print(f"{h:3d} {s['n']:4d}      -        -      -")
            continue
        pfs = "inf" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
        print(f"{h:3d} {s['n']:4d} {s['win']:6.1f} {s['net']*100:+8.3f} {pfs:>6s}")
    return out


def block_stats(label: str, trades, hours):
    sub = [t for t in trades if t.hour in hours]
    rest = [t for t in trades if t.hour not in hours]
    s, r = basic_stats(sub), basic_stats(rest)
    print(f"{label:28s} IN:  n={s['n']:4d} win={s['win']:5.1f}% net={s['net']*100:+7.3f}% | "
          f"OUT: n={r['n']:4d} win={r['win']:5.1f}% net={r['net']*100:+7.3f}%")
    return s, r


def main() -> None:
    tr_base = run_set(EXPL18, BASE)
    tr_c6 = run_set(EXPL18, C6)

    print("=== M7-1A. 24h map: BASELINE vs C6 (EXPL18, FUTURES fees) ===")
    hour_table("baseline", tr_base)
    hour_table("C6 (ladder+BTC)", tr_c6)

    print("\n=== M7-1B. Boundaries of the effect (C6) ===")
    block_stats("hours {1,6}", tr_c6, {1, 6})
    block_stats("hours {0,1,2}", tr_c6, {0, 1, 2})
    block_stats("hours {5,6,7}", tr_c6, {5, 6, 7})
    block_stats("hours {0,1,2,5,6,7}", tr_c6, {0, 1, 2, 5, 6, 7})
    block_stats("hours {1,2,6}", tr_c6, {1, 2, 6})

    print("\n=== M7-1C. Robustness: z x SMA (net%/trade, hours {1,6} vs rest) ===")
    for n in (24, 48):
        for ez in (-2.0, -2.5, -3.0):
            tr = run_set(EXPL18, Cfg(n=n, entry_z=ez))
            s, r = block_stats(f"SMA{n} z={ez}", tr, {1, 6})


if __name__ == "__main__":
    main()
