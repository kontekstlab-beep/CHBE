"""Тесты reconcile: сверка JSON-стейта движка с биржей (без сети).

Сценарии: pending-ордер исчез с биржи; позиция исчезла (сброс спотового testnet);
брокер отвечает «неизвестно» (None) -> стейт не трогаем.
"""
import logging
import sys
import types

import pytest

from paper.broker import DryRunBroker, SpotTestnetBroker
from paper.config import PaperConfig
from paper.engine import PaperEngine, Pending, Position, SymbolState, reconcile


class FakeSpotExchange:
    """Минимальная имитация ccxt binance для reconcile (без сети)."""

    def __init__(self, config):
        self.config = config
        self.urls = {"api": "https://testnet.binance.vision/api"}
        self.markets = {"BTC/USDT": {"symbol": "BTC/USDT", "base": "BTC"}}
        self.open_orders = []        # список dict(id=..., symbol=...)
        self.free_base = 0.0         # свободный баланс BTC
        self.fail_orders = False     # True -> fetch_open_orders падает
        self.fail_balance = False    # True -> fetch_balance падает

    def set_sandbox_mode(self, flag):
        self.sandbox = flag

    def load_markets(self):
        return self.markets

    def market(self, symbol):
        return self.markets[symbol]

    def fetch_open_orders(self, symbol):
        if self.fail_orders:
            raise RuntimeError("network down")
        return [o for o in self.open_orders if o["symbol"] == symbol]

    def fetch_balance(self):
        if self.fail_balance:
            raise RuntimeError("network down")
        return {"USDT": {"total": 1000.0}, "BTC": {"free": self.free_base}}


@pytest.fixture
def broker(monkeypatch):
    """SpotTestnetBroker на FakeSpotExchange через поддельный модуль ccxt."""
    mod = types.ModuleType("ccxt")
    mod.binance = FakeSpotExchange
    monkeypatch.setitem(sys.modules, "ccxt", mod)
    monkeypatch.setenv("BINANCE_TESTNET_KEY", "k")
    monkeypatch.setenv("BINANCE_TESTNET_SECRET", "s")
    return SpotTestnetBroker(log=logging.getLogger("test"))


def _engine_with(symbol="BTC/USDT", pending=None, position=None):
    eng = PaperEngine(PaperConfig(symbols=[symbol]), DryRunBroker())
    st = SymbolState()
    st.pending = pending
    st.position = position
    eng.states[symbol] = st
    return eng


def test_reconcile_drops_missing_pending(broker):
    # ордер есть в стейте, но на бирже открытых ордеров нет -> снимаем со стейта
    eng = _engine_with(pending=Pending(oid="111", price=100.0, placed_bar=0))
    reconcile(eng, broker)
    assert eng.states["BTC/USDT"].pending is None


def test_reconcile_keeps_existing_pending(broker):
    broker.ex.open_orders = [dict(id="111", symbol="BTC/USDT")]
    eng = _engine_with(pending=Pending(oid="111", price=100.0, placed_bar=0))
    reconcile(eng, broker)
    assert eng.states["BTC/USDT"].pending is not None


def test_reconcile_drops_ghost_position(broker):
    # сброс testnet: позиция в стейте, а base-актива на бирже нет -> drop без сделки
    pos = Position(entry=100.0, qty=0.5, entry_bar=1, sell_oid=None, target=101.0)
    eng = _engine_with(position=pos)
    broker.ex.free_base = 0.0
    reconcile(eng, broker)
    assert eng.states["BTC/USDT"].position is None
    assert eng.trades == []                      # сделка НЕ журналируется
    assert eng.equity == eng.cfg.start_equity    # equity не трогаем


def test_reconcile_keeps_position_when_held(broker):
    pos = Position(entry=100.0, qty=0.5, entry_bar=1, sell_oid="222", target=101.0)
    eng = _engine_with(position=pos)
    broker.ex.free_base = 0.5
    broker.ex.open_orders = [dict(id="222", symbol="BTC/USDT")]
    reconcile(eng, broker)
    st = eng.states["BTC/USDT"]
    assert st.position is not None and st.position.sell_oid == "222"


def test_reconcile_clears_missing_sell_order(broker):
    # лимит-продажа исчезла с биржи, но актив есть -> забываем oid, позиция остаётся
    pos = Position(entry=100.0, qty=0.5, entry_bar=1, sell_oid="222", target=101.0)
    eng = _engine_with(position=pos)
    broker.ex.free_base = 0.5
    reconcile(eng, broker)
    st = eng.states["BTC/USDT"]
    assert st.position is not None and st.position.sell_oid is None


def test_reconcile_unknown_keeps_state(broker):
    # биржа недоступна (None = неизвестно) -> стейт НЕ трогаем
    pos = Position(entry=100.0, qty=0.5, entry_bar=1, sell_oid="222", target=101.0)
    eng = _engine_with(pending=Pending(oid="111", price=100.0, placed_bar=0), position=pos)
    broker.ex.fail_orders = True
    broker.ex.fail_balance = True
    reconcile(eng, broker)
    st = eng.states["BTC/USDT"]
    assert st.pending is not None
    assert st.position is not None and st.position.sell_oid == "222"


def test_reconcile_dryrun_is_noop():
    # DryRunBroker: заглушки возвращают None -> reconcile ничего не меняет
    pos = Position(entry=100.0, qty=0.5, entry_bar=1, sell_oid=1, target=101.0)
    eng = _engine_with(pending=Pending(oid=2, price=100.0, placed_bar=0), position=pos)
    reconcile(eng, eng.broker)
    st = eng.states["BTC/USDT"]
    assert st.pending is not None and st.position is not None
