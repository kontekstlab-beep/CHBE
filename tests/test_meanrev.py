from meanrev import backtest_coin, stats


def test_backtest_enters_dip_and_profits():
    # 48 баров ~100 (узкий диапазон), резкий пролив до 95, затем восстановление.
    closes = [100.0 + (i % 2) * 0.01 for i in range(48)] + [95.0, 96.0, 98.0, 100.0, 100.0]
    trades = backtest_coin(closes, n=48, entry_z=-2.0, exit_z=0.0, max_hold=8)
    assert len(trades) >= 1          # пролив должен дать вход
    assert max(trades) > 0           # отскок -> положительная сделка


def test_no_trades_on_flat():
    closes = [100.0] * 200
    trades = backtest_coin(closes, n=48, entry_z=-2.0, exit_z=0.0, max_hold=8)
    # на идеально плоском ряду z не уходит ниже -2 (sd=0 обрабатывается, но отклонения нет)
    assert trades == [] or all(abs(t) < 1e-6 for t in trades)


def test_stats_basic():
    n, wr, m, pf = stats([0.01, -0.005, 0.02])
    assert n == 3 and 0 <= wr <= 100 and m != 0


def test_maker_fill_and_skip():
    from meanrev_maker import backtest
    closes = [100.0 + (i % 2) * 0.01 for i in range(48)] + [95.0, 96.0, 98.0, 100.0, 100.0]
    lows = [c - 0.5 for c in closes]
    lows[49] = 94.0  # следующий бар после сигнала касается лимитки (95) -> fill
    tr, sig, fil = backtest(closes, lows, entry_mode="maker", offset=0.0,
                            fill_window=3, fee_in=0.0002, fee_out=0.0002)
    assert sig >= 1 and fil >= 1 and len(tr) >= 1

    # если цена НЕ опускается до лимитки в окне -> сигнал есть, филла нет
    lows2 = [c + 5.0 for c in closes]  # low всегда выше близко к close+5
    tr2, sig2, fil2 = backtest(closes, lows2, entry_mode="maker", offset=0.01,
                               fill_window=2, fee_in=0.0002, fee_out=0.0002)
    assert sig2 >= 1 and fil2 == 0 and tr2 == []


def test_stop_caps_tail_loss():
    from tail_risk import backtest as bt_stop
    # пролив-сигнал, затем обвал: стоп 8% должен ограничить убыток, без стопа — хуже.
    closes = [100.0] * 48 + [95.0, 90.0, 85.0, 80.0, 78.0, 77.0, 76.0, 75.0, 74.0]
    lows = [c - 0.2 for c in closes]
    lows[49] = 94.0  # касание лимитки (95) -> вход
    with_stop = bt_stop(closes, lows, stop_frac=0.08)
    no_stop = bt_stop(closes, lows, stop_frac=0.0)
    assert with_stop and no_stop
    assert min(with_stop) >= -0.09          # стоп ~8% + издержки
    assert min(with_stop) > min(no_stop)     # без стопа убыток глубже
