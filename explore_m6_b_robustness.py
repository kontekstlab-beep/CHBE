"""M6-B: карта устойчивости параметров (EXPL18).

Сетка: z входа ∈ {-1.5,-2.0,-2.5,-3.0} × SMA ∈ {24,48,96} × max_hold ∈ {8,16,24}.
Цель НЕ оптимизация, а ГЛАДКОСТЬ: edge должен жить в окрестности текущей точки
(SMA48/z-2.0/hold8). Обрыв = хрупкость. Комиссии FUTURES.

    python explore_m6_b_robustness.py
"""
from __future__ import annotations

from explore_m6_lib import EXPL18, Cfg, report, run_set


def main() -> None:
    zs = (-1.5, -2.0, -2.5, -3.0)
    ns = (24, 48, 96)
    holds = (8, 16, 24)
    print("=== B. Карта устойчивости: нетто%/сделку (EXPL18, FUTURES) ===")
    grid = {}
    for n in ns:
        for h in holds:
            print(f"\n-- SMA{n}, max_hold={h} --")
            for ez in zs:
                tr = run_set(EXPL18, Cfg(n=n, entry_z=ez, max_hold=h))
                s = report(f"z={ez}", tr, show_port=False)
                grid[(n, ez, h)] = s
    print("\n=== Сводная таблица нетто%/сделку (строки z, колонки SMA/hold) ===")
    hdr = "z\\SMA,hold  " + "  ".join(f"{n}/{h:2d}" for n in ns for h in holds)
    print(hdr)
    for ez in zs:
        row = f"{ez:8.1f}  "
        for n in ns:
            for h in holds:
                s = grid[(n, ez, h)]
                row += f" {s['net']*100:+5.2f}" if s["n"] >= 40 else "   n/a"
        print(row)
    print("\nТа же таблица: медиана по монетам, %/сделку")
    print(hdr)
    for ez in zs:
        row = f"{ez:8.1f}  "
        for n in ns:
            for h in holds:
                s = grid[(n, ez, h)]
                row += f" {s['med']*100:+5.2f}" if s["n"] >= 40 else "   n/a"
        print(row)
    print("\nТа же таблица: число сделок")
    print(hdr)
    for ez in zs:
        row = f"{ez:8.1f}  "
        for n in ns:
            for h in holds:
                row += f" {grid[(n, ez, h)]['n']:5d}"
        print(row)


if __name__ == "__main__":
    main()
