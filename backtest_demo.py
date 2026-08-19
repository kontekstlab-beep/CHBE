"""Прогон бэктеста стратегии.

Синтетика (по умолчанию):
    python backtest_demo.py

Реальные свечи Binance (нужен ccxt):
    python backtest_demo.py --binance SOL/USDT 1h 1000
"""
from __future__ import annotations

import sys

from smartmoney import synth
from smartmoney.backtest import Backtester, BacktestConfig
from smartmoney.config import Config
from smartmoney.metrics import format_metrics
from smartmoney.strategy import SmartMoneyStrategy


def build_cfg() -> Config:
    cfg = Config()
    # ПРОТО-настройки для демо (⚙️ НЕ оптимизированы — только чтобы получить
    # осмысленную выборку сделок и показать работу движка/метрик).
    cfg.structure.pivot_strength = 2
    cfg.structure.trend_pivot_strength = 4
    cfg.orderblock.atr_period = 14
    cfg.orderblock.displacement_atr = 1.0
    cfg.orderblock.min_ob_score = 2
    cfg.risk.min_rr = 1.5
    cfg.liquidity.equal_level_tol = 0.006
    return cfg


def main(argv: list[str]) -> None:
    cfg = build_cfg()
    label = "синтетический нисходящий ряд"

    if len(argv) >= 2 and argv[0] == "--binance":
        from smartmoney.data import load_binance
        symbol = argv[1]
        timeframe = argv[2] if len(argv) > 2 else "1h"
        limit = int(argv[3]) if len(argv) > 3 else 1000
        candles = load_binance(symbol, timeframe, limit)
        label = f"Binance {symbol} {timeframe} ({len(candles)} свечей)"
    else:
        cfg.structure.pivot_strength = 1
        cfg.orderblock.atr_period = 5
        cfg.orderblock.displacement_atr = 1.0
        cfg.liquidity.equal_level_tol = 0.03
        candles = synth.downtrend_series(cycles=12)

    strat = SmartMoneyStrategy(cfg, allow_longs=True, arm_ttl_bars=30)
    res = Backtester(cfg, BacktestConfig(starting_equity=1000)).run(candles, strat)

    print(f"=== Бэктест: {label} ===")
    print(f"Баров: {len(candles)}\n")
    print(format_metrics(res.metrics))
    print(f"\nПервые сделки:")
    for tr in res.trades[:10]:
        print(f"  {tr.side.value:5s} вход@bar{tr.entry_index} {tr.entry:.2f} -> "
              f"выход@bar{tr.exit_index} {tr.exit:.2f} [{tr.reason}] "
              f"R={tr.r_multiple:+.2f} pnl={tr.pnl:+.2f}")
    if not res.trades:
        print("  (сделок не было — ужесточите/ослабьте пороги в build_cfg)")


if __name__ == "__main__":
    main(sys.argv[1:])
