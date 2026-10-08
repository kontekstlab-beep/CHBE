"""Регрессия: знак ATR-стопа в build_bracket.

Буфер sl_buffer_atr должен РАСШИРЯТЬ стоп на обеих сторонах:
LONG — ниже входа на (sl_atr_mult + sl_buffer_atr)*ATR, SHORT — выше на ту же
величину. Ранее для LONG буфер СУЖАЛ стоп (баг знака).
"""
from types import SimpleNamespace

from smartmoney.config import Config
from smartmoney.models import Candle, Side
from smartmoney.strategy import build_bracket


def _cfg():
    cfg = Config()
    cfg.risk.use_limit_entry = False      # вход по рынку: entry = cur.close
    cfg.entry.sl_mode = "atr"
    cfg.entry.sl_atr_mult = 1.0
    cfg.entry.target_mode = "rr"          # цель фикс-RR: пулы ликвидности не нужны
    cfg.entry.target_rr = 1.0
    cfg.risk.sl_buffer_atr = 0.1
    return cfg


def _bracket(side):
    candle = Candle(index=0, ts=0, open=100.0, high=101.0, low=99.0, close=100.0)
    bos = SimpleNamespace(ob_candle_index=0)
    return build_bracket(_cfg(), [candle], side, bos, candle, a=2.0, pools=[])


def test_atr_stop_buffer_widens_long():
    entry, sl, tp, is_limit = _bracket(Side.LONG)
    # стоп ниже входа ровно на (1.0 + 0.1) * 2.0 = 2.2
    assert entry == 100.0
    assert abs((entry - sl) - 2.2) < 1e-9
    assert sl < entry                      # стоп лонга СТРОГО ниже входа


def test_atr_stop_buffer_widens_short():
    entry, sl, tp, is_limit = _bracket(Side.SHORT)
    assert entry == 100.0
    assert abs((sl - entry) - 2.2) < 1e-9
    assert sl > entry                      # стоп шорта СТРОГО выше входа
