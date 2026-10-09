"""M6-G: селекция лучшего конфига (EXPL18).

Кандидаты отобраны из результатов A–F (никаких новых идей). Критерий:
«устойчивый нетто-edge» = медиана по монетам × выживаемость при SPOT_BNB
(бот работает на споте) + портфельный P&L/MDD + n >= 40. Победитель замораживается
для единственного прогона на FRESH12 (пункт H).

Дополнительно — sanity-check часовой аномалии (E4): часы 1 и 6 UTC сильно
отрицательные; проверяем, не артефакт ли это 1–2 монет, прежде чем вообще
рассматривать часовой фильтр.

    python explore_m6_g_select.py
"""
from __future__ import annotations

from explore_m6_lib import EXPL18, Cfg, basic_stats, portfolio, report, run_set

CANDS = [
    ("C0 baseline (48/-2.0/8)",            Cfg()),
    ("C1 +лесенка z<-3",                   Cfg(ladder_z=-3.0)),
    ("C2 лимит -0.5%",                     Cfg(offset=0.005)),
    ("C3 фильтр BTC z<-1",                 Cfg(btc_mode="req_z", btc_z=-1.0)),
    ("C4 entry_z=-2.5",                    Cfg(entry_z=-2.5)),
    ("C5 лесенка + лимит -0.5%",           Cfg(ladder_z=-3.0, offset=0.005)),
    ("C6 лесенка + BTC z<-1",              Cfg(ladder_z=-3.0, btc_mode="req_z", btc_z=-1.0)),
]


def line(label, cfg, fm):
    tr = run_set(EXPL18, cfg)
    s = basic_stats(tr)
    pnl, mdd = portfolio(tr)
    pfs = "inf" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    print(f"{label:30s} [{fm:9s}] n={s['n']:4d} win={s['win']:5.1f}% "
          f"нетто={s['net']*100:+6.3f}% pf={pfs:>5s} мед={s['med']*100:+6.3f}% "
          f"P&L={pnl*100:+6.2f}% MDD={mdd*100:5.2f}% худш={s['worst']*100:6.2f}%")
    return s, pnl, mdd


def main() -> None:
    print("=== G0. Sanity часовой аномалии: сделки в часы 1 и 6 UTC по монетам ===")
    tr = run_set(EXPL18, Cfg())
    bad = [t for t in tr if t.hour in (1, 6)]
    rest = [t for t in tr if t.hour not in (1, 6)]
    report("часы {1,6}", bad, show_port=False)
    report("все прочие часы", rest, show_port=False)
    neg_coins = {}
    for t in bad:
        neg_coins.setdefault(t.sym, []).append(t.net)
    rows = sorted(((s, len(v), sum(v)) for s, v in neg_coins.items()),
                  key=lambda x: x[2])
    print("вклад монет в P&L часов {1,6} (сумма нетто, п.п.):")
    for s, n, tot in rows:
        print(f"  {s:7s} n={n:2d} сумма={tot*100:+7.2f}")

    print("\n=== G1. Кандидаты на EXPL18: FUTURES vs SPOT_BNB ===")
    best = None
    for name, cfg in CANDS:
        s_f, pnl_f, mdd_f = line(name, cfg, "FUTURES")
        cfg_b = Cfg(**{**cfg.__dict__, "fee_model": "SPOT_BNB"})
        s_b, pnl_b, mdd_b = line(name, cfg_b, "SPOT_BNB")
        # скор: медиана при SPOT_BNB (выживаемость на споте), штраф за малый n
        score = s_b["med"] if s_b["n"] >= 40 else -9
        if best is None or score > best[0]:
            best = (score, name)
    print(f"\nПобедитель по критерию (медиана @SPOT_BNB): {best[1]}")


if __name__ == "__main__":
    main()
