"""Персистентность состояния движка (JSON) для рестарт-устойчивости.

Сохраняем equity, сделки и по-символьное состояние (история/позиция/лимитка).
Для testnet источник истины — биржа; JSON служит журналом и восстановлением
локального контекста (история цен, счётчики).
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Optional

from .engine import PaperEngine, Pending, Position, SymbolState, Trade


def save(engine: PaperEngine, path: str) -> None:
    data = {
        "equity": engine.equity,
        "trades": [asdict(t) for t in engine.trades],
        "states": {
            sym: {
                "closes": s.closes, "lows": s.lows, "bar": s.bar,
                "position": asdict(s.position) if s.position else None,
                "pending": asdict(s.pending) if s.pending else None,
            } for sym, s in engine.states.items()
        },
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load(engine: PaperEngine, path: str) -> None:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    engine.equity = data.get("equity", engine.equity)
    engine.trades = [Trade(**t) for t in data.get("trades", [])]
    engine.states = {}
    for sym, s in data.get("states", {}).items():
        st = SymbolState(closes=s["closes"], lows=s["lows"], bar=s["bar"])
        if s.get("position"):
            st.position = Position(**s["position"])
        if s.get("pending"):
            st.pending = Pending(**s["pending"])
        engine.states[sym] = st
