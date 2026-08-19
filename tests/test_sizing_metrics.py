import math

from smartmoney.config import RiskConfig
from smartmoney.metrics import compute_metrics, max_drawdown
from smartmoney.models import Side
from smartmoney.sizing import position_size, risk_reward, valid_bracket


def test_position_size_risks_one_percent():
    cfg = RiskConfig(risk_pct=0.01, max_margin_per_trade=0.20, max_leverage=20)
    sz = position_size(equity=1000, entry=100, stop_loss=103, cfg=cfg)
    # риск = 1% * 1000 = 10; stop_distance = 3 -> qty = 3.333
    assert math.isclose(sz.risk_amount, 10.0)
    assert math.isclose(sz.qty, 10.0 / 3.0, rel_tol=1e-9)
    # убыток по SL == risk_amount
    loss = sz.qty * abs(100 - 103)
    assert math.isclose(loss, 10.0, rel_tol=1e-9)


def test_leverage_within_bounds():
    cfg = RiskConfig(risk_pct=0.01, max_margin_per_trade=0.20, max_leverage=20)
    sz = position_size(1000, 100, 99.5, cfg)  # маленький стоп -> большой номинал
    assert 1 <= sz.leverage <= 20
    assert sz.margin <= 0.20 * 1000 + 1e-6 or sz.leverage == 20


def test_risk_reward_and_bracket():
    assert math.isclose(risk_reward(Side.SHORT, 100, 103, 94), 2.0)
    assert valid_bracket(Side.SHORT, 100, 103, 94)
    assert not valid_bracket(Side.SHORT, 100, 99, 94)  # SL должен быть выше входа


def test_max_drawdown():
    assert math.isclose(max_drawdown([100, 120, 90, 110]), (120 - 90) / 120)


def test_compute_metrics_basic():
    # 2 сделки: +2R (+20) и -1R (-10)
    m = compute_metrics([2.0, -1.0], [20.0, -10.0], [1000, 1020, 1010], 1000)
    assert m.trades == 2 and m.wins == 1 and m.losses == 1
    assert math.isclose(m.winrate, 0.5)
    assert math.isclose(m.avg_r, 0.5)
    assert math.isclose(m.profit_factor, 2.0)
    assert math.isclose(m.final_equity, 1010)
