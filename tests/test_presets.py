from smartmoney import synth
from smartmoney.backtest import Backtester, BacktestConfig
from smartmoney.presets import backtest_v1
from smartmoney.strategy import SmartMoneyStrategy


def test_preset_runs_and_uses_rr_target():
    cfg = backtest_v1()
    assert cfg.entry.target_mode == "rr" and cfg.entry.target_rr == 1.0
    assert cfg.entry.entry_edge == "distal" and cfg.entry.sl_mode == "atr"
    # прогон по синтетике не падает и даёт согласованные исходы
    candles = synth.downtrend_series(cycles=12)
    strat = SmartMoneyStrategy(cfg, allow_longs=True, arm_ttl_bars=30)
    res = Backtester(cfg, BacktestConfig()).run(candles, strat)
    for tr in res.trades:
        assert tr.reason in ("tp", "sl", "be")
    assert len(res.equity_curve) == 1 + len(res.trades)
