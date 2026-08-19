"""Движок paper-трейдинга: сопровождение ордеров/позиций по закрытым барам.

Схема на каждый закрытый бар символа:
  1) sync брокера -> обработать исполнения (buy fill -> открыть позицию + выставить
     лимит-продажу на среднем; sell fill -> зафиксировать возврат к среднему);
  2) сопровождение позиции: стоп/тайм-выход (market), иначе обновить цель = SMA;
  3) новый вход: z<entry_z и нет позиции/лимитки -> maker-лимитка на покупку;
  4) отмена «протухшей» лимитки после fill_window баров.

Логика сигнала — из paper.signal (общая с бэктестом).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .config import PaperConfig
from .signal import entry_signal, exit_signal, sma, zscore

log = logging.getLogger("paper")


@dataclass
class Position:
    entry: float
    qty: float
    entry_bar: int
    sell_oid: Optional[int] = None
    target: float = 0.0


@dataclass
class Pending:
    oid: int
    price: float
    placed_bar: int


@dataclass
class SymbolState:
    closes: List[float] = field(default_factory=list)
    lows: List[float] = field(default_factory=list)
    bar: int = 0
    position: Optional[Position] = None
    pending: Optional[Pending] = None


@dataclass
class Trade:
    symbol: str
    entry: float
    exit: float
    qty: float
    pnl: float
    reason: str


class PaperEngine:
    def __init__(self, cfg: PaperConfig, broker):
        self.cfg = cfg
        self.broker = broker
        self.equity = cfg.start_equity
        self.states: Dict[str, SymbolState] = {}
        self.trades: List[Trade] = []

    def _st(self, symbol) -> SymbolState:
        return self.states.setdefault(symbol, SymbolState())

    def step(self, symbol: str, candle: dict) -> None:
        """candle = {ts, o, h, l, c}. Должен быть ЗАКРЫТЫМ баром."""
        cfg = self.cfg
        st = self._st(symbol)
        st.bar += 1
        st.closes.append(candle["c"])
        st.lows.append(candle["l"])
        # ограничиваем историю
        keep = cfg.sma_n + 5
        if len(st.closes) > keep:
            st.closes = st.closes[-keep:]
            st.lows = st.lows[-keep:]

        # 1) обработать исполнения брокера
        for f in self.broker.sync(symbol, candle):
            self._on_fill(symbol, st, f)

        # 2) сопровождение открытой позиции
        if st.position is not None:
            self._manage(symbol, st, candle)

        # 3) новый вход
        if st.position is None and st.pending is None:
            if entry_signal(st.closes, cfg.sma_n, cfg.entry_z):
                price = candle["c"]
                qty = (self.equity * cfg.size_frac) / price
                oid = self.broker.place_limit_buy(symbol, price, qty)
                st.pending = Pending(oid, price, st.bar)
                log.info("%s ВХОД лимитка @%.6f qty=%.6f (z<%.1f)", symbol, price, qty, cfg.entry_z)

        # 4) отмена протухшей лимитки
        if st.pending is not None and (st.bar - st.pending.placed_bar) > cfg.fill_window:
            self.broker.cancel(symbol, st.pending.oid)
            log.info("%s лимитка отменена (не исполнилась за %d баров)", symbol, cfg.fill_window)
            st.pending = None

    def _on_fill(self, symbol, st: SymbolState, f: dict):
        cfg = self.cfg
        if f["side"] == "buy" and st.pending is not None:
            # открыли позицию; ставим лимит-продажу на среднем (maker reversion-выход)
            entry = f["price"]
            target = sma(st.closes, cfg.sma_n) or entry
            sell_oid = self.broker.place_limit_sell(symbol, target, f["qty"])
            st.position = Position(entry=entry, qty=f["qty"], entry_bar=st.bar,
                                   sell_oid=sell_oid, target=target)
            st.pending = None
            log.info("%s ПОЗИЦИЯ открыта @%.6f, цель=%.6f", symbol, entry, target)
        elif f["side"] == "sell" and st.position is not None:
            self._close(symbol, st, f["price"], f.get("maker", True), "reversion")

    def _manage(self, symbol, st: SymbolState, candle: dict):
        cfg = self.cfg
        p = st.position
        bars_held = st.bar - p.entry_bar
        reason = exit_signal(st.closes, cfg.sma_n, cfg.exit_z, bars_held, cfg.max_hold,
                             p.entry, candle["l"], cfg.stop_frac)
        if reason in ("stop", "time"):
            if p.sell_oid is not None:
                self.broker.cancel(symbol, p.sell_oid)
            fill = self.broker.market_sell(symbol, p.qty, candle["c"])
            self._close(symbol, st, fill["price"], False, reason)
        else:
            # обновляем цель (лимит-продажу) под текущее среднее
            new_t = sma(st.closes, cfg.sma_n)
            if new_t and abs(new_t - p.target) / p.target > 0.0005:
                if p.sell_oid is not None:
                    self.broker.cancel(symbol, p.sell_oid)
                p.sell_oid = self.broker.place_limit_sell(symbol, new_t, p.qty)
                p.target = new_t

    def _close(self, symbol, st: SymbolState, exit_px: float, exit_maker: bool, reason: str):
        cfg = self.cfg
        p = st.position
        fee_in = cfg.maker_fee                      # вход всегда maker-лимитка
        fee_out = cfg.maker_fee if exit_maker else cfg.taker_fee
        pnl = p.qty * (exit_px - p.entry) - p.qty * (p.entry * fee_in + exit_px * fee_out)
        self.equity += pnl
        self.trades.append(Trade(symbol, p.entry, exit_px, p.qty, pnl, reason))
        st.position = None
        log.info("%s ЗАКРЫТА @%.6f [%s] pnl=%.4f equity=%.2f",
                 symbol, exit_px, reason, pnl, self.equity)

    # --- отчётность ---
    def summary(self) -> dict:
        n = len(self.trades)
        wins = sum(1 for t in self.trades if t.pnl > 0)
        pnl = sum(t.pnl for t in self.trades)
        open_pos = sum(1 for s in self.states.values() if s.position is not None)
        return dict(trades=n, wins=wins, winrate=(wins / n * 100 if n else 0),
                    pnl=pnl, equity=self.equity, open_positions=open_pos)
