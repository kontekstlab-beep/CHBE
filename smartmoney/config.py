"""Параметры стратегии — соответствуют сводной таблице ТЗ §14.

🎓 — значение из обучения; ⚙️ — инженерное допущение (калибровать на бэктесте).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StructureConfig:
    pivot_strength: int = 2         # ⚙️ сила свинга для зоны/OB (баров слева/справа)
    trend_pivot_strength: int = 3   # ⚙️ крупные свинги для чтения тренда (HTF-контекст)
    confirm_pivot_strength: int = 1  # ⚙️ мелкие свинги для BOS-подтверждения (LTF-вход)
    trend_swings: int = 4           # ⚙️ K свингов для определения тренда
    regime_ma_len: int = 0          # ⚙️ фильтр режима по HTF-SMA (0 = выкл): шорт только
                                    #    если HTF-close < SMA, лонг — если >  (гипотеза M3.7)


@dataclass
class LiquidityConfig:
    equal_level_tol: float = 0.0010  # ⚙️ 0.10% — толеранс "равных" уровней
    min_touches: int = 2             # 🎓 двойное/тройное дно/вершина
    lookback_swings: int = 40        # ⚙️ кластеризовать только последние N свингов (близкая ликвидность)


@dataclass
class OrderBlockConfig:
    displacement_atr: float = 1.5    # ⚙️ порог импульса в ATR
    atr_period: int = 14             # ⚙️
    impulse_lookahead: int = 3       # ⚙️ баров на импульс после блока
    min_ob_score: int = 4            # ⚙️ (🎓 "сильный" блок)
    zone_mode: str = "full"          # 🎓 весь диапазон свечи


@dataclass
class RiskConfig:
    risk_pct: float = 0.01           # 🎓 1% на сделку
    min_rr: float = 3.0              # 🎓 RR >= 3 (цель 5)
    max_margin_per_trade: float = 0.20   # ⚙️
    max_leverage: int = 20           # ⚙️
    sl_buffer_atr: float = 0.1       # ⚙️
    # --- исполнение и сопровождение ---
    use_limit_entry: bool = True     # 🎓 лимитка от LTF-блока (иначе — вход по рынку)
    order_ttl_bars: int = 12         # ⚙️ TTL лимитки (баров до отмены)
    use_breakeven: bool = True       # 🎓 перевод SL в безубыток
    breakeven_at_r: float = 1.0      # 🎓 после +1R переносим SL в точку входа
    # --- частичная фиксация и трейлинг ---
    use_partial: bool = False        # ⚙️ частично фиксировать часть позиции
    partial_at_r: float = 1.0        # ⚙️ уровень частичной фиксации (в R)
    partial_frac: float = 0.5        # ⚙️ доля позиции, фиксируемая на partial_at_r
    use_trailing: bool = False       # ⚙️ трейлинг остатка после частичной фиксации
    trail_atr_mult: float = 1.5      # ⚙️ дистанция трейлинга в ATR


@dataclass
class EntryConfig:
    """Параметры входа/стопа/цели.

    Нейтральные дефолты ближе к методике учителя (вход у края блока, стоп за блок,
    цель — ликвидность). Валидированный на walk-forward вариант (глубокий вход +
    ATR-стоп + близкая фикс-цель RR1) вынесен в `presets.backtest_v1()`; см.
    README (M3.2).
    """
    # где ставить лимитку внутри LTF-блока, вызвавшего слом
    entry_edge: str = "proximal"     # proximal | mid | distal
    # как считать стоп-лосс
    sl_mode: str = "block"           # block (за край блока + буфер) | atr (entry ± k*ATR)
    sl_atr_mult: float = 1.0         # ⚙️ множитель ATR для sl_mode=atr
    # как выбирать цель
    target_mode: str = "pool_nearest"  # pool_nearest | pool_farthest | rr
    target_rr: float = 2.0           # ⚙️ фиксированный RR для target_mode=rr


@dataclass
class Config:
    structure: StructureConfig = field(default_factory=StructureConfig)
    liquidity: LiquidityConfig = field(default_factory=LiquidityConfig)
    orderblock: OrderBlockConfig = field(default_factory=OrderBlockConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    entry: EntryConfig = field(default_factory=EntryConfig)

    # 🎓 Фибоначчи Premium/Discount — точные уровни из обучения
    fib_levels: tuple = (0.0, 0.5, 0.62, 0.705, 0.79, 1.0, -0.27, -0.62)

    # 🎓 связки таймфреймов: HTF -> список LTF
    tf_pairings: dict = field(default_factory=lambda: {
        "1W": ["4H", "1D"],
        "1D": ["1H", "4H"],
        "4H": ["15m", "1H"],
    })
