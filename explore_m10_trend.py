"""M10-A: trend-filter short (continuation). EXPL18, 1h, extended data.

Short when close < SMA96 AND 24h return < -X% (X in {4,6,8}).
Exit: close back above SMA24 (trailing), or time 24h; catastrophe stop +8%.
Entry at next bar open (taker) - momentum needs immediacy.

All prints ASCII-only.
"""
from __future__ import annotations

from explore_m6_lib import EXPL18
from explore_m10_lib import load_ext, report, short_bt, sma_series


def main() -> None:
    print("=== M10-A. Trend short: close<SMA96 & ret24<-X%, exit SMA24 / 24h / stop+8% ===")
    for X in (0.04, 0.06, 0.08):
        for stop in (0.08,):
            all_tr = []
            for s in EXPL18:
                d = load_ext(s)
                c = d["c"]
                s96 = sma_series(c, 96)
                s24 = sma_series(c, 24)

                def enter(i, d=d, c=c, s96=s96, X=X):
                    return (s96[i] is not None and c[i] < s96[i]
                            and c[i] / c[i - 24] - 1 < -X)

                def exit_fn(k, c=c, s24=s24):
                    return s24[k] is not None and c[k] > s24[k]

                all_tr += short_bt(d, enter, exit_fn, stop=stop, hold=24)
            report(f"X={X*100:.0f}% stop+{stop*100:.0f}%", all_tr)


if __name__ == "__main__":
    main()
