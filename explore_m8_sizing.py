"""M8-3: sizing variants on C6 trades (EXPL18).

Post-processing of the same trade list (entry/exit bars align across coins -
same 4000-bar 1h grid), fee model SPOT_BNB (live bot is spot) + FUTURES ref:

  S0  fixed 5% of capital per trade (production)
  S1  z-scaled: trigger z in (-3,-2] -> 3%, z<-3 -> 7%
  S2  vol-targeting: w = 5% * median_sigma48/sigma_i, clipped to [2.5%, 10%]
      (equal risk per trade instead of equal fraction)
  S3  correlation cap: max N concurrent positions, N in {3,5,10,inf}
      (M4.4 found caps harmful pre-ladder/pre-BTC-gate; recheck on C6)

Metrics: portfolio P&L (% of capital, no compounding), MDD, P&L/MDD, n taken.
All prints ASCII-only.
"""
from __future__ import annotations

from statistics import median

from explore_m6_lib import EXPL18, Cfg, run_set

C6 = Cfg(ladder_z=-3.0, btc_mode="req_z", btc_z=-1.0)


def curve_stats(trades_w):
    """trades_w: list of (exit_i, w*net). P&L/MDD without compounding."""
    by_exit = {}
    for ei, pnl in trades_w:
        by_exit[ei] = by_exit.get(ei, 0.0) + pnl
    pnl = peak = mdd = 0.0
    for i in sorted(by_exit):
        pnl += by_exit[i]
        peak = max(peak, pnl)
        mdd = max(mdd, peak - pnl)
    return pnl, mdd


def cap_concurrent(trades, n_max):
    """Skip trades whose entry bar already has n_max open positions."""
    taken = []
    events = []
    for t in trades:
        events.append((t.entry_i, 1, t))   # open
        events.append((t.exit_i, -1, t))   # close
    events.sort(key=lambda e: (e[0], e[1]))  # closes (-1) before opens (+1)
    open_ids = set()
    for bar, d, t in events:
        key = id(t)
        if d == -1:
            open_ids.discard(key)
        else:
            if len(open_ids) < n_max:
                open_ids.add(key)
                taken.append(t)
    return taken


def show(label, trades_w, n_taken, n_total):
    pnl, mdd = curve_stats(trades_w)
    rtd = pnl / mdd if mdd > 0 else float("inf")
    print(f"{label:34s} P&L={pnl*100:+7.2f}% MDD={mdd*100:5.2f}% "
          f"P&L/MDD={rtd:5.2f} taken={n_taken}/{n_total}")


def main() -> None:
    for fm in ("SPOT_BNB", "FUTURES"):
        trades = run_set(EXPL18, Cfg(**{**C6.__dict__, "fee_model": fm}))
        n_total = len(trades)
        print(f"\n=== M8-3. Sizing on C6 (EXPL18, {fm}) — n={n_total} ===")

        # S0 fixed 5%
        show("S0 fixed 5%", [(t.exit_i, 0.05 * t.net) for t in trades], n_total, n_total)

        # S1 z-scaled 3%/7%
        def wz(t):
            return 0.07 if t.entry_z_val < -3.0 else 0.03
        show("S1 z-scaled 3%/7%", [(t.exit_i, wz(t) * t.net) for t in trades],
             n_total, n_total)

        # S2 vol targeting
        med_vol = median(t.entry_vol for t in trades) or 1e-9
        def wv(t):
            return min(0.10, max(0.025, 0.05 * med_vol / (t.entry_vol or 1e-9)))
        show("S2 vol-target (clip 2.5-10%)",
             [(t.exit_i, wv(t) * t.net) for t in trades], n_total, n_total)

        # S3 correlation cap
        for n_max in (3, 5, 10, 10**9):
            taken = cap_concurrent(trades, n_max)
            lab = "inf" if n_max > 10**6 else str(n_max)
            show(f"S3 max {lab} concurrent",
                 [(t.exit_i, 0.05 * t.net) for t in taken], len(taken), n_total)


if __name__ == "__main__":
    main()
