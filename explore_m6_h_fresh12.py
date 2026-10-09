"""M6-H: FRESH12 — строгая финальная валидация (НЕ подбирать на этом наборе).

Протокол: максимум 3 задокументированных прогона замороженных конфигов.
Заморожено ДО первого прогона на FRESH12 (по итогам A–G на EXPL18):
  H1 = baseline (paper/config.py): SMA48, z-2.0, hold8, стоп8, лимит@close;
  H2 = лучший кандидат G: baseline + лесенка z<-3 + фильтр BTC z48<-1;
  H3 = тай-брейк (запускается ТОЛЬКО если H1 vs H2 неразличимы):
       H2 + исключение часов UTC {1,6} (аномалия E4/G0, подтверждена на всех 18).

Правило решения (пре-специфицировано):
  diff > +0.03 п.п. и t > +2  -> кандидат лучше (стоп);
  diff < -0.03 п.п. и t < -2  -> baseline лучше (стоп);
  иначе -> прогон H3, то же сравнение H3 vs H1.

Основная модель комиссий — SPOT_BNB (бот работает на споте), FUTURES — справочно.
Сравнение: парный тест по 12 монетам (средние нетто/сделку на монету).

    python explore_m6_h_fresh12.py
"""
from __future__ import annotations

import math
from statistics import mean, pstdev

from explore_m6_lib import FRESH12, Cfg, backtest_coin, load, report

H1 = ("H1 baseline", Cfg())
H2 = ("H2 лесенка+BTCz<-1", Cfg(ladder_z=-3.0, btc_mode="req_z", btc_z=-1.0))
H3 = ("H3 H2+часы!={1,6}", Cfg(ladder_z=-3.0, btc_mode="req_z", btc_z=-1.0,
                               hours=set(range(24)) - {1, 6}))


def run(cfg: Cfg):
    tr = []
    for s in FRESH12:
        tr += backtest_coin(load(s), cfg)
    return tr


def paired(cfg1: Cfg, cfg2: Cfg, fee_model: str):
    c1 = Cfg(**{**cfg1.__dict__, "fee_model": fee_model})
    c2 = Cfg(**{**cfg2.__dict__, "fee_model": fee_model})
    m1, m2 = {}, {}
    for s in FRESH12:
        t1 = backtest_coin(load(s), c1)
        t2 = backtest_coin(load(s), c2)
        if t1 and t2:
            m1[s] = mean(t.net for t in t1)
            m2[s] = mean(t.net for t in t2)
    diffs = [m2[s] - m1[s] for s in m1]
    md = mean(diffs)
    sd = pstdev(diffs) or 1e-9
    t = md / (sd / math.sqrt(len(diffs)))
    return md, t, len(diffs)


def verdict(md, t, a, b):
    eco = "ПРОЙДЕН" if md > 0.0003 else ("провален (хуже)" if md < -0.0003 else "НЕ пройден")
    stat = "значимо" if abs(t) > 2 else "не значимо"
    print(f"  {b} - {a}: разность = {md*100:+.3f} п.п./сделку, t = {t:+.2f} "
          f"-> экон.порог {eco}, статистика {stat}")
    if md > 0.0003 and t > 2:
        return "CAND_WINS"
    if md < -0.0003 and t < -2:
        return "BASE_WINS"
    return "AMBIGUOUS"


def main() -> None:
    print("=== H. FRESH12 (прогон 1-2: H1 baseline, H2 кандидат) ===")
    for name, cfg in (H1, H2):
        for fm in ("SPOT_BNB", "FUTURES"):
            c = Cfg(**{**cfg.__dict__, "fee_model": fm})
            report(f"FRESH12 {name} [{fm}]", run(c))
    md, t, k = paired(H1[1], H2[1], "SPOT_BNB")
    print(f"\nПарный тест по {k} монетам (SPOT_BNB):")
    v = verdict(md, t, H1[0], H2[0])

    if v == "AMBIGUOUS":
        print("\n=== H. FRESH12 (прогон 3, тай-брейк: H3) — разрешён протоколом ===")
        for fm in ("SPOT_BNB", "FUTURES"):
            c = Cfg(**{**H3[1].__dict__, "fee_model": fm})
            report(f"FRESH12 {H3[0]} [{fm}]", run(c))
        md3, t3, k3 = paired(H1[1], H3[1], "SPOT_BNB")
        print(f"\nПарный тест по {k3} монетам (SPOT_BNB):")
        verdict(md3, t3, H1[0], H3[0])
    else:
        print(f"\nИтог: {v}; тай-брейк H3 НЕ запускался (FRESH12 сэкономлен).")


if __name__ == "__main__":
    main()
