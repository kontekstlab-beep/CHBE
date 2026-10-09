"""M6-E: фильтры (EXPL18, FUTURES).

E1. Контекст BTC, оба направления:
    - входить ТОЛЬКО когда BTC z48 < -1 (толпа падает вместе) + комплементарная рука;
    - запрет входа при свободном падении BTC (ретерн 24ч < -5%) + комплемент.
E2. Всплеск объёма: volume z-score(48) > +1 на баре триггера (+ комплемент).
E3. Фильтр «падающего ножа»: запрет, если ретерн последних 3 баров хуже предыдущих 3.
E4. Время суток (UTC): раскладка edge по часам триггера.

    python explore_m6_e_filters.py
"""
from __future__ import annotations

from collections import defaultdict

from explore_m6_lib import EXPL18, Cfg, basic_stats, report, run_set


def main() -> None:
    print("=== E. Фильтры (EXPL18, FUTURES) ===")
    report("baseline (без фильтров)", run_set(EXPL18, Cfg()), show_port=False)

    print("\n-- E1a. BTC z < -1: входить только когда BTC тоже в проливе --")
    report("только BTC z<-1", run_set(EXPL18, Cfg(btc_mode="req_z", btc_z=-1.0)),
           show_port=False)
    report("комплемент: BTC z>=-1", run_set(EXPL18, Cfg(btc_mode="req_z_inv", btc_z=-1.0)),
           show_port=False)

    print("\n-- E1b. Запрет при падении BTC >5% за 24ч --")
    report("запрет BTC crash -5%/24ч", run_set(EXPL18, Cfg(btc_mode="block_crash")),
           show_port=False)

    print("\n-- E2. Всплеск объёма на триггере (vol z48 > +1) --")
    report("только vol z>+1", run_set(EXPL18, Cfg(vol_z=1.0)), show_port=False)
    # комплемент вручную: vol_z очень низкий = без фильтра, поэтому считаем разность
    base = run_set(EXPL18, Cfg())
    vol_tr = run_set(EXPL18, Cfg(vol_z=1.0))
    key = {(t.sym, t.entry_i) for t in vol_tr}
    compl = [t for t in base if (t.sym, t.entry_i) not in key]
    report("комплемент: vol z<=+1", compl, show_port=False)

    print("\n-- E3. Фильтр падающего ножа (запрет при ускорении падения) --")
    report("knife-запрет", run_set(EXPL18, Cfg(knife=True)), show_port=False)
    base_tr = run_set(EXPL18, Cfg())
    kn_tr = run_set(EXPL18, Cfg(knife=True))
    key = {(t.sym, t.entry_i) for t in kn_tr}
    compl = [t for t in base_tr if (t.sym, t.entry_i) not in key]
    report("комплемент: ножи (отфильтрованные)", compl, show_port=False)

    print("\n-- E4. Edge по часам UTC (час триггера, без комиссий меняется мало) --")
    by_h = defaultdict(list)
    for t in run_set(EXPL18, Cfg()):
        by_h[t.hour].append(t)
    print(f"{'час':>4s} {'n':>4s} {'win%':>6s} {'нетто%':>8s} {'pf':>5s}")
    for h in range(24):
        tr = by_h.get(h, [])
        s = basic_stats(tr)
        if s["n"] < 5:
            print(f"{h:4d} {s['n']:4d}      -        -     -")
            continue
        pfs = "inf" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
        print(f"{h:4d} {s['n']:4d} {s['win']:6.1f} {s['net']*100:+8.3f} {pfs:>5s}")


if __name__ == "__main__":
    main()
