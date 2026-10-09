"""M6-F: варианты выхода (EXPL18, FUTURES).

F1. max_hold 8 vs 16 (24 — в карте B).
F2. Частичная фиксация 50% при z >= -1 (остаток — обычные правила).
F3. Катастроф-стоп 5 / 8 / 12%.

    python explore_m6_f_exits.py
"""
from __future__ import annotations

from explore_m6_lib import EXPL18, Cfg, report, run_set


def main() -> None:
    print("=== F. Варианты выхода (EXPL18, FUTURES) ===")
    report("baseline (hold8, стоп 8%)", run_set(EXPL18, Cfg()))

    print("\n-- F1. Тайм-стоп --")
    for h in (8, 16):
        report(f"max_hold={h}", run_set(EXPL18, Cfg(max_hold=h)))

    print("\n-- F2. Частичная фиксация 50% при z >= -1 --")
    report("partial 50% @ z>=-1", run_set(EXPL18, Cfg(partial_z=-1.0)))

    print("\n-- F3. Катастроф-стоп --")
    for st in (0.05, 0.08, 0.12):
        report(f"стоп {st*100:.0f}%", run_set(EXPL18, Cfg(stop=st)), show_port=False)
    report("без стопа", run_set(EXPL18, Cfg(stop=0.0)), show_port=False)


if __name__ == "__main__":
    main()
