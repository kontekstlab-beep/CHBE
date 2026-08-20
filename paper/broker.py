"""Брокеры: DryRunBroker (симуляция, без ключей) и TestnetBroker (ccxt sandbox).

Единый интерфейс. Движок вызывает sync(symbol, candle) на каждом закрытом баре,
получая список исполнений (fills). Для dry-run исполнения считаются по свече;
для testnet — опрашивается биржа.
"""
from __future__ import annotations

import logging
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

    def __init__(self, leverage: int = 1, log=None):
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
        self.leverage = leverage
        self._log = log or logging.getLogger("paper")
        self._open: Dict[str, dict] = {}   # order_id -> {symbol, side}
        self._levered = set()

    # --- подготовка инструмента ---
    def _ensure_leverage(self, symbol):
        if symbol in self._levered:
            return
        try:
            self.ex.set_leverage(self.leverage, symbol)
        except Exception as e:  # плечо могло быть уже задано / позиция открыта
            self._log.debug("set_leverage %s: %s", symbol, e)
        self._levered.add(symbol)

    def _round(self, symbol, price, qty):
        price = float(self.ex.price_to_precision(symbol, price))
        qty = float(self.ex.amount_to_precision(symbol, qty))
        return price, qty

    def _meets_min(self, symbol, price, qty) -> bool:
        m = self.ex.market(symbol)
        limits = m.get("limits", {})
        min_amt = (limits.get("amount") or {}).get("min") or 0
        min_cost = (limits.get("cost") or {}).get("min") or 0
        if qty <= 0 or qty < min_amt:
            return False
        if min_cost and price * qty < min_cost:
            return False
        return True

    def _create(self, symbol, side, price, qty, params):
        self._ensure_leverage(symbol)
        price, qty = self._round(symbol, price, qty)
        if price and not self._meets_min(symbol, price, qty):
            self._log.info("%s пропуск ордера: qty=%s не проходит min amount/notional", symbol, qty)
            return None
        try:
            o = self.ex.create_order(symbol, "limit" if price else "market", side,
                                     qty, price or None, params=params)
        except Exception as e:  # postOnly-отказ, precision, маржа и т.п. — это реальные данные
            self._log.warning("%s ордер отклонён (%s): %s", symbol, side, e)
            return None
        self._open[o["id"]] = dict(symbol=symbol, side=side)
        return o["id"]

    def place_limit_buy(self, symbol, price, qty):
        return self._create(symbol, "buy", price, qty, {"postOnly": True})

    def place_limit_sell(self, symbol, price, qty):
        return self._create(symbol, "sell", price, qty, {"postOnly": True, "reduceOnly": True})

    def cancel(self, symbol, order_id):
        self._open.pop(order_id, None)
        try:
            self.ex.cancel_order(order_id, symbol)
        except Exception:
            pass

    def market_sell(self, symbol, qty, ref_price=None):
        self._ensure_leverage(symbol)
        _, qty = self._round(symbol, ref_price or 1, qty)
        o = self.ex.create_order(symbol, "market", "sell", qty, params={"reduceOnly": True})
        return dict(side="sell", price=o.get("average") or ref_price, qty=qty, maker=False)

    def sync(self, symbol, candle) -> List[dict]:
        """Опрашивает ТОЛЬКО свои открытые ордера по символу; исполненные -> fills."""
        fills = []
        for oid in [i for i, o in self._open.items() if o["symbol"] == symbol]:
            try:
                o = self.ex.fetch_order(oid, symbol)
            except Exception as e:
                self._log.debug("fetch_order %s: %s", oid, e)
                continue
            status = o.get("status")
            if status == "closed" and o.get("filled"):
                fills.append(dict(order_id=oid, side=o["side"],
                                  price=o.get("average") or o["price"],
                                  qty=o["filled"], maker=True))
                self._open.pop(oid, None)
            elif status in ("canceled", "rejected", "expired"):
                self._open.pop(oid, None)
        return fills

    def equity(self) -> float:
        bal = self.ex.fetch_balance()
        return float(bal["USDT"]["total"])

    def preflight(self) -> dict:
        """Проверка подключения без сделок: баланс + число рынков."""
        bal = self.ex.fetch_balance()
        return dict(usdt=float(bal["USDT"]["total"]), markets=len(self.ex.markets))
