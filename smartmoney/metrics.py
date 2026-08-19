"""Метрики результата бэктеста: winrate, expectancy (в R), profit factor,
максимальная просадка, итоговая доходность."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple


@dataclass
class Metrics:
    trades: int
    wins: int
    losses: int
    winrate: float
    avg_r: float          # среднее R по сделкам = expectancy
    profit_factor: float
    total_return_pct: float
    max_drawdown_pct: float
    final_equity: float


def max_drawdown(equity_curve: Sequence[float]) -> float:
    """Максимальная просадка в долях (0..1) от пика."""
    peak = float("-inf")
    mdd = 0.0
    for e in equity_curve:
        peak = max(peak, e)
        if peak > 0:
            mdd = max(mdd, (peak - e) / peak)
    return mdd


def compute_metrics(
    r_multiples: Sequence[float],
    pnls: Sequence[float],
    equity_curve: Sequence[float],
    starting_equity: float,
) -> Metrics:
    n = len(pnls)
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    gross_win = sum(p for p in pnls if p > 0)
    gross_loss = sum(-p for p in pnls if p < 0)
    winrate = wins / n if n else 0.0
    avg_r = sum(r_multiples) / n if n else 0.0
    if gross_loss > 0:
        profit_factor = gross_win / gross_loss
    else:
        profit_factor = float("inf") if gross_win > 0 else 0.0
    final_equity = equity_curve[-1] if equity_curve else starting_equity
    total_return = (final_equity / starting_equity - 1.0) if starting_equity else 0.0
    return Metrics(
        trades=n, wins=wins, losses=losses, winrate=winrate, avg_r=avg_r,
        profit_factor=profit_factor, total_return_pct=total_return * 100,
        max_drawdown_pct=max_drawdown(equity_curve) * 100, final_equity=final_equity,
    )


def format_metrics(m: Metrics) -> str:
    pf = "inf" if m.profit_factor == float("inf") else f"{m.profit_factor:.2f}"
    return (
        f"Сделок: {m.trades}  |  винрейт: {m.winrate*100:.1f}%  "
        f"({m.wins}W/{m.losses}L)\n"
        f"Среднее R (expectancy): {m.avg_r:+.3f}R\n"
        f"Profit factor: {pf}\n"
        f"Итоговый капитал: {m.final_equity:.2f}  "
        f"(доходность {m.total_return_pct:+.2f}%)\n"
        f"Макс. просадка: {m.max_drawdown_pct:.2f}%"
    )
