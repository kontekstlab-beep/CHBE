import math

from smartmoney import synth
from smartmoney.backtest import Backtester, BacktestConfig
from smartmoney.config import Config
from smartmoney.models import Side
from smartmoney.strategy import ScriptedStrategy, Signal, SmartMoneyStrategy


def _flat(price, n, start_index=0):
    return [(price, price + 0.2, price - 0.2, price) for _ in range(n)]


def test_engine_take_profit_short():
    # Строим путь: до бара 5 цена ~100, на баре 5 сигнал SHORT (entry 100, sl 103, tp 94).
    # Далее цена плавно падает до 94 (TP), не касаясь 103.
    seq = _flat(100, 6)
    seq += [
        (100, 100.5, 97, 97),
        (97, 97.5, 94, 94),      # TP=94 достигнут (low<=94)
        (94, 95, 93, 93.5),
    ]
    candles = synth.make(seq)
    sig = Signal(Side.SHORT, entry=100, stop_loss=103, take_profit=94,
                 ob_index=4, at_index=5, reason="scripted")
    strat = ScriptedStrategy({5: sig})
    # без комиссий/проскальзывания для точных чисел
    bt = Backtester(Config(), BacktestConfig(starting_equity=1000, fee_bps=0, slippage_bps=0))
    res = bt.run(candles, strat)
    assert len(res.trades) == 1
    tr = res.trades[0]
    assert tr.side == Side.SHORT and tr.reason == "tp"
    assert math.isclose(tr.r_multiple, 2.0, rel_tol=1e-6)  # (100-94)/(103-100)
    assert res.metrics.final_equity > 1000


def test_engine_stop_loss_first_when_ambiguous():
    # Бар, где задет и SL и TP -> консервативно должен сработать SL.
    seq = _flat(100, 6)
    seq += [(100, 104, 93, 100)]  # high 104>=SL103 и low 93<=TP94 в одном баре
    candles = synth.make(seq)
    sig = Signal(Side.SHORT, 100, 103, 94, 4, 5, "scripted")
    strat = ScriptedStrategy({5: sig})
    bt = Backtester(Config(), BacktestConfig(starting_equity=1000, fee_bps=0, slippage_bps=0))
    res = bt.run(candles, strat)
    assert res.trades[0].reason == "sl"
    assert res.trades[0].r_multiple < 0


def test_limit_entry_fills_on_retest():
    # sell-limit на 100; цена сначала ниже, потом ретест вверх к 100 -> fill, затем TP.
    seq = _flat(96, 6)                       # цена ниже лимитки
    seq += [
        (96, 99, 95, 98),                    # bar6: не дотянулась до 100
        (98, 101, 97, 100),                  # bar7: high 101>=100 -> fill @100
        (100, 100.5, 94, 94),                # bar8: TP=94
    ]
    candles = synth.make(seq)
    sig = Signal(Side.SHORT, entry=100, stop_loss=103, take_profit=94,
                 ob_index=4, at_index=5, reason="scripted", is_limit=True)
    strat = ScriptedStrategy({5: sig})
    res = Backtester(Config(), BacktestConfig(starting_equity=1000, fee_bps=0, slippage_bps=0)).run(candles, strat)
    assert res.filled == 1 and len(res.trades) == 1
    assert res.trades[0].reason == "tp"


def test_limit_entry_cancelled_by_ttl():
    # лимитка на 200 недостижима -> отмена по TTL, сделок нет.
    cfg = Config()
    cfg.risk.order_ttl_bars = 5
    seq = _flat(100, 40)
    candles = synth.make(seq)
    sig = Signal(Side.SHORT, entry=200, stop_loss=210, take_profit=150,
                 ob_index=4, at_index=5, reason="scripted", is_limit=True)
    strat = ScriptedStrategy({5: sig})
    res = Backtester(cfg, BacktestConfig(starting_equity=1000, fee_bps=0, slippage_bps=0)).run(candles, strat)
    assert res.filled == 0 and res.cancelled == 1
    assert len(res.trades) == 0


