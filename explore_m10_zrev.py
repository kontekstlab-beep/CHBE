"""M10-C: overbought-reversal short WITH confirmation (M6-C died without it).

Short when z48 > +1.5 AND two consecutive red bars (close<open twice).
Exit: z48 <= 0, or time stop; catastrophe stop +8%.
Cross-check vs M6-C (plain z>+2 short was ~0 net).

All prints ASCII-only.
"""
from __future__ import annotations

from explore_m6_lib import EXPL18
from explore_m9_lib import zseries_fast
from explore_m10_lib import load_ext, report, short_bt


def main() -> None:
    print("=== M10-C. z48>+1.5 + two red bars -> short; exit z<=0 / time / stop+8% ===")
    for zt in (1.5, 2.0):
        for hold in (8, 24):
            all_tr = []
            for s in EXPL18:
                d = load_ext(s)
                c, o = d["c"], d["o"]
                z = zseries_fast(c, 48)

                def enter(i, z=z, c=c, o=o, zt=zt):
                    return (z[i] is not None and z[i] > zt
                            and c[i] < o[i] and c[i - 1] < o[i - 1])

                def exit_fn(k, z=z):
                    return z[k] is not None and z[k] <= 0.0

                all_tr += short_bt(d, enter, exit_fn, stop=0.08, hold=hold)
            report(f"z>+{zt} hold{hold}", all_tr)


if __name__ == "__main__":
    main()
