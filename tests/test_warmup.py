"""Прогрев live-движка из истории: без него первые sma_n баров сигналов нет."""
from paper.broker import DryRunBroker
from paper.config import PaperConfig
from paper.engine import PaperEngine
from run_paper import seed_from_history


def _hist(n, close=100.0, low=99.0):
    return [[i, close, close, low, close, 0.0] for i in range(n)]


def test_seed_enables_signal_from_first_bar():
    cfg = PaperConfig()
    eng = PaperEngine(cfg, DryRunBroker())
    seeded = seed_from_history(eng, "BTC/USDT", _hist(52), cfg.sma_n + 5)
    assert seeded == 52
    st = eng.states["BTC/USDT"]
    assert st.bar == 52 and len(st.closes) == 52

    # просадка на последнем баре -> z << -2 -> вход должен сработать СРАЗУ
    eng.step("BTC/USDT", dict(ts=99, o=91, h=91.5, l=89.5, c=90.0))
    assert st.pending is not None


def test_seed_is_noop_when_state_has_bars():
    cfg = PaperConfig()
    eng = PaperEngine(cfg, DryRunBroker())
    eng.step("BTC/USDT", dict(ts=1, o=100, h=101, l=99, c=100))
    before = list(eng.states["BTC/USDT"].closes)
    assert seed_from_history(eng, "BTC/USDT", _hist(52), cfg.sma_n + 5) == 0
    assert eng.states["BTC/USDT"].closes == before  # стейт не тронут


def test_seed_trims_to_keep():
    cfg = PaperConfig()
    eng = PaperEngine(cfg, DryRunBroker())
    seeded = seed_from_history(eng, "BTC/USDT", _hist(500), cfg.sma_n + 5)
    assert seeded == cfg.sma_n + 5
    assert len(eng.states["BTC/USDT"].closes) == cfg.sma_n + 5
