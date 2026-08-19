"""M3: калибровка порогов на train + честная оценка на out-of-sample.

Схема:
  1) грузим кэшированные свечи по монетам (data/ ; сначала запустите download);
  2) делим каждую серию по времени: первые TRAIN_FRAC — train, остаток — test;
  3) grid search: для каждой комбинации порогов гоняем бэктест по TRAIN всех монет,
     пулим сделки, считаем метрики; кандидат допускается только при >= MIN_TRADES;
  4) выбираем лучшую комбинацию по expectancy (среднее R), тай-брейк — profit factor;
  5) прогоняем выбранную комбинацию на TEST (out-of-sample) и печатаем честный итог.

Запуск:  python calibrate.py
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import List, Sequence

from smartmoney.backtest import Backtester, BacktestConfig
from smartmoney.config import Config
from smartmoney.data import get_cached
from smartmoney.metrics import Metrics, compute_metrics
from smartmoney.models import Candle
from smartmoney.strategy import SmartMoneyStrategy

SYMBOLS = ["SOL/USDT", "LINK/USDT", "NEAR/USDT", "FIL/USDT",
           "APE/USDT", "XRP/USDT", "BNB/USDT", "CRV/USDT"]
TIMEFRAME = "1h"
TOTAL_BARS = 4000
TRAIN_FRAC = 0.65
MIN_TRADES = 40          # порог достаточной выборки на train
STARTING_EQUITY = 1000.0

# сетка перебираемых порогов (⚙️). Держим компактной ради времени прогона.
GRID = {
    "trend_pivot_strength": [3, 4],
    "min_ob_score": [2, 3],
    "displacement_atr": [0.8, 1.2],
    "min_rr": [1.5, 2.0, 3.0],
    "equal_level_tol": [0.004, 0.008],
    "allow_longs": [True],
}


@dataclass
class Combo:
    trend_pivot_strength: int
    min_ob_score: int
    displacement_atr: float
    min_rr: float
    equal_level_tol: float
    allow_longs: bool


def make_cfg(combo: Combo) -> Config:
    cfg = Config()
    cfg.structure.pivot_strength = 2
    cfg.structure.confirm_pivot_strength = 1
    cfg.structure.trend_pivot_strength = combo.trend_pivot_strength
    cfg.orderblock.atr_period = 14
    cfg.orderblock.min_ob_score = combo.min_ob_score
    cfg.orderblock.displacement_atr = combo.displacement_atr
    cfg.risk.min_rr = combo.min_rr
    cfg.liquidity.equal_level_tol = combo.equal_level_tol
    return cfg


def split(candles: List[Candle], frac: float):
    k = int(len(candles) * frac)
    # переиндексируем срезы с нуля, чтобы .index совпадал с позицией
    def reindex(seq):
        return [Candle(i, c.ts, c.open, c.high, c.low, c.close, c.volume)
                for i, c in enumerate(seq)]
    return reindex(candles[:k]), reindex(candles[k:])


def run_portfolio(datasets: Sequence[List[Candle]], cfg: Config, allow_longs: bool) -> Metrics:
    all_r: List[float] = []
    all_pnl: List[float] = []
    for candles in datasets:
        strat = SmartMoneyStrategy(cfg, allow_longs=allow_longs, arm_ttl_bars=30)
        res = Backtester(cfg, BacktestConfig(starting_equity=STARTING_EQUITY)).run(candles, strat)
        all_r += [t.r_multiple for t in res.trades]
        all_pnl += [t.pnl for t in res.trades]
    equity = STARTING_EQUITY
    curve = [equity]
    for p in all_pnl:
        equity += p
        curve.append(equity)
    return compute_metrics(all_r, all_pnl, curve, STARTING_EQUITY)


def main() -> None:
    print("Загрузка данных из кэша (data/)…")
    trains, tests = [], []
    for s in SYMBOLS:
        c = get_cached(s, TIMEFRAME, TOTAL_BARS)
        tr, te = split(c, TRAIN_FRAC)
        trains.append(tr)
        tests.append(te)
    print(f"Монет: {len(SYMBOLS)}  |  train≈{len(trains[0])} баров, test≈{len(tests[0])} баров\n")

    keys = list(GRID.keys())
    combos = [Combo(**dict(zip(keys, vals))) for vals in itertools.product(*[GRID[k] for k in keys])]
    print(f"Комбинаций в сетке: {len(combos)}. Идёт перебор на TRAIN…\n")

    results = []
    for i, combo in enumerate(combos, 1):
        cfg = make_cfg(combo)
        m = run_portfolio(trains, cfg, combo.allow_longs)
        results.append((combo, m))
        flag = "" if m.trades >= MIN_TRADES else "  (мало сделок)"
        print(f"[{i:2d}/{len(combos)}] tps={combo.trend_pivot_strength} score={combo.min_ob_score} "
              f"disp={combo.displacement_atr} rr={combo.min_rr} tol={combo.equal_level_tol} "
              f"-> trades={m.trades} exp={m.avg_r:+.3f}R pf="
              f"{'inf' if m.profit_factor==float('inf') else f'{m.profit_factor:.2f}'}{flag}")

    eligible = [(c, m) for c, m in results if m.trades >= MIN_TRADES]
    if not eligible:
        print("\nНи одна комбинация не набрала MIN_TRADES на train. "
              "Снизьте MIN_TRADES или расширьте сетку/данные.")
        eligible = results
    best_combo, best_m = max(eligible, key=lambda cm: (cm[1].avg_r, cm[1].profit_factor))

    print("\n=== Лучшая комбинация на TRAIN ===")
    print(f"trend_pivot_strength={best_combo.trend_pivot_strength}  min_ob_score={best_combo.min_ob_score}  "
          f"displacement_atr={best_combo.displacement_atr}  min_rr={best_combo.min_rr}  "
          f"equal_level_tol={best_combo.equal_level_tol}")
    print(f"TRAIN: trades={best_m.trades} winrate={best_m.winrate*100:.1f}% "
          f"expectancy={best_m.avg_r:+.3f}R profit_factor="
          f"{'inf' if best_m.profit_factor==float('inf') else f'{best_m.profit_factor:.2f}'}")

    # честная оценка на out-of-sample
    cfg = make_cfg(best_combo)
    test_m = run_portfolio(tests, cfg, best_combo.allow_longs)
    print("\n=== Оценка на TEST (out-of-sample) ===")
    print(f"TEST:  trades={test_m.trades} winrate={test_m.winrate*100:.1f}% "
          f"expectancy={test_m.avg_r:+.3f}R profit_factor="
          f"{'inf' if test_m.profit_factor==float('inf') else f'{test_m.profit_factor:.2f}'} "
          f"return={test_m.total_return_pct:+.2f}% maxDD={test_m.max_drawdown_pct:.2f}%")

    verdict = "ПОЛОЖИТЕЛЬНОЕ" if test_m.avg_r > 0 else "ОТРИЦАТЕЛЬНОЕ"
    print(f"\nИтог: матожидание на out-of-sample {verdict} ({test_m.avg_r:+.3f}R).")
    if test_m.avg_r <= 0 or test_m.trades < 100:
        print("Критерий приёмки ТЗ (≥100 сделок и положительное матожидание) НЕ достигнут — "
              "это ожидаемо для прототипа; нужны доработки (лимит-вход от LTF-блока, безубыток, "
              "расширение сетки/данных).")


if __name__ == "__main__":
    main()
