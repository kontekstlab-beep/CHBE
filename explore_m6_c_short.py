"""M6-C: короткая сторона (EXPL18).

Зеркало лонга: z > +2.0 → шорт (лимит-продажа на close, fill по high бара),
выход z <= 0, катастроф-стоп +8%, тайм-стоп 8 баров. На споте не реализуемо —
ответ нужен для будущего фьючерсного режима. Сравнение силы с лонгом.

    python explore_m6_c_short.py
"""
from __future__ import annotations

from explore_m6_lib import EXPL18, Cfg, per_coin_table, report, run_set


def main() -> None:
    print("=== C. Лонг vs шорт (EXPL18, FUTURES) ===")
    report("long  z<-2.0 (baseline)", run_set(EXPL18, Cfg(side="long")))
    report("short z>+2.0 (зеркало)", run_set(EXPL18, Cfg(side="short")))
    print("\n-- чувствительность шорта к порогу --")
    for ez in (-1.5, -2.0, -2.5, -3.0):
        report(f"short z>{-ez:+.1f}", run_set(EXPL18, Cfg(side="short", entry_z=ez)),
               show_port=False)
    print("\n-- чувствительность шорта к комиссиям --")
    for fm in ("FUTURES", "SPOT_BNB", "SPOT_VIP0"):
        report(f"short [{fm}]", run_set(EXPL18, Cfg(side="short", fee_model=fm)),
               show_port=False)
    print("\n-- шорт по монетам (FUTURES) --")
    per_coin_table(EXPL18, Cfg(side="short"))


if __name__ == "__main__":
    main()
