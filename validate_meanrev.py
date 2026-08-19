"""Финальная проверка mean-reversion гипотезы на всех наборах, ЗАМОРОЖЕНО.

Параметры зафиксированы по результату свипа на TUNING (meanrev.py). Никакого
дальнейшего подбора. Ключевой вердикт — строка HOLDOUT.

    python validate_meanrev.py
"""
from __future__ import annotations

from typing import List

from meanrev import backtest_coin, load, stats
from smartmoney.datasets import HOLDOUT, OOS_USED, TUNING

# ЗАМОРОЖЕННЫЕ параметры (из свипа на TUNING):
N, ENTRY_Z, EXIT_Z, HOLD = 48, -2.0, 0.0, 8


def run(symbols) -> List[float]:
    R = []
    per = []
    for s in symbols:
        r = backtest_coin(load(s), N, ENTRY_Z, EXIT_Z, HOLD)
        R += r
        per.append((s, r))
    return R, per


def line(label, symbols):
    R, per = run(symbols)
    n, wr, m, pf = stats(R)
    pfs = "inf" if pf == float("inf") else f"{pf:.2f}"
    posc = sum(1 for _, r in per if stats(r)[2] > 0)
    print(f"{label:12s}: сделок={n:4d} win={wr:4.1f}% ср.нетто={m*100:+.3f}% "
          f"pf={pfs} монет+={posc}/{len(symbols)}")
    return per


def main() -> None:
    print(f"Заморожено: SMA{N}, entry_z={ENTRY_Z}, exit_z={EXIT_Z}, hold={HOLD}, "
          f"издержки round-trip 0.10%\n")
    line("TUNING", TUNING)
    line("OOS_USED", OOS_USED)
    per = line("HOLDOUT", HOLDOUT)

    print("\nHOLDOUT по монетам:")
    for s, r in sorted(per, key=lambda x: -stats(x[1])[2]):
        n, wr, m, pf = stats(r)
        print(f"  {s:11s} сделок={n:3d} win={wr:4.1f}% ср.нетто={m*100:+.3f}%")

    R, _ = run(HOLDOUT)
    n, wr, m, pf = stats(R)
    print("\n=== Вердикт (HOLDOUT) ===")
    if m > 0.0005 and pf > 1.15:
        print(f"Гипотеза ПОДТВЕРЖДЕНА на независимых данных: +{m*100:.3f}%/сделку, pf={pf:.2f}.")
    elif m > 0:
        print(f"Слабо положительно (+{m*100:.3f}%/сделку) — на грани издержек/шума.")
    else:
        print(f"Не подтвердилась ({m*100:+.3f}%/сделку).")


if __name__ == "__main__":
    main()
