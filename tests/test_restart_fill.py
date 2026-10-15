"""Restart-fill fix: orders that FILLED while the bot was down must not be
dropped as ghosts by reconcile, and the broker order book must be restorable
so sync() keeps polling them.

Scenario proved live on testnet (B2 died 19:00, restarted 22:11, 4 ladder
limits filled during the downtime were dropped as ghosts -> orphan assets).
"""
import logging
import sys
import types

import pytest

from paper.broker import SpotTestnetBroker
from paper.config import PaperConfig
from paper.engine import PaperEngine, Pending, Position, SymbolState, reconcile

SYM = "BTC/USDT"


class FakeExchange:
    """Minimal ccxt-binance stand-in with fetch_order support."""

    def __init__(self, config):
        self.config = config
        self.urls = {"api": "https://testnet.binance.vision/api"}
        self.markets = {SYM: {"symbol": SYM, "base": "BTC", "limits": {}}}
        self.open_orders = {}       # oid -> {id, symbol}
        self.closed_orders = {}     # oid -> {status, side, average, price, filled}
        self.free_base = 0.0
        self._next = 1000

    def set_sandbox_mode(self, flag):
        self.sandbox = flag

    def load_markets(self):
        return self.markets

    def market(self, symbol):
        return self.markets[symbol]

    def price_to_precision(self, symbol, price):
        return float(price)

    def amount_to_precision(self, symbol, qty):
        return float(qty)

    def create_order(self, symbol, otype, side, qty, price=None, params=None):
        self._next += 1
        oid = str(self._next)
        self.open_orders[oid] = dict(id=oid, symbol=symbol)
        return dict(id=oid, symbol=symbol, side=side, price=price, amount=qty)

    def cancel_order(self, oid, symbol):
        self.open_orders.pop(oid, None)

    def fetch_open_orders(self, symbol):
        return [o for o in self.open_orders.values() if o["symbol"] == symbol]

    def fetch_order(self, oid, symbol):
        if oid in self.closed_orders:
            o = dict(self.closed_orders[oid])
            o["id"] = oid
            return o
        if oid in self.open_orders:
            return dict(id=oid, status="open", side="buy", price=100.0, filled=0.0)
        raise RuntimeError("unknown order")

    def fetch_balance(self):
        return {"USDT": {"total": 1000.0}, "BTC": {"free": self.free_base}}


@pytest.fixture
def broker(monkeypatch):
    mod = types.ModuleType("ccxt")
    mod.binance = FakeExchange
    monkeypatch.setitem(sys.modules, "ccxt", mod)
    monkeypatch.setenv("BINANCE_TESTNET_KEY", "k")
    monkeypatch.setenv("BINANCE_TESTNET_SECRET", "s")
    return SpotTestnetBroker(log=logging.getLogger("test"))


def _engine(brk, pending=None, pending_ladder=None, position=None):
    eng = PaperEngine(PaperConfig(symbols=[SYM]), brk)
    st = SymbolState(closes=[100.0] * 48, lows=[99.0] * 48, bar=48)
    st.pending = pending
    st.pending_ladder = pending_ladder
    st.position = position
    eng.states[SYM] = st
    return eng


def _filled(oid, side="buy", price=100.0, qty=0.5):
    return dict(status="closed", side=side, average=price, price=price, filled=qty)


def test_restore_open_lets_sync_see_fills(broker):
    # стейт с pending; брокер «новый процесс» (книга пуста). restore_open ->
    # sync опрашивает ордер и ловит филл за простой.
    eng = _engine(broker, pending=Pending(oid="111", price=100.0, placed_bar=1))
    broker.restore_open(eng.tracked_orders())
    broker.ex.closed_orders["111"] = _filled("111", price=100.0, qty=0.5)
    fills = broker.sync(SYM, dict(ts=0, o=100, h=101, l=99, c=100))
    assert len(fills) == 1 and fills[0]["order_id"] == "111"


def test_reconcile_processes_entry_filled_during_downtime(broker):
    eng = _engine(broker, pending=Pending(oid="111", price=100.0, placed_bar=1))
    broker.restore_open(eng.tracked_orders())
    broker.ex.closed_orders["111"] = _filled("111", price=100.0, qty=0.5)
    broker.ex.free_base = 0.5
    reconcile(eng, broker)
    st = eng.states[SYM]
    assert st.pending is None
    assert st.position is not None
    assert st.position.entry == 100.0 and st.position.qty == 0.5
    assert st.position.sell_oid is not None          # цель перевыставлена на бирже
    assert "111" not in broker._open                 # забыть, sync не дублирует


