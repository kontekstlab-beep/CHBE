from paper.broker import DryRunBroker
from paper.config import PaperConfig
from paper.engine import PaperEngine
from paper.signal import entry_signal, exit_signal, zscore


def _candle(c, l=None, h=None):
    l = c - 0.1 if l is None else l
    h = c + 0.1 if h is None else h
    return dict(ts=0, o=c, h=h, l=l, c=c)


def test_zscore_and_signals():
    closes = [100.0] * 47 + [95.0]     # резкий пролив на последнем баре
    z = zscore(closes, 48)
    assert z is not None and z < -2
    assert entry_signal(closes, 48, -2.0)
    # выход по возврату к среднему
    assert exit_signal([100.0] * 48, 48, 0.0, 1, 8, 95.0, 99.9, 0.08) == "reversion"
    # стоп
    assert exit_signal([100.0] * 48, 48, 0.0, 1, 8, 100.0, 91.0, 0.08) == "stop"
    # тайм-стоп: close ниже среднего (нет reversion), low выше стопа (нет stop), held>=max_hold
    assert exit_signal([100.0] * 47 + [96.0], 48, 0.0, 8, 8, 100.0, 95.0, 0.08) == "time"


def test_engine_full_trade_cycle_dryrun():
    cfg = PaperConfig(symbols=["BTC/USDT"], sma_n=48, size_frac=0.05)
    eng = PaperEngine(cfg, DryRunBroker())
    # 47 плоских баров -> история
    for _ in range(47):
        eng.step("BTC/USDT", _candle(100.0))
    # бар-сигнал: пролив (z<-2). Лимитка на покупку @95.
    eng.step("BTC/USDT", _candle(95.0, l=94.9))
    st = eng.states["BTC/USDT"]
    assert st.pending is not None
    # следующий бар: low<=95 -> лимитка исполняется, позиция открыта
    eng.step("BTC/USDT", _candle(96.0, l=94.0))
    assert st.position is not None and st.pending is None
    # цена возвращается к среднему (~100) -> лимит-продажа на цели исполняется
    for _ in range(3):
        eng.step("BTC/USDT", _candle(100.0, h=101.0))
        if st.position is None:
            break
    assert st.position is None
    m = eng.summary()
    assert m["trades"] == 1
    assert eng.trades[0].reason in ("reversion", "time", "stop")


def test_engine_cancels_unfilled_limit():
    cfg = PaperConfig(symbols=["BTC/USDT"], fill_window=3)
    eng = PaperEngine(cfg, DryRunBroker())
    for _ in range(47):
        eng.step("BTC/USDT", _candle(100.0))
    eng.step("BTC/USDT", _candle(95.0, l=94.9))          # сигнал -> лимитка @95
    assert eng.states["BTC/USDT"].pending is not None
    # цена не возвращается к 95 (low всегда выше) -> лимитка не исполняется -> отмена
    for _ in range(5):
        eng.step("BTC/USDT", _candle(99.0, l=98.0))
    assert eng.states["BTC/USDT"].pending is None
    assert eng.states["BTC/USDT"].position is None
