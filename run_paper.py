"""Запуск paper-стратегии mean-reversion.

Режимы:
  # офлайн-демо (безопасно, без ключей): реплей движка по кэшу data/
  python run_paper.py --once

  # живой цикл на ПУБЛИЧНЫХ данных, симуляция филлов (без ключей, без ордеров)
  python run_paper.py --live

  # живой цикл с РЕАЛЬНЫМИ ордерами на Binance TESTNET (нужны ключи в окружении)
  #   export BINANCE_TESTNET_KEY=...   BINANCE_TESTNET_SECRET=...
  python run_paper.py --live --testnet

Ключи НЕ хардкодятся и вводятся только вами (см. README, раздел paper).
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import time

from paper.broker import DryRunBroker
from paper.config import PaperConfig
from paper.engine import PaperEngine
from paper import state as state_mod

# пути настраиваются через окружение (для монтирования тома на VPS)
STATE_PATH = os.environ.get("PAPER_STATE", "paper_state.json")
LOG_PATH = os.environ.get("PAPER_LOG", "paper.log")
REPLAY_BARS = 1500


def load_cached(symbol: str, timeframe: str):
    path = os.path.join("data", symbol.replace("/", "") + f"_{timeframe}_4000.csv")
    if not os.path.exists(path):
        return None
    out = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.append(dict(ts=int(float(r["ts"])), o=float(r["open"]),
                            h=float(r["high"]), l=float(r["low"]), c=float(r["close"])))
    return out


def run_once(cfg: PaperConfig):
    """Офлайн-реплей по кэшу: демонстрирует весь пайплайн детерминированно."""
    eng = PaperEngine(cfg, DryRunBroker())
    series = {}
    for s in cfg.symbols:
        c = load_cached(s, cfg.timeframe)
        if c:
            series[s] = c[-REPLAY_BARS:]
    if not series:
        print("Нет кэша в data/. Сначала: python -c \"from smartmoney.data import get_cached; "
              "get_cached('BTC/USDT','1h',4000)\"")
        return
    L = min(len(v) for v in series.values())
    syms = list(series.keys())
    for i in range(L):
        for s in syms:
            eng.step(s, series[s][i])
    m = eng.summary()
    print("=== PAPER (офлайн-реплей по кэшу) ===")
    print(f"Монет: {len(syms)} | баров: {L}")
    print(f"Сделок: {m['trades']}  винрейт: {m['winrate']:.1f}%  "
          f"P&L: {m['pnl']:+.2f}  equity: {m['equity']:.2f}  "
          f"(старт {cfg.start_equity:.0f})")
    print(f"Открытых позиций сейчас: {m['open_positions']}")
    if m["trades"]:
        net_per = m["pnl"] / m["trades"] / cfg.start_equity / cfg.size_frac * 100
        print(f"Средний нетто/сделку (в % от риска позиции): {net_per:+.3f}%")


def make_broker(testnet: bool):
    if testnet:
        from paper.broker import TestnetBroker
        return TestnetBroker(leverage=1)
    return DryRunBroker()


def run_check():
    """Предполётная проверка testnet: подключение + баланс, БЕЗ сделок."""
    from paper.broker import TestnetBroker
    broker = TestnetBroker(leverage=1)
    info = broker.preflight()
    print("=== TESTNET preflight ===")
    print(f"Подключение OK. Баланс USDT: {info['usdt']:.2f} | рынков загружено: {info['markets']}")
    if info["usdt"] <= 0:
        print("ВНИМАНИЕ: нулевой баланс. На testnet.binancefuture.com нажмите "
              "'Perpetual Futures' и пополните тестовый баланс (кнопка faucet).")
    else:
        print("Готово к запуску: python run_paper.py --live --testnet")


def run_live(cfg: PaperConfig, testnet: bool):
    import ccxt
    pub = ccxt.binanceusdm({"enableRateLimit": True})
    broker = make_broker(testnet)
    eng = PaperEngine(cfg, broker)
    if os.path.exists(STATE_PATH):
        state_mod.load(eng, STATE_PATH)
        logging.info("состояние восстановлено из %s", STATE_PATH)
    # для testnet сайзинг считаем от РЕАЛЬНОГО баланса, а не виртуального
    if testnet:
        try:
            eng.equity = broker.equity()
            logging.info("баланс testnet: %.2f USDT", eng.equity)
        except Exception as e:
            logging.warning("не удалось получить баланс testnet: %s", e)
    last_ts = {s: (eng.states[s].__dict__.get("_last_ts") if s in eng.states else 0) for s in cfg.symbols}

    logging.info("LIVE старт | брокер=%s | монет=%d | state=%s", broker.name, len(cfg.symbols), STATE_PATH)
    tf_ms = 3_600_000
    while True:
        try:
            for s in cfg.symbols:
                try:
                    ohlcv = pub.fetch_ohlcv(s, cfg.timeframe, limit=cfg.sma_n + 6)
                    if len(ohlcv) < cfg.sma_n + 2:
                        continue
                    closed = ohlcv[-2]  # последний ЗАКРЫТЫЙ бар (последний в списке — формирующийся)
                    candle = dict(ts=closed[0], o=closed[1], h=closed[2], l=closed[3], c=closed[4])
                    if candle["ts"] == last_ts.get(s):
                        continue
                    last_ts[s] = candle["ts"]
                    eng.step(s, candle)
                except Exception as e:  # pragma: no cover
                    logging.warning("%s ошибка шага: %s", s, e)
            state_mod.save(eng, STATE_PATH)
            m = eng.summary()
            logging.info("итог: сделок=%d equity=%.2f откр.позиций=%d",
                         m["trades"], m["equity"], m["open_positions"])
        except Exception as e:  # pragma: no cover — цикл не должен падать целиком
            logging.exception("ошибка цикла: %s", e)
        # спим до следующего часа + небольшой запас
        now = time.time()
        sleep_s = tf_ms / 1000 - (now % (tf_ms / 1000)) + 5
        time.sleep(max(30, sleep_s))


def main():
    from logging.handlers import RotatingFileHandler
    for p in (LOG_PATH, STATE_PATH):          # создать каталоги, если задан вложенный путь
        d = os.path.dirname(p)
        if d:
            os.makedirs(d, exist_ok=True)
    fileh = RotatingFileHandler(LOG_PATH, maxBytes=10_000_000, backupCount=3, encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(), fileh])
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="офлайн-реплей по кэшу (демо)")
    ap.add_argument("--live", action="store_true", help="живой цикл на публичных данных")
    ap.add_argument("--testnet", action="store_true", help="реальные ордера на Binance testnet")
    ap.add_argument("--check", action="store_true", help="предполётная проверка testnet (без сделок)")
    args = ap.parse_args()
    cfg = PaperConfig()
    if args.check:
        run_check()
    elif args.live:
        run_live(cfg, args.testnet)
    else:
        run_once(cfg)


if __name__ == "__main__":
    main()
