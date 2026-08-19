import os

import pytest

from portfolio import simulate

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
pytestmark = pytest.mark.skipif(
    not os.path.exists(os.path.join(_DATA, "SOLUSDT_1h_4000.csv")),
    reason="кэш data/ отсутствует (регенерируется smartmoney.data.get_cached)")


def test_portfolio_sim_runs():
    # smoke: симулятор возвращает корректную структуру на реальных (уже использованных) данных
    M = simulate(["SOL/USDT", "LINK/USDT"], max_concurrent=999, kill_thresh=None)
    for key in ("pnl", "mdd", "trades", "kills", "rtd"):
        assert key in M
    assert M["mdd"] >= 0
    assert M["trades"] >= 0


def test_concurrency_limit_reduces_trades():
    full = simulate(["SOL/USDT", "LINK/USDT", "NEAR/USDT"], 999, None)
    capped = simulate(["SOL/USDT", "LINK/USDT", "NEAR/USDT"], 1, None)
    assert capped["trades"] <= full["trades"]
