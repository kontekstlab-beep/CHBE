"""Событийный бэктестер (bar-by-bar), без look-ahead.

Порядок на каждом закрытом баре для ОТКРЫТОЙ позиции:
  1) полный выход по текущему SL/TP (SL первым при неоднозначности) — закрывает
     остаток позиции; результат агрегируется в одну сделку (Trade);
  2) частичная фиксация: при достижении +partial_at_r закрываем долю partial_frac,
     двигаем SL в безубыток и включаем трейлинг остатка;
  3) обновление трейлинг-стопа остатка (за экстремумом ± trail_atr_mult*ATR);
  4) если позиции нет — обслуживаем лимитку (fill/TTL) или спрашиваем сигнал.

Одна позиция -> одна запись Trade с суммарным P&L (частичные фиксации свёрнуты).
Стратегии передаётся индекс t; она уже вычислила примитивы «as-of» в prepare().
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .config import Config
from .metrics import Metrics, compute_metrics
from .models import Candle, Side
from .sizing import position_size
from .strategy import Signal, Strategy
from .structure import atr


@dataclass
class BacktestConfig:
    starting_equity: float = 1000.0
    fee_bps: float = 4.0
    slippage_bps: float = 2.0


@dataclass
class Trade:
    side: Side
    entry_index: int
    exit_index: int
    entry: float
    exit: float
    qty: float
    pnl: float
    r_multiple: float
    reason: str          # 'tp' | 'sl' | 'be' | 'trail'
    ob_index: int
    partial: bool = False  # была ли частичная фиксация по пути


@dataclass
class BacktestResult:
    trades: List[Trade]
    equity_curve: List[float]
    metrics: Metrics
    filled: int = 0
    cancelled: int = 0


@dataclass
class _Pending:
    side: Side
    entry: float
    stop_loss: float
    take_profit: float
    created_index: int
    ob_index: int
    reason: str


@dataclass
class _Position:
    side: Side
    entry_index: int
    entry: float
    stop_loss: float
    take_profit: float
    qty: float               # остаток
    init_qty: float          # исходный объём (для записи)
    risk_amount: float
    stop_distance0: float
    ob_index: int
    reason: str
    realized_pnl: float = 0.0
    partial_done: bool = False
    partial_flag: bool = False
    moved_be: bool = False
    trailing_on: bool = False
    fav_extreme: float = 0.0


class Backtester:
    def __init__(self, cfg: Config, bt: Optional[BacktestConfig] = None):
        self.cfg = cfg
        self.bt = bt or BacktestConfig()

    def run(self, candles: List[Candle], strategy: Strategy) -> BacktestResult:
        equity = self.bt.starting_equity
        equity_curve: List[float] = [equity]
        trades: List[Trade] = []
        pos: Optional[_Position] = None
        pending: Optional[_Pending] = None
        filled = cancelled = 0
        slip = self.bt.slippage_bps / 10_000.0
        fee = self.bt.fee_bps / 10_000.0
        rc = self.cfg.risk
        atr_series = atr(candles, self.cfg.orderblock.atr_period)

        strategy.prepare(candles)

        for t, c in enumerate(candles):
            # 1) сопровождение открытой позиции
            if pos is not None:
                closed_pnl = self._manage(pos, c, t, slip, fee, rc, atr_series)
                if closed_pnl is not None:
                    equity += closed_pnl
                    equity_curve.append(equity)
                    trades.append(self._last_trade)
                    pos = None

            # 2) обслуживание лимитки
            if pos is None and pending is not None:
                if (t - pending.created_index) > rc.order_ttl_bars:
                    pending = None
                    cancelled += 1
                elif self._limit_hit(pending, c):
                    pos = self._open_from_pending(pending, equity, t)
                    pending = None
                    filled += 1
                    # на баре входа — только немедленный SL/TP (без БУ/частички/трейла)
                    closed_pnl = self._try_full_exit(pos, c, t, slip, fee)
                    if closed_pnl is not None:
                        equity += closed_pnl
                        equity_curve.append(equity)
                        trades.append(self._last_trade)
                        pos = None

            # 3) новый сигнал
            if pos is None and pending is None:
                sig = strategy.evaluate_at(t)
                if sig is not None:
                    if sig.is_limit and rc.use_limit_entry:
                        pending = _Pending(sig.side, sig.entry, sig.stop_loss,
                                           sig.take_profit, t, sig.ob_index, sig.reason)
                    else:
                        pos = self._open_market(sig, equity, slip, t)

        return BacktestResult(trades, equity_curve,
                              self._metrics(trades, equity_curve), filled, cancelled)

    # --- полный выход по текущему SL/TP (закрывает остаток, агрегирует P&L) ---
    def _try_full_exit(self, pos: _Position, c: Candle, t: int,
                       slip: float, fee: float) -> Optional[float]:
        exit_price, reason = self._check_exit(pos, c)
        if exit_price is None:
            return None
        exit_fill = self._exit_fill(pos.side, exit_price, slip)
        leg = self._leg_pnl(pos, pos.qty, exit_fill, fee)
        total = pos.realized_pnl + leg
        r = total / pos.risk_amount if pos.risk_amount else 0.0
        self._last_trade = Trade(pos.side, pos.entry_index, t, pos.entry, exit_fill,
                                 pos.init_qty, total, r, reason, pos.ob_index, pos.partial_flag)
        return total

    # --- управление позицией (возвращает суммарный P&L при полном закрытии) ---
    def _manage(self, pos: _Position, c: Candle, t: int, slip: float, fee: float,
                rc, atr_series) -> Optional[float]:
        # 1) полный выход по SL/TP (SL первым)
        closed = self._try_full_exit(pos, c, t, slip, fee)
        if closed is not None:
            return closed

        # 2) частичная фиксация
        if rc.use_partial and not pos.partial_done and self._reached_r(pos, c, rc.partial_at_r):
            plevel = self._r_level(pos, rc.partial_at_r)
            pqty = pos.init_qty * rc.partial_frac
            pfill = self._exit_fill(pos.side, plevel, slip)
            pos.realized_pnl += self._leg_pnl(pos, pqty, pfill, fee)
            pos.qty -= pqty
            pos.partial_done = True
            pos.partial_flag = True
            pos.stop_loss = pos.entry            # безубыток на остаток
            pos.moved_be = True
        # 2b) обычный безубыток (если частичка не используется)
        elif rc.use_breakeven and not pos.moved_be and self._reached_r(pos, c, rc.breakeven_at_r):
            pos.stop_loss = pos.entry
            pos.moved_be = True

        # 2c) включение трейлинга после достижения безубытка (через частичку или БУ)
        if rc.use_trailing and pos.moved_be and not pos.trailing_on:
            pos.trailing_on = True
            pos.fav_extreme = c.low if pos.side == Side.SHORT else c.high

        # 3) трейлинг остатка
        if pos.trailing_on and rc.use_trailing:
            d = rc.trail_atr_mult * atr_series[t]
            if pos.side == Side.SHORT:
                pos.fav_extreme = min(pos.fav_extreme, c.low)
                pos.stop_loss = min(pos.stop_loss, pos.fav_extreme + d)
            else:
                pos.fav_extreme = max(pos.fav_extreme, c.high)
                pos.stop_loss = max(pos.stop_loss, pos.fav_extreme - d)
        return None

    # --- открытие ---
    def _open_market(self, sig: Signal, equity: float, slip: float, t: int) -> _Position:
        entry_fill = self._entry_fill(sig.side, sig.entry, slip)
        sz = position_size(equity, entry_fill, sig.stop_loss, self.cfg.risk)
        return _Position(sig.side, t, entry_fill, sig.stop_loss, sig.take_profit,
                         sz.qty, sz.qty, sz.risk_amount, abs(entry_fill - sig.stop_loss),
                         sig.ob_index, sig.reason)

    def _open_from_pending(self, p: _Pending, equity: float, t: int) -> _Position:
        sz = position_size(equity, p.entry, p.stop_loss, self.cfg.risk)
        return _Position(p.side, t, p.entry, p.stop_loss, p.take_profit,
                         sz.qty, sz.qty, sz.risk_amount, abs(p.entry - p.stop_loss),
                         p.ob_index, p.reason)

    @staticmethod
    def _limit_hit(p: _Pending, c: Candle) -> bool:
        if p.side == Side.SHORT:
            return c.high >= p.entry
        return c.low <= p.entry

    @staticmethod
    def _reached_r(pos: _Position, c: Candle, r_mult: float) -> bool:
        target = r_mult * pos.stop_distance0
        if pos.side == Side.SHORT:
            return c.low <= pos.entry - target
        return c.high >= pos.entry + target

    @staticmethod
    def _r_level(pos: _Position, r_mult: float) -> float:
        target = r_mult * pos.stop_distance0
        return pos.entry - target if pos.side == Side.SHORT else pos.entry + target

    @staticmethod
    def _entry_fill(side: Side, price: float, slip: float) -> float:
        return price * (1 + slip) if side == Side.LONG else price * (1 - slip)

    @staticmethod
    def _exit_fill(side: Side, price: float, slip: float) -> float:
        return price * (1 - slip) if side == Side.LONG else price * (1 + slip)

    @staticmethod
    def _check_exit(pos: _Position, c: Candle):
        if pos.side == Side.SHORT:
            if c.high >= pos.stop_loss:
                return pos.stop_loss, ("trail" if pos.trailing_on else "be" if pos.moved_be else "sl")
            if c.low <= pos.take_profit:
                return pos.take_profit, "tp"
        else:
            if c.low <= pos.stop_loss:
                return pos.stop_loss, ("trail" if pos.trailing_on else "be" if pos.moved_be else "sl")
            if c.high >= pos.take_profit:
                return pos.take_profit, "tp"
        return None, ""

    @staticmethod
    def _leg_pnl(pos: _Position, qty: float, exit_price: float, fee: float) -> float:
        if pos.side == Side.SHORT:
            gross = qty * (pos.entry - exit_price)
        else:
            gross = qty * (exit_price - pos.entry)
        fees = fee * qty * (pos.entry + exit_price)
        return gross - fees

    def _metrics(self, trades: List[Trade], equity_curve: List[float]) -> Metrics:
        return compute_metrics(
            [t.r_multiple for t in trades],
            [t.pnl for t in trades],
            equity_curve,
            self.bt.starting_equity,
        )
