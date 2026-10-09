"""M6-A: baseline на свежих данных (EXPL18, данные до 2026-10-09).

Замороженный конфиг paper/config.py: SMA48, entry_z=-2.0, exit_z=0, max_hold=8,
стоп 8%, maker-лимитка на close, fill_window=3.

Вопросы: жив ли edge на свежих данных? Чувствительность к комиссиям
(плоский свип 0/0.02/0.05/0.075/0.1% за сторону + три реальные модели).
Потолок издержек: при какой комиссии за сторону средний нетто-edge умирает.

    python explore_m6_a_baseline.py
"""
from __future__ import annotations

from explore_m6_lib import (EXPL18, Cfg, basic_stats, per_coin_table,
                            portfolio, report, run_set)


def main() -> None:
    base = Cfg()  # замороженный baseline
    print("=== A1. Baseline на EXPL18, модели комиссий (по факту maker/taker) ===")
    for fm in ("FUTURES", "SPOT_BNB", "SPOT_VIP0"):
        cfg = Cfg(fee_model=fm)
        report(f"baseline [{fm}]", run_set(EXPL18, cfg))

    print("\n=== A2. Плоский свип комиссии за сторону (обе ноги одинаковые) ===")
    gross_tr = run_set(EXPL18, Cfg(flat_fee=0.0))
    g = basic_stats(gross_tr)
    print(f"брутто (0%): нетто={g['gross']*100:+.3f}%/сделку, n={g['n']}")
    for f in (0.0, 0.0002, 0.0005, 0.00075, 0.001):
        report(f"flat {f*100:.3f}%/сторона", run_set(EXPL18, Cfg(flat_fee=f)),
               show_port=False)
    ceiling = g["gross"] / 2
    print(f"\nПотолок издержек: edge умирает при плоской комиссии ~{ceiling*100:.3f}% "
          f"за сторону (round-trip ~{g['gross']*100:.3f}%).")

    print("\n=== A3. Раскладка baseline по монетам (EXPL18, FUTURES) ===")
    per_coin_table(EXPL18, base)

    tr = run_set(EXPL18, base)
    pnl, mdd = portfolio(tr)
    print(f"\nПортфель (5%/позиция, без компаундинга): P&L={pnl*100:+.2f}% "
          f"капитала, MDD={mdd*100:.2f}%, P&L/DD={pnl/mdd if mdd else 0:.2f}")
    neg = sum(1 for t in tr if t.net < 0)
    print(f"сделок: {len(tr)}, убыточных: {neg}, fill-модель консервативная "
          f"(лимит исполняется по low бара)")


if __name__ == "__main__":
    main()
