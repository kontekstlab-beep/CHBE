"""Модели данных для примитивов структуры рынка.

Все примитивы неизменяемы там, где это возможно, и хранят индекс бара,
на котором они ПОДТВЕРЖДЕНЫ (для защиты от look-ahead в бэктесте).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"


class Trend(str, Enum):
    UP = "up"
    DOWN = "down"
    RANGE = "range"


class SwingType(str, Enum):
    HIGH = "high"
    LOW = "low"


class PoolType(str, Enum):
    BSL = "bsl"  # buy-side liquidity (над хаями)
    SSL = "ssl"  # sell-side liquidity (под лоями)


@dataclass(frozen=True)
class Candle:
    """OHLCV свеча. index — позиция в серии; ts — время открытия (unix ms)."""
    index: int
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def is_bull(self) -> bool:
        return self.close > self.open

    @property
    def is_bear(self) -> bool:
        return self.close < self.open

    @property
    def body_high(self) -> float:
        return max(self.open, self.close)

    @property
    def body_low(self) -> float:
        return min(self.open, self.close)

    @property
    def range(self) -> float:
        return self.high - self.low


@dataclass(frozen=True)
class Swing:
    """Подтверждённый пивот. confirmed_at — индекс бара, на котором подтверждён."""
    type: SwingType
    index: int          # индекс бара-экстремума
    price: float
    confirmed_at: int


@dataclass(frozen=True)
class LiquidityPool:
    type: PoolType
    price: float
    touches: int
    first_index: int
    last_index: int
    swept: bool = False
    swept_at: Optional[int] = None


@dataclass(frozen=True)
class FVG:
    """Fair Value Gap / имбаланс. bearish — направление разрыва."""
    bearish: bool
    low: float
    high: float
    index: int          # индекс средней (i) свечи тройки
    confirmed_at: int   # индекс i+1

    @property
    def mid(self) -> float:
        return (self.low + self.high) / 2.0


@dataclass
class OrderBlock:
    """Блок заказов. score 0..4 — число выполненных условий силы."""
    side: Side           # short = медвежий блок, long = бычий
    index: int           # индекс свечи-блока
    low: float
    high: float
    confirmed_at: int
    swept_liquidity: bool = False
    engulfed: bool = False
    has_fvg: bool = False
    caused_bos: bool = False
    mitigated_at: Optional[int] = None
    invalidated_at: Optional[int] = None

    @property
    def score(self) -> int:
        return int(self.swept_liquidity) + int(self.engulfed) + int(self.has_fvg) + int(self.caused_bos)

    @property
    def is_strong(self) -> bool:
        return self.score == 4

    @property
    def proximal(self) -> float:
        """Ближняя к цене граница входа: для шорта — верх, для лонга — низ."""
        return self.high if self.side == Side.SHORT else self.low

    @property
    def distal(self) -> float:
        """Дальняя граница (за неё ставится стоп)."""
        return self.low if self.side == Side.SHORT else self.high

    def contains(self, price: float) -> bool:
        return self.low <= price <= self.high


@dataclass(frozen=True)
class BOS:
    """Слом структуры (break of structure)."""
    direction: Trend        # UP или DOWN
    break_level: float
    index: int              # индекс свечи, закрывшейся за уровнем
    ob_candle_index: int    # индекс свечи-блока, вызвавшего слом
