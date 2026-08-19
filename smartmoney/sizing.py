"""Расчёт размера позиции под фиксированный риск 1% и соотношения риск/прибыль.

Риск ограничивается стоп-лоссом (🎓): при выбивании по SL убыток = risk_pct * equity,
независимо от плеча. Плечо подбирается только чтобы хватило маржи.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .config import RiskConfig
from .models import Side


@dataclass(frozen=True)
class Sizing:
    qty: float          # объём в единицах базового актива (контрактах)
    notional: float     # номинал позиции (qty * entry)
    leverage: int       # подобранное плечо
    margin: float       # требуемая маржа (notional / leverage)
    risk_amount: float  # сумма риска (equity * risk_pct)
    stop_distance: float


def position_size(equity: float, entry: float, stop_loss: float, cfg: RiskConfig) -> Sizing:
    """Размер позиции так, чтобы потеря по SL = risk_pct * equity."""
    stop_distance = abs(entry - stop_loss)
    if stop_distance <= 0:
        raise ValueError("stop_distance must be > 0")
    risk_amount = equity * cfg.risk_pct
    qty = risk_amount / stop_distance
    notional = qty * entry
    # минимальное плечо, чтобы маржа не превысила max_margin_per_trade * equity
    max_margin = cfg.max_margin_per_trade * equity
    if max_margin <= 0:
        leverage = 1
    else:
        leverage = max(1, math.ceil(notional / max_margin))
    leverage = min(leverage, cfg.max_leverage)
    margin = notional / leverage
    return Sizing(qty, notional, leverage, margin, risk_amount, stop_distance)


def risk_reward(side: Side, entry: float, stop_loss: float, take_profit: float) -> float:
    """RR = |вход - тейк| / |вход - стоп|. Не проверяет корректность сторон."""
    risk = abs(entry - stop_loss)
    reward = abs(take_profit - entry)
    if risk <= 0:
        return 0.0
    return reward / risk


def valid_bracket(side: Side, entry: float, stop_loss: float, take_profit: float) -> bool:
    """Проверка геометрии: для шорта SL выше входа, TP ниже; для лонга наоборот."""
    if side == Side.SHORT:
        return stop_loss > entry > take_profit
    return stop_loss < entry < take_profit
