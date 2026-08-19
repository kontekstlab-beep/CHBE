"""Разведочный анализ: есть ли предсказуемая структура в 1h-доходностях?

Только TUNING-набор (разведка in-sample). Для каждого сигнала считаем среднюю
будущую доходность по бакетам + hit rate + размер выборки, БЕЗ look-ahead.
Порог торгуемости: |edge| должен превышать round-trip издержки (~0.10%).

    python eda.py
"""
from __future__ import annotations

import csv
import math
import os
from statistics import mean, pstdev
from typing import Dict, List

from smartmoney.datasets import TUNING

COST = 0.0010  # ~0.10% round-trip (тейкер обе стороны + проскальзывание)
H = 4          # горизонт будущей доходности, баров (1h)


def load(sym: str) -> List[dict]:
    path = os.path.join("data", sym.replace("/", "") + "_1h_4000.csv")
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({k: float(r[k]) for k in ("ts", "open", "high", "low", "close")})
    return rows


def sma(xs, i, n):
    if i + 1 < n:
        return None
    return sum(xs[i - n + 1:i + 1]) / n


def rsi(closes, i, n=14):
    if i < n:
        return None
    gains = losses = 0.0
    for j in range(i - n + 1, i + 1):
        d = closes[j] - closes[j - 1]
        if d > 0:
            gains += d
        else:
            losses -= d
    if losses == 0:
        return 100.0
    rs = (gains / n) / (losses / n)
    return 100 - 100 / (1 + rs)


def bucket_stats(pairs: List[tuple], label: str, buckets: Dict[str, callable]):
    """pairs: [(signal_value, fwd_return)]; buckets: имя->предикат(value)."""
    print(f"\n== {label} == (горизонт {H}h, издержки {COST*100:.2f}%)")
    print(f"{'бакет':18s} {'N':>7s} {'ср.fwd%':>9s} {'hit>0%':>7s} {'нетто%':>8s}")
    for bname, pred in buckets.items():
        fr = [f for v, f in pairs if pred(v)]
        if len(fr) < 50:
            print(f"{bname:18s} {len(fr):7d}  (мало)")
            continue
        m = mean(fr)
        hit = sum(1 for x in fr if x > 0) / len(fr) * 100
        net = abs(m) - COST
        flag = "  <-- клир издержки" if net > 0 else ""
        print(f"{bname:18s} {len(fr):7d} {m*100:+9.3f} {hit:7.1f} {net*100:+8.3f}{flag}")


def main() -> None:
    # собираем сигналы и будущие доходности по всем TUNING-монетам
    ret_sign = []      # (знак прошлого бара, fwd)
    ret6 = []          # (доходность за 6ч, fwd)
    rsi_p = []         # (RSI, fwd)
    zdist = []         # (z от SMA24, fwd)
    consec = []        # (число подряд одинаковых баров со знаком, fwd)
    hour = []          # (час, fwd)
    autocorr_x, autocorr_y = [], []  # ret[t], ret[t+1]

    for s in TUNING:
        rows = load(s)
        closes = [r["close"] for r in rows]
        rets = [0.0] + [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
        n = len(closes)
        for i in range(30, n - H):
            fwd = closes[i + H] / closes[i] - 1
            ret_sign.append((rets[i], fwd))
            ret6.append((closes[i] / closes[i - 6] - 1, fwd))
            r = rsi(closes, i)
            if r is not None:
                rsi_p.append((r, fwd))
            m24 = sma(closes, i, 24)
            if m24:
                sd = pstdev(closes[i - 23:i + 1]) or 1e-9
                zdist.append(((closes[i] - m24) / sd, fwd))
            # число подряд идущих одинаковых по знаку баров
            c = 0
            sgn = 1 if rets[i] > 0 else -1
            j = i
            while j > 0 and (1 if rets[j] > 0 else -1) == sgn:
                c += 1
                j -= 1
            consec.append((sgn * c, fwd))
            hour.append((int((rows[i]["ts"] // 3_600_000) % 24), fwd))
            autocorr_x.append(rets[i])
            autocorr_y.append(rets[i + 1])

    print(f"Монет: {len(TUNING)} | наблюдений: ~{len(ret_sign)}")

    # 0) автокорреляция доходностей (есть ли вообще линейная предсказуемость)
    mx, my = mean(autocorr_x), mean(autocorr_y)
    cov = mean((a - mx) * (b - my) for a, b in zip(autocorr_x, autocorr_y))
    sx, sy = pstdev(autocorr_x), pstdev(autocorr_y)
    ac1 = cov / (sx * sy) if sx and sy else 0
    print(f"\nАвтокорреляция 1h-доходностей (лаг 1): {ac1:+.4f}  "
          f"(≈0 => простой линейной предсказуемости нет)")

    bucket_stats(ret_sign, "Знак прошлого бара (реверсия/моментум)", {
        "прошлый бар +": lambda v: v > 0,
        "прошлый бар -": lambda v: v < 0,
    })
    bucket_stats(rsi_p, "RSI(14)", {
        "RSI<20 (перепрод)": lambda v: v < 20,
        "RSI 20-40": lambda v: 20 <= v < 40,
        "RSI 40-60": lambda v: 40 <= v < 60,
        "RSI 60-80": lambda v: 60 <= v < 80,
        "RSI>80 (перекуп)": lambda v: v >= 80,
    })
    bucket_stats(zdist, "Отклонение от SMA24 (z)", {
        "z < -2": lambda v: v < -2,
        "-2..-1": lambda v: -2 <= v < -1,
        "-1..1": lambda v: -1 <= v <= 1,
        "1..2": lambda v: 1 < v <= 2,
        "z > 2": lambda v: v > 2,
    })
    bucket_stats(ret6, "Импульс за 6ч", {
        "6ч < -3%": lambda v: v < -0.03,
        "6ч -3..-1%": lambda v: -0.03 <= v < -0.01,
        "6ч -1..1%": lambda v: -0.01 <= v <= 0.01,
        "6ч 1..3%": lambda v: 0.01 < v <= 0.03,
        "6ч > 3%": lambda v: v > 0.03,
    })
    bucket_stats(consec, "Подряд идущих баров одного знака", {
        "3+ подряд вверх": lambda v: v >= 3,
        "3+ подряд вниз": lambda v: v <= -3,
        "4+ подряд вверх": lambda v: v >= 4,
        "4+ подряд вниз": lambda v: v <= -4,
    })
    bucket_stats(hour, "Час суток (UTC)", {
        f"{h:02d}:00": (lambda v, h=h: v == h) for h in (0, 8, 12, 13, 14, 16, 20)
    })

    print("\nПрим.: это разведка на TUNING (in-sample). Любой эффект, «клирящий» издержки,"
          "\nобязан пройти проверку на HOLDOUT прежде, чем считаться реальным.")


if __name__ == "__main__":
    main()
