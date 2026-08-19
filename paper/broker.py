"""Брокеры: DryRunBroker (симуляция, без ключей) и TestnetBroker (ccxt sandbox).

Единый интерфейс. Движок вызывает sync(symbol, candle) на каждом закрытом баре,
получая список исполнений (fills). Для dry-run исполнения считаются по свече;
для testnet — опрашивается биржа.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional


class DryRunBroker:
    """Симуляция исполнения по OHLC-свече. Ничего не отправляет наружу."""
    name = "dry-run"

    def __init__(self):
        self._orders: Dict[int, dict] = {}
        self._oid = 0

    def _new(self, symbol, side, price, qty, post_only=True) -> int:
        self._oid += 1
        self._orders[self._oid] = dict(id=self._oid, symbol=symbol, side=side,
                                       price=price, qty=qty, post_only=post_only)
        return self._oid

    def place_limit_buy(self, symbol, price, qty) -> int:
        return self._new(symbol, "buy", price, qty)

    def place_limit_sell(self, symbol, price, qty) -> int:
        return self._new(symbol, "sell", price, qty)

    def cancel(self, symbol, order_id) -> None:
        self._orders.pop(order_id, None)

    def market_sell(self, symbol, qty, ref_price) -> dict:
        return dict(side="sell", price=ref_price, qty=qty, maker=False)

    def sync(self, symbol, candle) -> List[dict]:
        """Исполняет лимитки: buy при low<=price, sell при high>=price (maker)."""
        fills = []
        for oid, o in list(self._orders.items()):
            if o["symbol"] != symbol:
                continue
            if o["side"] == "buy" and candle["l"] <= o["price"]:
                fills.append(dict(order_id=oid, side="buy", price=o["price"], qty=o["qty"], maker=True))
                del self._orders[oid]
            elif o["side"] == "sell" and candle["h"] >= o["price"]:
                fills.append(dict(order_id=oid, side="sell", price=o["price"], qty=o["qty"], maker=True))
                del self._orders[oid]
        return fills

    def open_order_ids(self, symbol) -> List[int]:
        return [oid for oid, o in self._orders.items() if o["symbol"] == symbol]


class TestnetBroker:
    """Реальные ордера на Binance USDT-M Futures TESTNET через ccxt.

    Ключи берутся ИЗ ОКРУЖЕНИЯ (никогда не хардкодятся):
        BINANCE_TESTNET_KEY, BINANCE_TESTNET_SECRET
    Права ключа — только фьючерсная торговля, БЕЗ вывода средств.
    """
    name = "testnet"

    def __init__(self):
        try:
            import ccxt  # noqa
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("нужен ccxt: pip install ccxt") from e
        key = os.environ.get("BINANCE_TESTNET_KEY")
        secret = os.environ.get("BINANCE_TESTNET_SECRET")
        if not key or not secret:
            raise RuntimeError(
                "не заданы ключи testnet. Создайте их на testnet.binancefuture.com и "
                "экспортируйте BINANCE_TESTNET_KEY / BINANCE_TESTNET_SECRET.")
        import ccxt
        self.ex = ccxt.binanceusdm({
            "apiKey": key, "secret": secret,
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        })
        self.ex.set_sandbox_mode(True)  # TESTNET
        self.ex.load_markets()

    def place_limit_buy(self, symbol, price, qty):
        o = self.ex.create_order(symbol, "limit", "buy", qty, price,
                                 params={"postOnly": True})
        return o["id"]

    def place_limit_sell(self, symbol, price, qty):
        o = self.ex.create_order(symbol, "limit", "sell", qty, price,
                                 params={"postOnly": True, "reduceOnly": True})
        return o["id"]

    def cancel(self, symbol, order_id):
        try:
            self.ex.cancel_order(order_id, symbol)
        except Exception:
            pass

    def market_sell(self, symbol, qty, ref_price=None):
        o = self.ex.create_order(symbol, "market", "sell", qty,
                                 params={"reduceOnly": True})
        return dict(side="sell", price=o.get("average") or ref_price, qty=qty, maker=False)

    def sync(self, symbol, candle) -> List[dict]:
        """Опрашивает открытые ордера; помечает исполненные как fills."""
        fills = []
        for o in self.ex.fetch_orders(symbol, limit=20):
            if o["status"] == "closed" and o.get("filled"):
                fills.append(dict(order_id=o["id"], side=o["side"],
                                  price=o.get("average") or o["price"],
                                  qty=o["filled"], maker=True))
        return fills

    def equity(self) -> float:
        bal = self.ex.fetch_balance()
        return float(bal["USDT"]["total"])
