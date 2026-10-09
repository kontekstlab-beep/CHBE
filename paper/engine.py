"""Движок paper-трейдинга: сопровождение ордеров/позиций по закрытым барам.

Схема на каждый закрытый бар символа:
  1) sync брокера -> обработать исполнения (buy fill -> открыть позицию + выставить
     лимит-продажу на среднем; buy fill лесенки -> усреднить позицию; sell fill ->
     зафиксировать возврат к среднему);
  2) сопровождение позиции: стоп/тайм-выход (market), иначе обновить цель = SMA;
     при z < ladder_z — лесенка (вторая порция, C6), один раз за позицию;
  3) новый вход: z<entry_z, гейт BTC-контекста (C6), нет позиции/лимитки ->
     maker-лимитка на покупку;
  4) отмена «протухших» лимиток после fill_window баров (вход и лесенка).

C6 (M6_RESEARCH.md): baseline + лесенка при z<-3 + фильтр входа по z48(BTC)<-1.
BTC должен степаться ПЕРВЫМ в cfg.symbols — тогда его closes содержат текущий
бар к моменту шага остальных монет. При недостатке данных BTC гейт не блокирует.

Логика сигнала — из paper.signal (общая с бэктестом).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .config import PaperConfig
from .signal import btc_gate, entry_signal, exit_signal, sma, zscore

log = logging.getLogger("paper")


@dataclass
class Position:
    entry: float
    qty: float
    entry_bar: int
    sell_oid: Optional[int] = None
    target: float = 0.0
    ladder_used: bool = False      # вторая порция (C6) уже добавлялась


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
    pending_ladder: Optional[Pending] = None   # лесеночная лимитка (C6)


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

    def _btc_ok(self) -> bool:
        """Гейт BTC-контекста (C6). BTC степается первым в cfg.symbols, поэтому
        его closes уже содержат ТЕКУЩИЙ бар к моменту шага других монет.
        Нет/мало данных BTC -> НЕ блокируем (деградация в baseline)."""
        cfg = self.cfg
        if not cfg.use_btc_filter:
            return True
        bst = self.states.get(cfg.btc_symbol)
        if bst is None:
            return True
        return btc_gate(bst.closes, cfg.sma_n, cfg.btc_filter_z)

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

        # 3) новый вход (с гейтом BTC-контекста, C6)
        if st.position is None and st.pending is None:
            if entry_signal(st.closes, cfg.sma_n, cfg.entry_z) and self._btc_ok():
                price = candle["c"]
                qty = (self.equity * cfg.size_frac) / price
                oid = self.broker.place_limit_buy(symbol, price, qty)
                if oid is not None:                 # None -> ордер отклонён/мал; пропуск
                    st.pending = Pending(oid, price, st.bar)
                    log.info("%s ВХОД лимитка @%.6f qty=%.6f (z<%.1f)", symbol, price, qty, cfg.entry_z)

        # 4) отмена протухших лимиток (вход и лесенка — одинаковый TTL)
        if st.pending is not None and (st.bar - st.pending.placed_bar) > cfg.fill_window:
            self.broker.cancel(symbol, st.pending.oid)
            log.info("%s лимитка отменена (не исполнилась за %d баров)", symbol, cfg.fill_window)
            st.pending = None
        if st.pending_ladder is not None:
            if st.position is None:
                # сирота: позиция закрылась до филла лесенки -> отменить
                self.broker.cancel(symbol, st.pending_ladder.oid)
                st.pending_ladder = None
            elif (st.bar - st.pending_ladder.placed_bar) > cfg.fill_window:
                self.broker.cancel(symbol, st.pending_ladder.oid)
                log.info("%s лесенка отменена (не исполнилась за %d баров)", symbol, cfg.fill_window)
                st.pending_ladder = None

    def _on_fill(self, symbol, st: SymbolState, f: dict):
        cfg = self.cfg
        oid = f.get("order_id")
        if f["side"] == "buy" and st.pending is not None \
                and (oid is None or oid == st.pending.oid):
            # открыли позицию; ставим лимит-продажу на среднем (maker reversion-выход)
            entry = f["price"]
            target = sma(st.closes, cfg.sma_n) or entry
            sell_oid = self.broker.place_limit_sell(symbol, target, f["qty"])
            st.position = Position(entry=entry, qty=f["qty"], entry_bar=st.bar,
                                   sell_oid=sell_oid, target=target)
            st.pending = None
            log.info("%s ПОЗИЦИЯ открыта @%.6f, цель=%.6f", symbol, entry, target)
        elif f["side"] == "buy" and st.pending_ladder is not None \
                and (oid is None or oid == st.pending_ladder.oid):
            # лесенка (C6): усреднение и перевыставление продажи на полный qty
            p = st.position
            st.pending_ladder = None
            if p is None:                      # позиции уже нет — игнорируем (страховка)
                log.warning("%s лесенка исполнилась без позиции — пропуск", symbol)
                return
            p.ladder_used = True
            new_qty = p.qty + f["qty"]
            p.entry = (p.entry * p.qty + f["price"] * f["qty"]) / new_qty
            p.qty = new_qty
            if p.sell_oid is not None:
                self.broker.cancel(symbol, p.sell_oid)
            p.sell_oid = self.broker.place_limit_sell(symbol, p.target, p.qty)
            log.info("%s ЛЕСЕНКА @%.6f: усреднение entry=%.6f qty=%.6f",
                     symbol, f["price"], p.entry, p.qty)
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
            # лесенка (C6): вторая порция при z < ladder_z, один раз за позицию
            if not p.ladder_used and st.pending_ladder is None and cfg.ladder_frac > 0:
                z = zscore(st.closes, cfg.sma_n)
                if z is not None and z < cfg.ladder_z and self._btc_ok():
                    price = candle["c"]
                    qty = (self.equity * cfg.ladder_frac) / price
                    oid = self.broker.place_limit_buy(symbol, price, qty)
                    if oid is not None:
                        st.pending_ladder = Pending(oid, price, st.bar)
                        log.info("%s ЛЕСЕНКА лимитка @%.6f qty=%.6f (z=%.2f<%.1f)",
                                 symbol, price, qty, z, cfg.ladder_z)

    def _close(self, symbol, st: SymbolState, exit_px: float, exit_maker: bool, reason: str):
        cfg = self.cfg
        p = st.position
        if st.pending_ladder is not None:      # лесенка не успела исполниться -> отмена
            self.broker.cancel(symbol, st.pending_ladder.oid)
            st.pending_ladder = None
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


def reconcile(eng: PaperEngine, broker, log=None) -> None:
    """Сверка стейта с биржей (после рестарта, ручных действий, сброса testnet).

    None от брокера («неизвестно», ошибка запроса) -> стейт НЕ трогаем. Иначе:
    - pending-лимитка (вход или лесенка), которой нет среди открытых на бирже,
      -> снимается со стейта;
    - лимит-продажа позиции, которой нет на бирже, -> забывается (перевыставится
      движком при следующей смене цели);
    - позиция, по которой на бирже нет base-актива (held < 10% от qty), ->
      снимается БЕЗ сделки (reconcile-drop): продавать нечего, сделка не журналируется.
    """
    log = log or logging.getLogger("paper")
    for sym, st in eng.states.items():
        if st.pending is not None or st.pending_ladder is not None \
                or (st.position is not None and st.position.sell_oid is not None):
            oids = broker.open_order_ids_on_exchange(sym)
            if oids is not None:
                if st.pending is not None and str(st.pending.oid) not in oids:
                    log.warning("%s reconcile: лимитка %s отсутствует на бирже -> снята со стейта",
                                sym, st.pending.oid)
                    st.pending = None
                if st.pending_ladder is not None and str(st.pending_ladder.oid) not in oids:
                    log.warning("%s reconcile: лесенка %s отсутствует на бирже -> снята со стейта",
                                sym, st.pending_ladder.oid)
                    st.pending_ladder = None
                if st.position is not None and st.position.sell_oid is not None \
                        and str(st.position.sell_oid) not in oids:
                    log.warning("%s reconcile: лимит-продажа %s отсутствует на бирже -> "
                                "забыта (перевыставится при смене цели)", sym, st.position.sell_oid)
                    st.position.sell_oid = None
        if st.position is not None:
            held = broker.held_qty(sym)
            if held is not None and held < 0.1 * st.position.qty:
                log.warning("%s reconcile: позиция %.6f в стейте, на бирже актива %.6f -> "
                            "позиция снята БЕЗ сделки", sym, st.position.qty, held)
                st.position = None
