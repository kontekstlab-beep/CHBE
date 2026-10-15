"""M10-B: Donchian breakdown short. EXPL18, 1h, extended data.

Short when close < min(low of previous 48 bars). Exit: close > max(high of
previous 12 bars), or time 24h; catastrophe stop +6%.

All prints ASCII-only.
"""
from __future__ import annotations

from explore_m6_lib import EXPL18
from explore_m10_lib import load_ext, report, short_bt


def main() -> None:
    print("=== M10-B. Breakdown short: close<min(low,48), exit max(high,12) / 24h ===")
    for ch in (48,):
        for exn in (12,):
            for stop in (0.06,):
                all_tr = []
                for s in EXPL18:
                    d = load_ext(s)
                    c, lo, h = d["c"], d["lo"], d["h"]

                    def enter(i, c=c, lo=lo, ch=ch):
                        return c[i] < min(lo[i - ch:i])

                    def exit_fn(k, c=c, h=h, exn=exn):
                        return c[k] > max(h[k - exn:k])

                    all_tr += short_bt(d, enter, exit_fn, stop=stop, hold=24,
                                       start=ch)
                report(f"ch48/ex{exn}/stop+{stop*100:.0f}%", all_tr)


if __name__ == "__main__":
    main()
