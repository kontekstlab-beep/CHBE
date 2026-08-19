"""Гипотеза mean-reversion: покупка резких проливов (long-only).

Правило: если close на z < entry_z ниже SMA(n) — вход в лонг по close.
Выход: когда z вернулся к >= exit_z ИЛИ прошло max_hold баров. Издержки round-trip.

Разведка (eda.py) показала устойчивый отскок на перепроданности по 3 метрикам.
Здесь проверяем это как стратегию на уровне сделок (TUNING, walk-forward).

    python meanrev.py
"""
from __future__ import annotations

import csv
import os
from statistics import mean, pstdev
from typing import List

from smartmoney.datasets import TUNING

COST = 0.0010  # round-trip


def load(sym: str):
    path = os.path.join("data", sym.replace("/", "") + "_1h_4000.csv")
    with open(path, encoding="utf-8") as f:
        return [float(r["close"]) for r in csv.DictReader(f)]


def zseries(closes: List[float], n: int):
    z = [None] * len(closes)
    for i in range(n - 1, len(closes)):
        window = closes[i - n + 1:i + 1]
        m = sum(window) / n
        sd = pstdev(window) or 1e-9
        z[i] = (closes[i] - m) / sd
    return z


def backtest_coin(closes, n, entry_z, exit_z, max_hold):
    """Возвращает список чистых доходностей сделок (после издержек)."""
    z = zseries(closes, n)
    trades = []
    i = n
    while i < len(closes) - 1:
        if z[i] is not None and z[i] < entry_z:
            entry = closes[i]
            j = i + 1
            while j < len(closes) and (j - i) < max_hold and (z[j] is None or z[j] < exit_z):
                j += 1
            j = min(j, len(closes) - 1)
            trades.append(closes[j] / entry - 1 - COST)
            i = j + 1  # сделки не перекрываются
        else:
            i += 1
    return trades


def stats(R: List[float]):
    n = len(R)
    if not n:
        return 0, 0.0, 0.0, 0.0
    m = mean(R)
    wr = sum(1 for r in R if r > 0) / n * 100
    gw = sum(r for r in R if r > 0)
    gl = -sum(r for r in R if r < 0)
    pf = gw / gl if gl > 0 else float("inf")
    return n, wr, m, pf


def run_all(data, n, ez, xz, hold):
    R = []
    for closes in data.values():
        R += backtest_coin(closes, n, ez, xz, hold)
    return R


def walkforward(data, n, ez, xz, hold, K=5):
    pos = 0
    allR = []
    for k in range(K):
        R = []
        for closes in data.values():
            m = len(closes) // K
            R += backtest_coin(closes[k * m:(k + 1) * m], n, ez, xz, hold)
        allR += R
        if stats(R)[2] > 0:
            pos += 1
    n_, wr, mm, pf = stats(allR)
    return n_, wr, mm, pf, pos


def main() -> None:
    data = {s: load(s) for s in TUNING}
    print("=== mean-reversion (long dip-buy) на TUNING: свип параметров (walk-forward) ===")
    print(f"{'n/ez/xz/hold':18s} {'сделок':>6s} {'win%':>6s} {'ср.нетто%':>9s} {'pf':>5s} {'+окон':>6s}")
    print("-" * 58)
    best = None
    for n in (24, 48):
        for ez in (-1.5, -2.0, -2.5):
            for hold in (4, 8, 12):
                res = walkforward(data, n, ez, 0.0, hold)
                nn, wr, mm, pf, pos = res
                pfs = "inf" if pf == float("inf") else f"{pf:.2f}"
                label = f"{n}/{ez}/0/{hold}"
                print(f"{label:18s} {nn:6d} {wr:6.1f} {mm*100:+9.3f} {pfs:>5s} {pos:>4d}/5")
                if nn >= 100 and (best is None or (pos, mm) > (best[0], best[1])):
                    best = (pos, mm, (n, ez, hold), nn, wr, pf)
    print("\nЛучший (по +окон, затем ср.доходности):")
    pos, mm, (n, ez, hold), nn, wr, pf = best
    pfs = "inf" if pf == float("inf") else f"{pf:.2f}"
    print(f"  SMA{n}, entry_z={ez}, hold={hold}: сделок={nn} win={wr:.1f}% "
          f"ср.нетто={mm*100:+.3f}% pf={pfs} +окон={pos}/5")
    print("\nПрим.: TUNING (in-sample). Финальная проверка — на HOLDOUT (validate_meanrev.py).")


if __name__ == "__main__":
    main()
