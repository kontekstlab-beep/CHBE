"""Пункт 1: maker-вход для mean-reversion (срезать издержки).

Модель исполнения: при сигнале (z<entry_z) ставим ЛИМИТКУ на buy по
close*(1-offset). Она исполняется, только если в ближайшие fill_window баров
цена коснулась лимит-уровня (low <= limit) — иначе сделки НЕТ (пропуск).
Так честно учитываем, что часть сигналов (быстрый отскок) не исполнится.

Комиссии: вход maker, выход taker (консервативно) либо оба maker.

Сравнение taker vs maker на TUNING (dev), затем заморозка -> HOLDOUT.

    python meanrev_maker.py
"""
from __future__ import annotations

import csv
import os
from typing import List, Tuple

from meanrev import stats, zseries
from smartmoney.datasets import HOLDOUT, OOS_USED, TUNING

N, ENTRY_Z, EXIT_Z, HOLD = 48, -2.0, 0.0, 8
MAKER, TAKER = 0.0002, 0.0005  # комиссии Binance futures VIP0


def load_ohlc(sym: str) -> Tuple[List[float], List[float]]:
    """Возвращает (closes, lows)."""
    path = os.path.join("data", sym.replace("/", "") + "_1h_4000.csv")
    closes, lows = [], []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            closes.append(float(r["close"]))
            lows.append(float(r["low"]))
    return closes, lows


def backtest(closes, lows, *, entry_mode: str, offset: float, fill_window: int,
             fee_in: float, fee_out: float) -> Tuple[List[float], int, int]:
    """Возвращает (net_returns, signals, fills). Фактические low баров для филлов."""
    z = zseries(closes, N)
    trades: List[float] = []
    signals = fills = 0
    i = N
    n = len(closes)
    while i < n - 1:
        if z[i] is None or z[i] >= ENTRY_Z:
            i += 1
            continue
        signals += 1
        if entry_mode == "taker":
            entry, entry_bar, filled = closes[i], i, True
        else:  # maker-лимитка: исполняется, если low следующих баров коснулся лимита
            limit = closes[i] * (1 - offset)
            entry_bar = None
            for jj in range(i + 1, min(i + 1 + fill_window, n)):
                if lows[jj] <= limit:
                    entry_bar = jj
                    break
            filled = entry_bar is not None
            entry = limit if filled else None
        if not filled:
            i += 1
            continue
        fills += 1
        k = entry_bar + 1
        while k < n and (k - entry_bar) < HOLD and (z[k] is None or z[k] < EXIT_Z):
            k += 1
        k = min(k, n - 1)
        trades.append(closes[k] / entry - 1 - fee_in - fee_out)
        i = k + 1
    return trades, signals, fills


def summary(symbols, **kw):
    R: List[float] = []
    sig = fil = 0
    for s in symbols:
        closes, lows = load_ohlc(s)
        r, sg, fl = backtest(closes, lows, **kw)
        R += r
        sig += sg
        fil += fl
    n, wr, m, pf = stats(R)
    fillrate = fil / sig * 100 if sig else 0
    return n, wr, m, pf, fillrate


def line(label, symbols, **kw):
    n, wr, m, pf, fr = summary(symbols, **kw)
    pfs = "inf" if pf == float("inf") else f"{pf:.2f}"
    print(f"{label:34s} сделок={n:4d} fill={fr:4.0f}% win={wr:4.1f}% "
          f"нетто={m*100:+.3f}% pf={pfs}")


def main() -> None:
    print("=== TUNING: taker vs maker-вход (важно — доля исполнения fill%) ===")
    line("taker (fee 0.10%)", TUNING, entry_mode="taker", offset=0, fill_window=1,
         fee_in=TAKER, fee_out=TAKER)
    line("maker@close, exit taker (0.07%)", TUNING, entry_mode="maker", offset=0.0, fill_window=3,
         fee_in=MAKER, fee_out=TAKER)
    line("maker@close, exit maker (0.04%)", TUNING, entry_mode="maker", offset=0.0, fill_window=3,
         fee_in=MAKER, fee_out=MAKER)
    line("maker -0.2%, exit taker", TUNING, entry_mode="maker", offset=0.002, fill_window=3,
         fee_in=MAKER, fee_out=TAKER)
    line("maker -0.5%, exit taker", TUNING, entry_mode="maker", offset=0.005, fill_window=4,
         fee_in=MAKER, fee_out=TAKER)

    print("\n=== HOLDOUT: taker vs лучший maker (заморожено) ===")
    line("taker (0.10%)", HOLDOUT, entry_mode="taker", offset=0, fill_window=1,
         fee_in=TAKER, fee_out=TAKER)
    line("maker@close exit taker (0.07%)", HOLDOUT, entry_mode="maker", offset=0.0, fill_window=3,
         fee_in=MAKER, fee_out=TAKER)
    line("maker@close exit maker (0.04%)", HOLDOUT, entry_mode="maker", offset=0.0, fill_window=3,
         fee_in=MAKER, fee_out=MAKER)

    print("\nПрим.: «low» аппроксимирован по close (нет тиков) — оценка филлов КОНСЕРВАТИВНА "
          "(реальные внутрибарные лои дали бы больше исполнений).")


if __name__ == "__main__":
    main()
