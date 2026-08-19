"""M3.3: сравнение сопровождения (частичка/трейлинг) на walk-forward.

База — presets.backtest_v1 (вход distal + ATR-стоп). Меняем только управление
позицией. Метрика робастности — walk-forward по 5 окнам (плюс в скольких окнах).

    python explore_management.py
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List

from smartmoney.backtest import Backtester, BacktestConfig
from smartmoney.config import Config
from smartmoney.data import get_cached
from smartmoney.models import Candle
from smartmoney.presets import backtest_v1
from smartmoney.strategy import SmartMoneyStrategy
from calibrate import SYMBOLS, TIMEFRAME, TOTAL_BARS

K = 5


def reindex(seq):
    return [Candle(i, c.ts, c.open, c.high, c.low, c.close, c.volume) for i, c in enumerate(seq)]


@dataclass
class Mgmt:
    name: str
    apply: Callable[[Config], None]


def v1_base(cfg: Config):
    pass  # RR1 full, без частички/трейла (как в backtest_v1)


def partial_only(cfg: Config):
    cfg.entry.target_rr = 3.0
    cfg.risk.use_partial = True
    cfg.risk.partial_at_r = 1.0
    cfg.risk.partial_frac = 0.5
    cfg.risk.use_trailing = False


def trail_only(cfg: Config):
    cfg.entry.target_rr = 3.0
    cfg.risk.use_partial = False
    cfg.risk.use_breakeven = True
    cfg.risk.breakeven_at_r = 1.0
    cfg.risk.use_trailing = True
    cfg.risk.trail_atr_mult = 1.5


def partial_trail(cfg: Config):
    cfg.entry.target_rr = 3.0
    cfg.risk.use_partial = True
    cfg.risk.partial_at_r = 1.0
    cfg.risk.partial_frac = 0.5
    cfg.risk.use_trailing = True
    cfg.risk.trail_atr_mult = 1.5


def partial_trail_wide(cfg: Config):
    partial_trail(cfg)
    cfg.risk.trail_atr_mult = 2.5


def partial_30(cfg: Config):
    partial_trail(cfg)
    cfg.risk.partial_frac = 0.3


VARIANTS = [
    Mgmt("v1 база (RR1 full)", v1_base),
    Mgmt("частичка 50% (без трейла)", partial_only),
    Mgmt("только трейлинг ATR1.5", trail_only),
    Mgmt("частичка50 + трейл1.5", partial_trail),
    Mgmt("частичка50 + трейл2.5", partial_trail_wide),
    Mgmt("частичка30 + трейл1.5", partial_30),
]


def run_fold(datasets: List[List[Candle]], mgmt: Mgmt):
    R: List[float] = []
    for cs in datasets:
        cfg = backtest_v1()
        mgmt.apply(cfg)
        st = SmartMoneyStrategy(cfg, allow_longs=True, arm_ttl_bars=30)
        res = Backtester(cfg, BacktestConfig()).run(cs, st)
        R += [t.r_multiple for t in res.trades]
    n = len(R)
    exp = sum(R) / n if n else 0.0
    wr = sum(1 for r in R if r > 0) / n * 100 if n else 0.0
    gw = sum(r for r in R if r > 0)
    gl = -sum(r for r in R if r < 0)
    pf = gw / gl if gl > 0 else float("inf")
    return n, wr, exp, pf


def main() -> None:
    folds = [[] for _ in range(K)]
    for s in SYMBOLS:
        c = get_cached(s, TIMEFRAME, TOTAL_BARS)
        n = len(c) // K
        for k in range(K):
            folds[k].append(reindex(c[k * n:(k + 1) * n]))

    print("=== Сопровождение: walk-forward по 5 окнам (база — вход v1) ===")
    print(f"{'вариант':28s} {'сделок':>6s} {'win%':>6s} {'exp,R':>7s} {'pf':>5s} {'+окон':>6s}")
    print("-" * 62)
    for v in VARIANTS:
        exps = []
        tot = 0
        agg_R_n = 0
        # общий пул + по окнам
        pos_windows = 0
        alln = allexp_num = 0
        total_R = []
        for k in range(K):
            n, wr, exp, pf = run_fold(folds[k], v)
            exps.append(exp)
            if exp > 0:
                pos_windows += 1
        # пул по всем окнам сразу
        n, wr, exp, pf = run_fold([cs for f in folds for cs in f], v)
        pfs = "inf" if pf == float("inf") else f"{pf:.2f}"
        print(f"{v.name:28s} {n:6d} {wr:6.1f} {exp:+7.3f} {pfs:>5s} {pos_windows:>4d}/{K}")


if __name__ == "__main__":
    main()
