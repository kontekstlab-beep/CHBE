"""Замороженные параметры paper-стратегии (из исследования)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class PaperConfig:
    # --- стратегия (заморожено) ---
    sma_n: int = 48
    entry_z: float = -2.0
    exit_z: float = 0.0
    max_hold: int = 8          # баров (1h)
    stop_frac: float = 0.08    # катастроф-стоп
    fill_window: int = 3       # баров ждём исполнения лимитки, иначе отмена
    # --- риск/сайзинг ---
    size_frac: float = 0.05    # доля капитала на позицию
    max_concurrent: int = 999  # без лимита (доказано, что лимит вредит)
    # --- исполнение ---
    timeframe: str = "1h"
    # корзина (широкая диверсификация; можно менять)
    symbols: List[str] = field(default_factory=lambda: [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "LINK/USDT", "AVAX/USDT",
        "DOT/USDT", "ADA/USDT", "ARB/USDT", "OP/USDT", "APT/USDT",
    ])
    start_equity: float = 1000.0
    # комиссии для dry-run учёта (Binance futures VIP0)
    maker_fee: float = 0.0002
    taker_fee: float = 0.0005
