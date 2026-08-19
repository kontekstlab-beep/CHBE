"""Пресеты конфигурации.

`backtest_v1` — комбинация, показавшая наилучшую УСТОЙЧИВОСТЬ на walk-forward
(5 окон, плюс в 4/5, винрейт ~60%, expectancy ~+0.07R в среднем; см. README M3.2).
Отклоняется от методики учителя целью RR≈1 (учитель целится в дальнюю ликвидность
при RR≥3) — но именно высокий-RR/низкий-винрейт вариант в бэктесте не работал.

Это прототип на одной серии со многими упрощениями; edge тонкий и не подтверждён
на бумаге/реале. Не является инвестиционной рекомендацией.
"""
from __future__ import annotations

from .config import Config


def backtest_v1() -> Config:
    cfg = Config()
    # структура (⚙️ калибровка M3)
    cfg.structure.pivot_strength = 2
    cfg.structure.confirm_pivot_strength = 1
    cfg.structure.trend_pivot_strength = 4
    # блоки заказов
    cfg.orderblock.atr_period = 14
    cfg.orderblock.min_ob_score = 3
    cfg.orderblock.displacement_atr = 1.2
    # ликвидность
    cfg.liquidity.equal_level_tol = 0.006
    # риск/исполнение
    cfg.risk.use_limit_entry = True
    cfg.risk.use_breakeven = True
    cfg.risk.breakeven_at_r = 2.0
    # вход/стоп/цель (валидированный вариант M3.2)
    cfg.entry.entry_edge = "distal"
    cfg.entry.sl_mode = "atr"
    cfg.entry.sl_atr_mult = 1.0
    cfg.entry.target_mode = "rr"
    cfg.entry.target_rr = 1.0
    return cfg


def mtf_v1() -> Config:
    """Конфиг для мультиТФ (HTF=4h контекст, LTF=1h вход). Отличается от v1 тем,
    что trend/pivot силы применяются к более крупному 4h (меньше нужны большие
    значения). Вход/цель — как в валидированном v1 (distal + ATR + RR1)."""
    cfg = backtest_v1()
    cfg.structure.trend_pivot_strength = 3   # 4h уже крупный -> умереннее
    cfg.structure.pivot_strength = 2
    cfg.structure.confirm_pivot_strength = 1  # для LTF (1h) BOS
    return cfg


def mtf_1d_v1() -> Config:
    """Лучшая найденная конфигурация: мультиТФ 1D (контекст) -> 1h (вход).

    Дневной контекст даёт заметно более чистые тренд/зоны. На walk-forward:
    ~+0.23R, PF≈1.65, винрейт ~68%, 7/8 монет в плюсе (см. README M3.5).
    Использовать с MultiTFStrategy(htf=1d, ltf=1h).

    Оговорка: HTF-пороги подобраны на тех же данных; edge тонкий, на paper/реале
    не проверен. Не инвестиционная рекомендация.
    """
    cfg = backtest_v1()
    cfg.structure.trend_pivot_strength = 2   # дневные свинги уже значимы
    cfg.structure.pivot_strength = 2
    cfg.structure.confirm_pivot_strength = 1  # LTF (1h) BOS
    cfg.orderblock.min_ob_score = 2          # на 1D полный score=4 редок
    return cfg


def backtest_v2() -> Config:
    """v1 + частичная фиксация и трейлинг (остаток к дальней цели RR3).

    ВНИМАНИЕ: по walk-forward этот вариант ХУЖЕ v1 (expectancy уходит в минус,
    винрейт 60%→47%). Оставлен как задокументированный отрицательный результат:
    у стратегии edge сосредоточен на близкой цели RR≈1, «раннер» его разрушает.
    Рекомендуемый пресет — backtest_v1. См. README (M3.3) / explore_management.py.
    """
    cfg = backtest_v1()
    cfg.entry.target_rr = 3.0        # дальняя цель для «раннера»
    cfg.risk.use_partial = True
    cfg.risk.partial_at_r = 1.0      # банкуем на +1R
    cfg.risk.partial_frac = 0.5      # половину позиции
    cfg.risk.use_trailing = True
    cfg.risk.trail_atr_mult = 1.5
    return cfg
