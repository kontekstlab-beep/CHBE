"""Портфельный риск-контроль для mean-reversion: лимит одновременных позиций +
рыночный kill-switch (пауза входов, когда вся корзина в свободном падении).

Симулятор шагает по времени сразу по всем монетам, ведёт общий P&L (в % от
стартового капитала, без компаундинга — чтобы честно мерить просадку) и меряет
максимальную просадку. Цель — не рост доходности, а СНИЖЕНИЕ коррелированной
просадки без потери суммарной прибыли.

Разработка на DEV -> заморозка -> HOLDOUT.

    python portfolio.py
"""
from __future__ import annotations

import csv
import os
from statistics import mean
from typing import Dict, List, Tuple

from meanrev import zseries
from smartmoney.datasets import HOLDOUT, OOS_USED, TUNING

N, ENTRY_Z, EXIT_Z, HOLD = 48, -2.0, 0.0, 8
MAKER, TAKER = 0.0002, 0.0005
STOP = 0.08          # широкий катастроф-стоп (из M4.3)
BASE_FRAC = 0.05     # доля стартового капитала на одну позицию
KILL_LOOKBACK = 24   # окно рыночного индекса (баров)


def load_full(sym: str):
    path = os.path.join("data", sym.replace("/", "") + "_1h_4000.csv")
    ts, closes, lows = [], [], []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ts.append(int(float(r["ts"])))
            closes.append(float(r["close"]))
            lows.append(float(r["low"]))
    return ts, closes, lows


def simulate(symbols, max_concurrent: int, kill_thresh, kill_ma: int = 0, verbose=False):
    coins = {}
    L = min(len(load_full(s)[0]) for s in symbols)
    for s in symbols:
        ts, c, lo = load_full(s)
        coins[s] = dict(ts=ts[:L], c=c[:L], lo=lo[:L], z=zseries(c[:L], N))
    # равновзвешенный индекс корзины (для kill по медвежьему режиму)
    idx = []
    for i in range(L):
        idx.append(mean(coins[s]["c"][i] / coins[s]["c"][0] for s in symbols))

    open_pos: Dict[str, dict] = {}   # sym -> {entry, entry_i}
    pnl = 0.0                        # накопленный P&L в долях стартового капитала
    curve = [0.0]
    peak = 0.0
    mdd = 0.0
    trades = 0
    kills = 0

    for i in range(N, L):
        # рыночный индекс: средняя доходность корзины за KILL_LOOKBACK
        kill = False
        if kill_thresh is not None and i > KILL_LOOKBACK:
            mret = mean(coins[s]["c"][i] / coins[s]["c"][i - KILL_LOOKBACK] - 1 for s in symbols)
            kill = mret < kill_thresh
        if kill_ma and i >= kill_ma:                 # медвежий режим: индекс ниже своей SMA
            sma = sum(idx[i - kill_ma + 1:i + 1]) / kill_ma
            if idx[i] < sma:
                kill = True
        if kill:
            kills += 1

        # 1) сопровождение открытых позиций
        for s in list(open_pos.keys()):
            p = open_pos[s]
            c = coins[s]
            entry = p["entry"]
            k = i
            exit_px = None
            if STOP > 0 and c["lo"][k] <= entry * (1 - STOP):
                exit_px = entry * (1 - STOP)
            elif c["z"][k] is not None and c["z"][k] >= EXIT_Z:
                exit_px = c["c"][k]
            elif (k - p["entry_i"]) >= HOLD:
                exit_px = c["c"][k]
            if exit_px is not None:
                ret = exit_px / entry - 1 - MAKER - TAKER
                pnl += BASE_FRAC * ret
                trades += 1
                del open_pos[s]

        # 2) новые входы (если kill выключен и есть свободные слоты)
        if not kill:
            for s in symbols:
                if s in open_pos or len(open_pos) >= max_concurrent:
                    continue
                c = coins[s]
                if c["z"][i] is not None and c["z"][i] < ENTRY_Z:
                    open_pos[s] = dict(entry=c["c"][i], entry_i=i)

        curve.append(pnl)
        peak = max(peak, pnl)
        mdd = max(mdd, peak - pnl)

    ret_to_dd = (pnl / mdd) if mdd > 0 else float("inf")
    return dict(pnl=pnl, mdd=mdd, trades=trades, kills=kills, rtd=ret_to_dd)


def line(label, symbols, mc, kt, km=0):
    M = simulate(symbols, mc, kt, km)
    rtd = "inf" if M["rtd"] == float("inf") else f"{M['rtd']:.2f}"
    print(f"{label:26s} P&L={M['pnl']*100:+7.2f}% просадка={M['mdd']*100:6.2f}% "
          f"P&L/DD={rtd:>5s} сделок={M['trades']:4d}")


def main() -> None:
    dev = TUNING + OOS_USED
    print("=== DEV (TUNING+OOS): контроли риска ===")
    line("без контроля", dev, 999, None)
    line("лимит 6 позиций", dev, 6, None)
    line("kill-switch -5%/24ч", dev, 999, -0.05)
    line("kill-switch -8%/24ч", dev, 999, -0.08)
    line("kill медвежий (idx<SMA200)", dev, 999, None, 200)
    line("лимит 6 + kill -5%", dev, 6, -0.05)

    print("\n=== HOLDOUT (заморожено): без контроля vs лимит6+kill-5% ===")
    line("без контроля", HOLDOUT, 999, None)
    line("лимит 6 + kill -5%", HOLDOUT, 6, -0.05)

    print("\nЧитать: цель — снизить просадку и поднять P&L/DD, не убив суммарный P&L.")


if __name__ == "__main__":
    main()
