"""M9-2: multi-TF variants (signal on 1h C6, refinement on 15m). EXPL18.

Baseline arm A0 ('close') mirrors production C6 exactly: 1h signal z48<-2 +
BTC gate z48<-1, maker limit at the 1h signal close, fill if lows touch within
3x1h, manage on 1h (ladder z<-3, reversion z>=0, stop -8%, hold 8x1h).
Note: 1h low == min of its 15m lows, so A0 must reproduce lib C6 numbers -
this is the engine self-check.

Arms:
  A1/A2 (MTF-A): entry limit -0.3% / -0.6% below the 1h signal close,
                 TTL 4 x 15m bars (1h), fill by 15m lows;
  B     (MTF-B): A0 but the -8% stop evaluated on 15m lows (finer than 1h);
  C     (MTF-C): wait for the first GREEN 15m bar after the 1h signal
                 (within 4 bars), limit at its close, 1-bar TTL.

All prints ASCII-only.
"""
from __future__ import annotations

from statistics import mean

import explore_m6_lib as lib
from explore_m6_lib import EXPL18, Cfg, Trade, basic_stats, portfolio
from explore_m9_lib import load_tf, setup_tf, zseries_fast

N1H = 48
C6Z, BTCZ, STOP, HOLD, FW = -2.0, -1.0, 0.08, 8, 3
LADDER_Z = -3.0
HOUR = 3_600_000


def mtf_coin(d1h, d15, mode, dip=0.0, stop_15m=False, fm="FUTURES"):
    mk, tk = lib.FEES[fm]
    c1, lo1, ts1 = d1h["c"], d1h["lo"], d1h["ts"]
    L1 = len(c1)
    z1 = zseries_fast(c1, N1H)
    lo15, ts15 = d15["lo"], d15["ts"]
    pos15 = {t: i for i, t in enumerate(ts15)}
    L15 = len(ts15)

    def lows15(ts_from, count):
        """15m lows starting at ts_from (ms), up to `count` bars."""
        j = pos15.get(ts_from)
        if j is None:
            return []
        return lo15[j:j + count]

    btc = lib.btc_ctx()
    trades = []
    signals = fills = 0
    i = N1H
    while i < L1 - 1:
        if z1[i] is None or z1[i] >= C6Z:
            i += 1
            continue
        bz, _ = btc.get(ts1[i], (0.0, 0.0))
        if bz > BTCZ:
            i += 1
            continue
        signals += 1
        t_next = ts1[i] + HOUR
        # --- entry (mode-dependent) ---
        if mode in ("close", "dip"):
            limit = c1[i] * (1 - dip)
            window = lows15(t_next, 12 if mode == "close" else 4)
            hit = next((x for x in window if x <= limit), None)
            if hit is None:
                i += 1
                continue
            entry_bar = i + 1          # conservative: manage from next 1h bar
            entry = limit
        else:  # 'green15'
            j = pos15.get(t_next)
            entry = None
            if j is not None:
                for jj in range(j, min(j + 4, L15 - 1)):
                    if d15["c"][jj] > d15["o"][jj]:
                        if lo15[jj + 1] <= d15["c"][jj]:
                            entry = d15["c"][jj]
                        break
            if entry is None:
                i += 1
                continue
            entry_bar = i + 1
        fills += 1
        # --- management on 1h (C6) ---
        portions = 1
        add_limit = None
        exit_px = reason = None
        mfe = mae = 0.0
        k = entry_bar + 1
        while k < L1:
            zk = z1[k]
            lows_k = lows15(ts1[k], 4) if stop_15m else [lo1[k]]
            bar_lo = min(lows_k) if lows_k else lo1[k]
            mfe = max(mfe, d1h["h"][k] / entry - 1)
            mae = min(mae, bar_lo / entry - 1)
            if bar_lo <= entry * (1 - STOP):
                exit_px, reason = entry * (1 - STOP), "stop"
                break
            if portions < 2:
                if add_limit is not None:
                    if bar_lo <= add_limit:
                        entry = (entry * portions + add_limit) / (portions + 1)
                        portions += 1
                    add_limit = None
                if zk is not None and zk < LADDER_Z and portions < 2:
                    add_limit = c1[k]
            if zk is not None and zk >= 0.0:
                exit_px, reason = c1[k], "reversion"
                break
            if (k - entry_bar) >= HOLD:
                exit_px, reason = c1[k], "time"
                break
            k += 1
        if exit_px is None:
            exit_px, reason, k = c1[L1 - 1], "end", L1 - 1
        gross = exit_px / entry - 1
        fees = mk + (mk if reason == "reversion" else tk)
        trades.append(Trade(d1h["sym"], entry_bar, k, (ts1[i] // HOUR) % 24,
                            reason, gross, fees, gross - fees, mfe, mae))
        i = k + 1
    return trades, signals, fills


def arm(label, mode, dip=0.0, stop_15m=False, fm="FUTURES"):
    all_tr, sig, fil = [], 0, 0
    for s in EXPL18:
        tr, sg, fl = mtf_coin(load_tf(s, "1h", 4000), load_tf(s, "15m", 16000),
                              mode, dip, stop_15m, fm)
        all_tr += tr
        sig += sg
        fil += fl
    s = basic_stats(all_tr)
    pnl, mdd = portfolio(all_tr)
    pfs = "inf" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    print(f"{label:26s} [{fm:8s}] sig={sig:4d} fill={fil/sig*100:4.0f}% "
          f"n={s['n']:4d} win={s['win']:5.1f}% net={s['net']*100:+7.3f}% "
          f"pf={pfs:>5s} med={s['med']*100:+6.3f}% "
          f"P&L={pnl*100:+6.2f}% MDD={mdd*100:5.2f}%")
    return s


def main() -> None:
    setup_tf([], "1h", 4000, N1H)   # BTC gate context (1h, z48)
    print("=== M9-2. Multi-TF arms (EXPL18, signal 1h C6, refinement 15m) ===")
    for fm in ("FUTURES", "SPOT_BNB"):
        arm("A0 close (baseline=C6)", "close", fm=fm)
        arm("A1 limit -0.3%, TTL 4x15m", "dip", dip=0.003, fm=fm)
        arm("A2 limit -0.6%, TTL 4x15m", "dip", dip=0.006, fm=fm)
        arm("B A0 + stop on 15m lows", "close", stop_15m=True, fm=fm)
        arm("C wait green 15m bar", "green15", fm=fm)


if __name__ == "__main__":
    main()
