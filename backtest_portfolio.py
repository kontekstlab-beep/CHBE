"""Портфельный прогон: бэктест по нескольким монетам, сводная таблица + пул метрик.

    python backtest_portfolio.py            # список по умолчанию, 1500 свечей 1h
    python backtest_portfolio.py 4h 1500 SOL/USDT LINK/USDT ...

ВНИМАНИЕ: пороги в backtest_demo.build_cfg НЕ оптимизированы (это задача M3).
Результаты иллюстрируют работу движка/метрик, а не прибыльность стратегии.
"""
from __future__ import annotations

import sys

from backtest_demo import build_cfg
from smartmoney.backtest import Backtester, BacktestConfig
from smartmoney.data import load_binance
from smartmoney.metrics import compute_metrics
from smartmoney.strategy import SmartMoneyStrategy

DEFAULT_SYMBOLS = ["SOL/USDT", "LINK/USDT", "NEAR/USDT", "FIL/USDT",
                   "APE/USDT", "XRP/USDT", "BNB/USDT", "CRV/USDT"]


def main(argv: list[str]) -> None:
    timeframe = argv[0] if len(argv) > 0 else "1h"
    limit = int(argv[1]) if len(argv) > 1 else 1500
    symbols = argv[2:] if len(argv) > 2 else DEFAULT_SYMBOLS

    cfg = build_cfg()
    all_r: list[float] = []
    all_pnl: list[float] = []

    print(f"=== Портфельный бэктест ({timeframe}, {limit} свечей) ===")
    print(f"{'symbol':12s} {'trades':>6s} {'win%':>6s} {'exp,R':>7s} {'ret%':>7s} {'maxDD%':>7s}")
    print("-" * 52)
    for sym in symbols:
        try:
            candles = load_binance(sym, timeframe, limit)
        except Exception as e:
            print(f"{sym:12s}  ошибка загрузки: {e}")
            continue
        strat = SmartMoneyStrategy(cfg, allow_longs=True, arm_ttl_bars=30)
        res = Backtester(cfg, BacktestConfig(starting_equity=1000)).run(candles, strat)
        m = res.metrics
        all_r += [t.r_multiple for t in res.trades]
        all_pnl += [t.pnl for t in res.trades]
        print(f"{sym:12s} {m.trades:6d} {m.winrate*100:6.1f} {m.avg_r:+7.3f} "
              f"{m.total_return_pct:+7.2f} {m.max_drawdown_pct:7.2f}")

    print("-" * 52)
    # пул по всем сделкам (equity нарастающим итогом от 1000)
    equity = 1000.0
    curve = [equity]
    for p in all_pnl:
        equity += p
        curve.append(equity)
    pooled = compute_metrics(all_r, all_pnl, curve, 1000.0)
    print(f"ПУЛ: сделок={pooled.trades}  винрейт={pooled.winrate*100:.1f}%  "
          f"expectancy={pooled.avg_r:+.3f}R  profit_factor="
          f"{'inf' if pooled.profit_factor==float('inf') else f'{pooled.profit_factor:.2f}'}")
    print("\nПрим.: пороги не калибровались (M3). Показана работа движка и метрик.")


if __name__ == "__main__":
    main(sys.argv[1:])
