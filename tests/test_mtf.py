from smartmoney import synth
from smartmoney.backtest import Backtester, BacktestConfig
from smartmoney.mtf import MultiTFStrategy
from smartmoney.models import Candle
from smartmoney.presets import mtf_1d_v1, mtf_v1


def _resample(ltf, factor):
    """Строит HTF-свечи из LTF агрегацией по `factor` баров (для тестов)."""
    htf = []
    for i in range(0, len(ltf) - factor + 1, factor):
        grp = ltf[i:i + factor]
        htf.append(Candle(len(htf), grp[0].ts,
                          grp[0].open, max(x.high for x in grp),
                          min(x.low for x in grp), grp[-1].close,
                          sum(x.volume for x in grp)))
    return htf


def test_mtf_runs_without_lookahead_smoke():
    # LTF с шагом 1h, HTF агрегируем x4. Прогон не падает, исходы валидны.
    ltf = synth.downtrend_series(cycles=16)
    ltf = [Candle(i, i * 3_600_000, c.open, c.high, c.low, c.close, c.volume)
           for i, c in enumerate(ltf)]
    htf = _resample(ltf, 4)
    strat = MultiTFStrategy(htf, htf_ms=4 * 3_600_000, ltf_ms=3_600_000,
                            cfg=mtf_v1(), allow_longs=True, arm_ttl_bars=30)
    res = Backtester(mtf_v1(), BacktestConfig()).run(ltf, strat)
    for tr in res.trades:
        assert tr.reason in ("tp", "sl", "be", "trail")
    assert len(res.equity_curve) == 1 + len(res.trades)


def test_mtf_1d_preset_runs():
    # связка 1D->1h (агрегируем x24) на пресете mtf_1d_v1: прогон без падений.
    ltf = synth.downtrend_series(cycles=40)
    ltf = [Candle(i, i * 3_600_000, c.open, c.high, c.low, c.close, c.volume)
           for i, c in enumerate(ltf)]
    htf = _resample(ltf, 24)
    strat = MultiTFStrategy(htf, htf_ms=24 * 3_600_000, ltf_ms=3_600_000,
                            cfg=mtf_1d_v1(), allow_longs=True, arm_ttl_bars=30)
    res = Backtester(mtf_1d_v1(), BacktestConfig()).run(ltf, strat)
    for tr in res.trades:
        assert tr.reason in ("tp", "sl", "be", "trail")
    assert len(res.equity_curve) == 1 + len(res.trades)


def test_mtf_htf_known_no_lookahead():
    # _htf_known(t) не должен включать HTF-бары, закрывшиеся позже открытия LTF-бара t.
    ltf = synth.downtrend_series(cycles=4)
    ltf = [Candle(i, i * 3_600_000, c.open, c.high, c.low, c.close, c.volume)
           for i, c in enumerate(ltf)]
    htf = _resample(ltf, 4)
    strat = MultiTFStrategy(htf, 4 * 3_600_000, 3_600_000, mtf_v1())
    strat.prepare(ltf)
    for t in range(len(ltf)):
        k = strat._htf_known(t)
        # все «известные» HTF-бары закрылись не позже открытия LTF-бара t
        for i in range(k):
            assert htf[i].ts + strat.htf_ms <= ltf[t].ts
