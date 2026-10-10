"""M7-2: is the hour anomaly an artifact? (EXPL18)

Checks:
  A) day clustering: P&L of bad-hour trades by UTC day - is the minus made by
     2-3 unlucky days (news cluster) or spread across many days?
  B) multiple comparisons: permutation test (shuffle entry-hour labels among
     trades 10000x; how often does a random hour get such a minus?) + Bonferroni.
  C) mechanism hypotheses:
     (a) funding (Binance futures 00/08/16 UTC): are bad hours a post-funding
         window? (spot has NO funding - if the mechanism is funding-driven,
         the filter is irrelevant for the spot bot!)
     (b) liquidity: mean volume and bar range% by hour - are bad hours
         anomalously thin/volatile?
     (c) exits: stop/time/reversion mix; MFE/MAE profile of bad-hour trades
         vs normal ones (bounce came but late, or no bounce at all?).

All prints ASCII-only.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from statistics import mean, median

from explore_m6_lib import EXPL18, Cfg, basic_stats, load, run_set

BAD = {1, 6}
C6 = Cfg(ladder_z=-3.0, btc_mode="req_z", btc_z=-1.0)


def day_of(ts_ms: int) -> int:
    return ts_ms // 86_400_000


def part_a(trades) -> None:
    print("=== M7-2A. Day clustering of bad-hour trades (hours 1,6 UTC) ===")
    by_day = defaultdict(float)
    cnt = defaultdict(int)
    for t in trades:
        if t.hour in BAD:
            d = day_of(load(t.sym)["ts"][t.entry_i])
            by_day[d] += t.net
            cnt[d] += 1
    tot = sum(by_day.values())
    days = sorted(by_day.items(), key=lambda kv: kv[1])
    print(f"bad-hour trades: n={sum(cnt.values())} on {len(by_day)} distinct days, "
          f"total P&L = {tot*100:+.2f} (sum of per-trade net fractions)")
    w3 = sum(v for _, v in days[:3])
    print(f"worst 3 days contribute {w3*100:+.2f} "
          f"({w3/tot*100 if tot else 0:.0f}% of total bad-hour P&L)")
    neg_days = sum(1 for _, v in days if v < 0)
    print(f"negative days: {neg_days}/{len(by_day)}")
    print("worst 8 days (date, n, P&L%):")
    import datetime
    for d, v in days[:8]:
        dt = datetime.datetime.fromtimestamp(d * 86400, datetime.UTC).date()
        print(f"  {dt} n={cnt[d]:3d} pnl={v*100:+7.2f}")


def welch_t(a, b):
    ma, mb = mean(a), mean(b)
    va = sum((x - ma) ** 2 for x in a) / max(1, len(a) - 1)
    vb = sum((x - mb) ** 2 for x in b) / max(1, len(b) - 1)
    se = math.sqrt(va / len(a) + vb / len(b)) or 1e-12
    return (ma - mb) / se


def part_b(trades) -> None:
    print("\n=== M7-2B. Multiple comparisons ===")
    nets = [t.net for t in trades]
    hours = [t.hour for t in trades]
    by_h = defaultdict(list)
    for h, x in zip(hours, nets):
        by_h[h].append(x)

    def min_hour_mean(hl):
        bh = defaultdict(list)
        for h, x in zip(hl, nets):
            bh[h].append(x)
        cands = [mean(v) for v in bh.values() if len(v) >= 20]
        return min(cands) if cands else 0.0

    obs = min_hour_mean(hours)
    rng = random.Random(42)
    N = 10000
    worse = 0
    hl = hours[:]
    for _ in range(N):
        rng.shuffle(hl)
        if min_hour_mean(hl) <= obs:
            worse += 1
    print(f"permutation test ({N} shuffles): observed min per-hour mean = {obs*100:+.3f}%")
    print(f"  p-value = {worse}/{N} = {worse/N:.4f} "
          f"(fraction of shuffles with an equally bad hour)")

    bad = [t.net for t in trades if t.hour in BAD]
    rest = [t.net for t in trades if t.hour not in BAD]
    t_stat = welch_t(bad, rest)
    # normal approximation for p (n large)
    p_raw = 0.5 * math.erfc(abs(t_stat) / math.sqrt(2))
    print(f"hours {{1,6}} vs rest: n={len(bad)} vs {len(rest)}, "
          f"mean {mean(bad)*100:+.3f}% vs {mean(rest)*100:+.3f}%, "
          f"t={t_stat:+.2f}, p_raw~{p_raw:.2e}, Bonferroni x24 = {min(1.0, p_raw*24):.2e}")


def part_c(trades) -> None:
    print("\n=== M7-2C. Mechanism ===")
    # (a) funding windows
    print("-- (a) funding hypothesis (funding at 00/08/16 UTC): net%/trade by window --")
    for label, hs in [("bad {1,6}", {1, 6}),
                      ("post-fund00 {0,1,2}", {0, 1, 2}),
                      ("post-fund08 {8,9,10}", {8, 9, 10}),
                      ("post-fund16 {16,17,18}", {16, 17, 18}),
                      ("rest", set(range(24)) - {1, 6})]:
        sub = [t for t in trades if t.hour in hs]
        s = basic_stats(sub)
        print(f"  {label:22s} n={s['n']:4d} net={s['net']*100:+7.3f}% win={s['win']:5.1f}%")

    # (b) liquidity by hour
    print("-- (b) liquidity: mean relative volume and range% by hour (EXPL18) --")
    vol_h = defaultdict(list)
    rng_h = defaultdict(list)
    for sym in EXPL18:
        d = load(sym)
        mv = mean(d["v"]) or 1e-9
        for i in range(len(d["c"])):
            h = (d["ts"][i] // 3_600_000) % 24
            vol_h[h].append(d["v"][i] / mv)
            rng_h[h].append((d["h"][i] - d["lo"][i]) / d["c"][i])
    print(f"  {'hr':>3s} {'relvol':>7s} {'range%':>7s}")
    for h in range(24):
        mark = " <-- BAD" if h in BAD else ""
        print(f"  {h:3d} {mean(vol_h[h]):7.2f} {mean(rng_h[h])*100:7.3f}{mark}")

    # (c) exits + MFE/MAE
    print("-- (c) exit mix and MFE/MAE profile --")
    for label, sub in [("bad {1,6}", [t for t in trades if t.hour in BAD]),
                       ("rest", [t for t in trades if t.hour not in BAD])]:
        if not sub:
            continue
        mix = defaultdict(int)
        for t in sub:
            mix[t.reason] += 1
        n = len(sub)
        bounced_late = sum(1 for t in sub if t.mfe > 0.005 and t.net <= 0) / n * 100
        print(f"  {label:10s} n={n:4d} | stops={mix['stop']/n*100:4.1f}% "
              f"time={mix['time']/n*100:4.1f}% rev={mix['reversion']/n*100:4.1f}% | "
              f"MFE avg={mean(t.mfe for t in sub)*100:+6.2f}% med={median(t.mfe for t in sub)*100:+6.2f}% | "
              f"MAE avg={mean(t.mae for t in sub)*100:+6.2f}% med={median(t.mae for t in sub)*100:+6.2f}% | "
              f"bounce>0.5% but closed red: {bounced_late:4.1f}%")


def main() -> None:
    trades = run_set(EXPL18, C6)
    print(f"C6 trades on EXPL18: {len(trades)}")
    part_a(trades)
    part_b(trades)
    part_c(trades)


if __name__ == "__main__":
    main()
