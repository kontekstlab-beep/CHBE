"""Тесты SpotTestnetBroker (и регрессия TestnetBroker) без сети: ccxt мокается.

FakeExchange имитирует минимальный интерфейс ccxt-объекта binance:
sandbox-режим, рынки с лимитами, создание/отмену/опрос ордеров, баланс.
"""
import logging

import pytest

import ccxt

from paper.broker import SpotTestnetBroker, TestnetBroker


class FakeExchange:
    """Минимальная имитация ccxt-объекта биржи (без сети)."""

    def __init__(self, config):
        self.config = config
        self.sandbox = False
        self.markets = {
            "BTC/USDT": {
                "symbol": "BTC/USDT",
                "limits": {"amount": {"min": 0.0001}, "cost": {"min": 10.0}},
            },
        }
        self.orders = {}
        self._oid = 0
        self.created = []          # журнал create_order для проверки параметров

    # --- инфраструктура ---
    def set_sandbox_mode(self, flag):
        self.sandbox = flag

    def load_markets(self):
        return self.markets

    def market(self, symbol):
        return self.markets[symbol]

    def price_to_precision(self, symbol, price):
        return round(float(price), 2)

    def amount_to_precision(self, symbol, qty):
        return round(float(qty), 4)

    def fetch_balance(self):
        return {"USDT": {"total": 1000.0}}

    # --- ордера ---
    def create_order(self, symbol, otype, side, qty, price=None, params=None):
        self._oid += 1
        self.created.append(dict(symbol=symbol, type=otype, side=side,
                                 qty=qty, price=price, params=params or {}))
        order = dict(id=str(self._oid), symbol=symbol, side=side,
                     price=price, filled=qty, average=price or 100.0,
                     status="open")
        self.orders[order["id"]] = order
        return order

    def cancel_order(self, order_id, symbol):
        self.orders.pop(str(order_id), None)

    def fetch_order(self, order_id, symbol):
        o = self.orders[str(order_id)]
        if o is None:
            raise KeyError(order_id)
        return o

    def set_leverage(self, leverage, symbol):
        self.leverage = leverage

    # --- помощники для тестов ---
    def fill(self, order_id):
        """Пометить ордер исполненным (как закрытый на бирже)."""
        self.orders[str(order_id)]["status"] = "closed"


@pytest.fixture
def fake_spot(monkeypatch):
    """SpotTestnetBroker на FakeExchange вместо ccxt.binance (без ключей сети)."""
    monkeypatch.setattr(ccxt, "binance", FakeExchange)
    monkeypatch.setenv("BINANCE_TESTNET_KEY", "k")
    monkeypatch.setenv("BINANCE_TESTNET_SECRET", "s")
    broker = SpotTestnetBroker(log=logging.getLogger("test"))
    return broker


def test_spot_requires_keys(monkeypatch):
    monkeypatch.setattr(ccxt, "binance", FakeExchange)
    monkeypatch.delenv("BINANCE_TESTNET_KEY", raising=False)
    monkeypatch.delenv("BINANCE_TESTNET_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="testnet\\.binance\\.vision"):
        SpotTestnetBroker()


def test_spot_uses_binance_spot_sandbox(fake_spot):
    assert fake_spot.name == "spot-testnet"
    assert isinstance(fake_spot.ex, FakeExchange)
    assert fake_spot.ex.sandbox is True            # ccxt -> testnet.binance.vision
    assert fake_spot.ex.config["apiKey"] == "k"
    # на споте плеча нет: ни атрибута leverage, ни вызовов set_leverage
    assert not hasattr(fake_spot, "leverage")
    assert not hasattr(fake_spot.ex, "leverage")


def test_spot_limit_orders_postonly_no_reduceonly(fake_spot):
    oid = fake_spot.place_limit_buy("BTC/USDT", 100.0, 0.2)
    assert oid is not None
    p = fake_spot.ex.created[-1]["params"]
    assert p == {"postOnly": True}

    oid = fake_spot.place_limit_sell("BTC/USDT", 105.0, 0.2)
    assert oid is not None
    p = fake_spot.ex.created[-1]["params"]
    assert p == {"postOnly": True}                  # reduceOnly на споте НЕТ


def test_spot_market_sell_no_reduceonly(fake_spot):
    res = fake_spot.market_sell("BTC/USDT", 0.2, ref_price=100.0)
    assert res["side"] == "sell" and res["maker"] is False
    o = fake_spot.ex.created[-1]
    assert o["type"] == "market" and o["side"] == "sell"
    assert o["params"] == {}                        # reduceOnly на споте НЕТ


def test_spot_skips_order_below_min_notional(fake_spot):
    # 0.0001 BTC по 100 = 0.01 USDT < min cost 10 -> ордер пропускается
    assert fake_spot.place_limit_buy("BTC/USDT", 100.0, 0.0001) is None
    assert fake_spot.ex.created == []               # на биржу ничего не ушло
    # 0.2 BTC по 100 = 20 USDT >= 10 -> проходит
    assert fake_spot.place_limit_buy("BTC/USDT", 100.0, 0.2) is not None


def test_spot_sync_returns_fills(fake_spot):
    oid = fake_spot.place_limit_buy("BTC/USDT", 100.0, 0.2)
    candle = dict(ts=0, o=100, h=101, l=99, c=100)
    assert fake_spot.sync("BTC/USDT", candle) == []   # ордер ещё открыт
    fake_spot.ex.fill(oid)
    fills = fake_spot.sync("BTC/USDT", candle)
    assert len(fills) == 1
    assert fills[0]["side"] == "buy" and fills[0]["qty"] == 0.2
    assert fake_spot.sync("BTC/USDT", candle) == []   # повторно fill не выдаётся


def test_spot_preflight_and_equity(fake_spot):
    info = fake_spot.preflight()
    assert info["usdt"] == 1000.0 and info["markets"] == 1
    assert fake_spot.equity() == 1000.0


def test_futures_broker_keeps_reduceonly(monkeypatch):
    """Регрессия: фьючерсный TestnetBroker по-прежнему шлёт reduceOnly и плечо."""
    monkeypatch.setattr(ccxt, "binanceusdm", FakeExchange)
    monkeypatch.setenv("BINANCE_TESTNET_KEY", "k")
    monkeypatch.setenv("BINANCE_TESTNET_SECRET", "s")
    broker = TestnetBroker(leverage=1, log=logging.getLogger("test"))
    broker.place_limit_sell("BTC/USDT", 105.0, 0.2)
    assert broker.ex.created[-1]["params"] == {"postOnly": True, "reduceOnly": True}
    broker.market_sell("BTC/USDT", 0.2, ref_price=100.0)
    assert broker.ex.created[-1]["params"] == {"reduceOnly": True}
    assert broker.ex.leverage == 1                  # плечо выставлено


def test_futures_requires_keys(monkeypatch):
    monkeypatch.setattr(ccxt, "binanceusdm", FakeExchange)
    monkeypatch.delenv("BINANCE_TESTNET_KEY", raising=False)
    monkeypatch.delenv("BINANCE_TESTNET_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="testnet\\.binancefuture\\.com"):
        TestnetBroker()