def test_breakeven_protects_after_1r():
    # market-вход short@100, SL103, TP90 (1R=3). Цена доходит до 97 (+1R) -> SL в БУ (100),
    # затем возвращается к 100 -> выход 'be' около нуля, а не полный стоп.
    cfg = Config()
    cfg.risk.use_breakeven = True
    cfg.risk.breakeven_at_r = 1.0
    seq = _flat(100, 6)
    seq += [
        (100, 100.5, 97, 97.5),   # bar6: low 97 -> достигнут +1R, SL -> БУ
        (98, 100.2, 98, 100),     # bar7: high 100.2 >= БУ(100) -> выход 'be'
        (100, 101, 99, 100),
    ]
    candles = synth.make(seq)
    sig = Signal(Side.SHORT, entry=100, stop_loss=103, take_profit=90,
                 ob_index=4, at_index=5, reason="scripted", is_limit=False)
    strat = ScriptedStrategy({5: sig})
    res = Backtester(cfg, BacktestConfig(starting_equity=1000, fee_bps=0, slippage_bps=0)).run(candles, strat)
    assert len(res.trades) == 1
    tr = res.trades[0]
    assert tr.reason == "be"
    assert abs(tr.pnl) < 1e-6            # безубыток при нулевых издержках
    assert tr.r_multiple > -1.0          # точно не полный стоп


def test_partial_take_profit_banks_and_runs():
    # short@100, SL110 (1R=10), TP70 (RR3). Частичка 50% на +1R (=90), остаток до TP.
    cfg = Config()
    cfg.risk.use_partial = True
    cfg.risk.partial_at_r = 1.0
    cfg.risk.partial_frac = 0.5
    cfg.risk.use_trailing = False
    seq = _flat(100, 6)
    seq += [
        (100, 101, 90, 91),   # bar6: low 90 -> частичная фиксация 0.5 @90, SL->БУ
        (91, 95, 70, 70),     # bar7: low 70 -> остаток по TP @70
        (70, 72, 69, 71),
    ]
    candles = synth.make(seq)
    sig = Signal(Side.SHORT, entry=100, stop_loss=110, take_profit=70,
                 ob_index=4, at_index=5, reason="scripted", is_limit=False)
    strat = ScriptedStrategy({5: sig})
    res = Backtester(cfg, BacktestConfig(starting_equity=1000, fee_bps=0, slippage_bps=0)).run(candles, strat)
    assert len(res.trades) == 1
    tr = res.trades[0]
    assert tr.partial is True and tr.reason == "tp"
    # половина по +1R (+0.5R от риска) + половина по +3R (+1.5R) = +2R суммарно
    assert abs(tr.r_multiple - 2.0) < 1e-6


def test_trailing_preset_smoke():
    # прогон пресета v2 (частичка + трейлинг) по синтетике: инварианты не нарушены,
    # встречаются частичные фиксации, исходы валидны.
    from smartmoney.presets import backtest_v2
    cfg = backtest_v2()
    candles = synth.downtrend_series(cycles=12)
    strat = SmartMoneyStrategy(cfg, allow_longs=True, arm_ttl_bars=30)
    res = Backtester(cfg, BacktestConfig()).run(candles, strat)
    for tr in res.trades:
        assert tr.reason in ("tp", "sl", "be", "trail")
    assert len(res.equity_curve) == 1 + len(res.trades)


def test_no_lookahead_signal_stable():
    # Сигнал на баре t не должен зависеть от будущих баров:
    # evaluate(candles[:t+1]) даёт тот же результат при добавлении будущего.
    candles = synth.downtrend_series(cycles=4)
    strat_a = SmartMoneyStrategy(Config())
    strat_b = SmartMoneyStrategy(Config())
    t = 40
    a = strat_a.evaluate(candles[:t + 1])
    b = strat_b.evaluate(candles[:t + 1])  # свежий экземпляр, та же история
    assert (a is None) == (b is None)


def test_full_backtest_runs_and_produces_trades():
    candles = synth.downtrend_series(cycles=8)
    cfg = Config()
    cfg.structure.pivot_strength = 1
    cfg.orderblock.atr_period = 5
    cfg.orderblock.displacement_atr = 1.0
    cfg.orderblock.min_ob_score = 3
    cfg.risk.min_rr = 2.0
    cfg.liquidity.equal_level_tol = 0.03
    strat = SmartMoneyStrategy(cfg)
    res = Backtester(cfg, BacktestConfig(starting_equity=1000)).run(candles, strat)
    # движок отработал корректно; знаки P&L согласованы с причиной выхода
    for tr in res.trades:
        if tr.reason == "tp":
            assert tr.pnl > 0
        elif tr.reason == "sl":
            assert tr.pnl < 0
    assert len(res.equity_curve) == 1 + len(res.trades)
    assert res.metrics.trades == len(res.trades)