def test_reconcile_processes_ladder_filled_during_downtime(broker):
    pos = Position(entry=100.0, qty=0.5, entry_bar=1, sell_oid="222", target=105.0)
    eng = _engine(broker, pending_ladder=Pending(oid="333", price=90.0, placed_bar=2),
                  position=pos)
    broker.restore_open(eng.tracked_orders())
    broker.ex.open_orders["222"] = dict(id="222", symbol=SYM)   # sell жива
    broker.ex.closed_orders["333"] = _filled("333", price=90.0, qty=0.5)
    broker.ex.free_base = 1.0
    reconcile(eng, broker)
    st = eng.states[SYM]
    assert st.pending_ladder is None
    p = st.position
    assert p.ladder_used is True
    assert p.qty == pytest.approx(1.0)                        # усреднение
    assert p.entry == pytest.approx(95.0)                     # (100*0.5+90*0.5)/1
    # sell перевыставлен на полный qty
    new_sells = [o for oid, o in broker.ex.open_orders.items() if oid != "222"]
    assert "222" not in broker.ex.open_orders                 # старый sell отменён
    assert len(new_sells) == 1


def test_reconcile_drops_canceled_during_downtime(broker):
    eng = _engine(broker, pending=Pending(oid="111", price=100.0, placed_bar=1))
    broker.ex.closed_orders["111"] = dict(status="canceled", side="buy",
                                          price=100.0, filled=0.0)
    reconcile(eng, broker)
    st = eng.states[SYM]
    assert st.pending is None
    assert st.position is None
    assert eng.trades == []                                   # без сделки


def test_reconcile_sell_filled_during_downtime_closes_position(broker):
    pos = Position(entry=100.0, qty=0.5, entry_bar=1, sell_oid="222", target=105.0)
    eng = _engine(broker, position=pos)
    broker.restore_open(eng.tracked_orders())
    broker.ex.closed_orders["222"] = _filled("222", side="sell", price=105.0, qty=0.5)
    reconcile(eng, broker)
    st = eng.states[SYM]
    assert st.position is None
    assert len(eng.trades) == 1 and eng.trades[0].reason == "reversion"
    assert eng.trades[0].exit == 105.0


def test_reconcile_unknown_fetch_keeps_state(broker, monkeypatch):
    # fetch_order падает -> «неизвестно» -> стейт не трогаем
    def boom(oid, symbol):
        raise RuntimeError("network down")
    monkeypatch.setattr(broker.ex, "fetch_order", boom)
    eng = _engine(broker, pending=Pending(oid="111", price=100.0, placed_bar=1))
    reconcile(eng, broker)
    assert eng.states[SYM].pending is not None


def test_reconcile_idempotent_no_double_fill(broker):
    eng = _engine(broker, pending=Pending(oid="111", price=100.0, placed_bar=1))
    broker.restore_open(eng.tracked_orders())
    broker.ex.closed_orders["111"] = _filled("111", price=100.0, qty=0.5)
    broker.ex.free_base = 0.5
    reconcile(eng, broker)
    reconcile(eng, broker)      # второй проход: pending уже None -> не дублируется
    st = eng.states[SYM]
    assert st.position is not None and st.position.qty == 0.5
    assert len(eng.trades) == 0
    # и через sync ордер не всплывёт повторно (забыт из книги)
    assert broker.sync(SYM, dict(ts=0, o=100, h=101, l=99, c=100)) == []


def test_tracked_orders_collects_all():
    pos = Position(entry=100.0, qty=0.5, entry_bar=1, sell_oid="222", target=105.0)
    eng = _engine(None, pending=Pending(oid="111", price=100.0, placed_bar=1),
                  pending_ladder=Pending(oid="333", price=90.0, placed_bar=2),
                  position=pos)
    got = sorted(eng.tracked_orders())
    assert got == [("111", SYM, "buy"), ("222", SYM, "sell"), ("333", SYM, "buy")]
