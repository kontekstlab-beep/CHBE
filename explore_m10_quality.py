"""M10-2: quality checks for the short candidates (EXPL18, extended data).

1) modest parameter extension: A (hold 24/48), B (stop 6/8);
2) regime split: monthly P&L + the Oct 12-13 crash days specifically;
3) complementarity: daily P&L of the candidate vs daily P&L of C6-long
   (Pearson correlation; a hedge should be NEGATIVELY correlated).

All prints ASCII-only.
"""
from __future__ import annotations

import explore_m6_lib as lib
from explore_m6_lib import EXPL18, Cfg, run_set
from explore_m10_lib import (daily_pnl, load_ext, pearson, report, short_bt,
                             sma_series, stats_str)
from explore_m9_lib import zseries_fast

DAY = 86_400_000


def cand_A(X, hold):
    out = []
    for s in EXPL18:
        d = load_ext(s)
        c = d["c"]
        s96 = sma_series(c, 96)
        s24 = sma_series(c, 24)
        out += short_bt(d,
                        lambda i: (s96[i] is not None and c[i] < s96[i]
                                   and c[i] / c[i - 24] - 1 < -X),
                        lambda k: s24[k] is not None and c[k] > s24[k],
                        stop=0.08, hold=hold)
    return out


def cand_B(stop):
    out = []
    for s in EXPL18:
        d = load_ext(s)
        c, lo, h = d["c"], d["lo"], d["h"]
        out += short_bt(d,
                        lambda i: c[i] < min(lo[i - 48:i]),
                        lambda k: c[k] > max(h[k - 12:k]),
                        stop=stop, hold=24, start=48)
    return out


def cand_C(zt, hold):
    out = []
    for s in EXPL18:
        d = load_ext(s)
        c, o = d["c"], d["o"]
        z = zseries_fast(c, 48)
        out += short_bt(d,
                        lambda i: (z[i] is not None and z[i] > zt
                                   and c[i] < o[i] and c[i - 1] < o[i - 1]),
                        lambda k: z[k] is not None and z[k] <= 0.0,
                        stop=0.08, hold=hold)
    return out


def c6_daily():
    """Daily P&L of the C6 long strategy on the SAME extended window."""
    for s in EXPL18:
        lib.CACHE[s] = load_ext(s)
    lib.CACHE["BTC"] = load_ext("BTC")
    lib._BTC = None                      # rebuild BTC ctx on extended data
    tr = run_set(EXPL18, Cfg(ladder_z=-3.0, btc_mode="req_z", btc_z=-1.0))
    d_map = {s: lib.CACHE[s] for s in EXPL18}
    return daily_pnl(tr, d_map)


def regime(label, trades, d_map):
    by_day = daily_pnl(trades, d_map)
    by_month = {}
    import datetime
    for day, v in by_day.items():
        m = datetime.datetime.fromtimestamp(day * 86400, datetime.UTC).strftime("%Y-%m")
        by_month[m] = by_month.get(m, 0.0) + v
    print(f"  {label}: monthly P&L (sum of net, pp): "
          + " ".join(f"{m}={v*100:+.1f}" for m, v in sorted(by_month.items())))
    crash = [d for d in by_day if 20261012 <= int(datetime.datetime.fromtimestamp(
        d * 86400, datetime.UTC).strftime("%Y%m%d")) <= 20261013]
    crash_pnl = sum(by_day[d] for d in crash)
    print(f"  {label}: crash days 12-13 Oct P&L = {crash_pnl*100:+.2f} pp "
          f"({len(crash)} days in data)")
    return by_day


def main() -> None:
    print("=== M10-2a. Extended parameter sweep (EXPL18) ===")
    for hold in (24, 48):
        report(f"A X=4% hold{hold}", cand_A(0.04, hold))
    report("B stop+8%", cand_B(0.08))
    report("C z>+2.0 hold8", cand_C(2.0, 8))

    print("\n=== M10-2b. Regime split (monthly + crash days) ===")
    d_map = {s: load_ext(s) for s in EXPL18}
    cands = [("A X=4% h24", cand_A(0.04, 24)),
             ("B stop6", cand_B(0.06)),
             ("C z2 h24", cand_C(2.0, 24))]
    dailys = {}
    for name, tr in cands:
        dailys[name] = regime(name, tr, d_map)

    print("\n=== M10-2c. Complementarity: daily P&L corr vs C6-long ===")
    dc6 = c6_daily()
    tot6 = sum(dc6.values())
    print(f"C6-long daily P&L total over window: {tot6*100:+.1f} pp")
    for name, dd in dailys.items():
        days = sorted(set(dd) | set(dc6))
        x = [dd.get(d, 0.0) for d in days]
        y = [dc6.get(d, 0.0) for d in days]
        print(f"  corr({name}, C6-long) = {pearson(x, y):+.3f}  over {len(days)} days")


if __name__ == "__main__":
    main()
