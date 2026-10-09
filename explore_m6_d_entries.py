"""M6-D: варианты входа (EXPL18, FUTURES).

D1. Лесенка: вторая порция 5% при z < -3 (усреднение, лимит на close следующего бара).
D2. Вход с подтверждением: ждать первый зелёный бар (close>open) после триггера
    (окно 3 бара), затем обычная лимитка на close.
D3. Лимитка глубже close: -0.5% и -1.0% (trade-off цена vs fill rate).

    python explore_m6_d_entries.py
"""
from __future__ import annotations

from explore_m6_lib import EXPL18, Cfg, report, run_set


def main() -> None:
    print("=== D. Варианты входа (EXPL18, FUTURES) ===")
    report("baseline (лимит на close)", run_set(EXPL18, Cfg()))

    print("\n-- D1. Лесенка: +5% при z < -3 --")
    report("лесенка z<-3", run_set(EXPL18, Cfg(ladder_z=-3.0)))

    print("\n-- D2. Вход с подтверждением (первый зелёный бар, окно 3) --")
    report("подтверждение", run_set(EXPL18, Cfg(confirm=True)))

    print("\n-- D3. Глубина лимитки --")
    for off in (0.0, 0.005, 0.01):
        report(f"лимит -{off*100:.1f}%", run_set(EXPL18, Cfg(offset=off)))
    print("\nПрим.: лесенка удваивает средний размер позиции в глубоких проливах —"
          " сравнивать нетто/сделку с осторожностью (сделка = 1-2 порции).")


if __name__ == "__main__":
    main()
