"""Тесты C6 (M6): лесенка (вторая порция при z<ladder_z) + BTC-гейт входа.

Сценарии: полный цикл лесенки с ручным расчётом P&L; запрет повторной лесенки;
отмена по TTL; отмена при раннем выходе; BTC-гейт (блок/пропуск/нет данных);
state round-trip и загрузка старого формата; reconcile призрачной лесенки.
"""
import json

import pytest

from paper import state as state_mod
from paper.broker import DryRunBroker
from paper.config import PaperConfig
from paper.engine import PaperEngine, Pending, Position, SymbolState, reconcile
from paper.signal import btc_gate


def _candle(c, l=None, h=None):
    l = c - 0.1 if l is None else l
    h = c + 0.1 if h is None else h
    return dict(ts=0, o=c, h=h, l=l, c=c)


def _engine_no_filter(**kw):
    cfg = PaperConfig(symbols=["X/USDT"], use_btc_filter=False, **kw)
    return PaperEngine(cfg, DryRunBroker())


def _open_position(eng):
    """47 плоских баров + пролив -> лимитка; следующий бар -> филл. Позиция @95."""
    for _ in range(47):
        eng.step("X/USDT", _candle(100.0))
    eng.step("X/USDT", _candle(95.0, l=94.9))      # сигнал -> лимитка @95
    eng.step("X/USDT", _candle(96.0, l=94.0))      # филл @95
    st = eng.states["X/USDT"]
    assert st.position is not None
    return st


# --- чистая функция гейта ---

def test_btc_gate_pure():
    assert btc_gate([100.0] * 10, 48, -1.0) is True        # мало данных -> пропуск
    assert btc_gate([100.0] * 48, 48, -1.0) is False       # z=0 -> блок
    assert btc_gate([100.0] * 47 + [95.0], 48, -1.0) is True   # пролив -> пропуск


# --- лесенка: полный цикл ---

def test_ladder_full_cycle_and_pnl():
    eng = _engine_no_filter(sma_n=48)
    st = _open_position(eng)
    p = st.position
    q1 = 1000.0 * 0.05 / 95.0
    assert p.qty == pytest.approx(q1)
    # лесенка ставится на том же баре, что и филл входа (z<-3), по close бара
    assert st.pending_ladder is not None
    ladder_px = st.pending_ladder.price
    assert ladder_px == pytest.approx(96.0)
    # филл лесенки -> усреднение, sell перевыставлен на полный qty
    eng.step("X/USDT", _candle(97.0, l=95.5))
    p = st.position
    q2 = 1000.0 * 0.05 / ladder_px
    exp_qty = q1 + q2
    exp_entry = (95.0 * q1 + ladder_px * q2) / exp_qty
    assert p.ladder_used is True
    assert st.pending_ladder is None
    assert p.qty == pytest.approx(exp_qty)
    assert p.entry == pytest.approx(exp_entry)
    sells = [o for o in eng.broker._orders.values() if o["side"] == "sell"]
    assert len(sells) == 1 and sells[0]["qty"] == pytest.approx(exp_qty)
    # выход по реверсии на актуальной цели движка
    target = p.target
    eng.step("X/USDT", _candle(100.0, l=99.0, h=target + 0.5))
    assert st.position is None
    assert len(eng.trades) == 1
    t = eng.trades[0]
    assert t.reason == "reversion"
    mk = eng.cfg.maker_fee
    exp_pnl = exp_qty * (target - exp_entry) - exp_qty * (exp_entry * mk + target * mk)
    assert t.pnl == pytest.approx(exp_pnl)
    assert t.qty == pytest.approx(exp_qty)


def test_ladder_not_placed_twice():
    eng = _engine_no_filter(sma_n=48)
    st = _open_position(eng)
    eng.step("X/USDT", _candle(97.0, l=95.5))    # лесенка исполнена
    assert st.position.ladder_used is True
    buys_before = len([o for o in eng.broker._orders.values() if o["side"] == "buy"])
    # ещё один бар с z<-3: вторая лесенка НЕ ставится
    eng.step("X/USDT", _candle(90.0, l=89.0))
    assert st.position is not None               # стоп 8% от 95.497=87.86 не задет
    assert st.pending_ladder is None
    buys_after = len([o for o in eng.broker._orders.values() if o["side"] == "buy"])
    assert buys_after == buys_before


def test_ladder_ttl_cancel():
    eng = _engine_no_filter(sma_n=48, fill_window=3)
    st = _open_position(eng)                     # позиция + лесенка @96 (bar=49)
    assert st.pending_ladder is not None
    placed = st.pending_ladder.placed_bar
    # цена выше 96: филла нет; z между -3 и 0 -> перевыставления тоже нет
    for _ in range(4):
        eng.step("X/USDT", _candle(97.5, l=96.5))
    assert st.bar - placed > 3
    assert st.pending_ladder is None
    assert st.position is not None               # позиция жива
    assert not [o for o in eng.broker._orders.values() if o["side"] == "buy"]


def test_ladder_cancelled_on_early_exit():
    eng = _engine_no_filter(sma_n=48)
    st = _open_position(eng)                     # позиция + лесенка @96
    assert st.pending_ladder is not None
    # резкий отскок: лесенка (96) не задета, лимит-продажа на SMA исполняется
    eng.step("X/USDT", _candle(100.5, l=97.0, h=100.6))
    assert st.position is None                   # выход по реверсии
    assert st.pending_ladder is None             # лесенка отменена
    assert not [o for o in eng.broker._orders.values() if o["side"] == "buy"]


# --- BTC-гейт ---

def _engine_with_btc(btc_closes):
    cfg = PaperConfig(symbols=["BTC/USDT", "ALT/USDT"], use_btc_filter=True)
    eng = PaperEngine(cfg, DryRunBroker())
    bst = eng._st("BTC/USDT")
    bst.closes.extend(btc_closes)
    bst.bar = len(btc_closes)
    for _ in range(47):
        eng.step("ALT/USDT", _candle(100.0))
    return eng


def test_btc_gate_blocks_entry():
    eng = _engine_with_btc([100.0] * 48)          # z(BTC)=0 >= -1 -> блок
    eng.step("ALT/USDT", _candle(95.0, l=94.9))   # сигнал по ALT
    assert eng.states["ALT/USDT"].pending is None


def test_btc_gate_passes_on_btc_dip():
    eng = _engine_with_btc([100.0] * 47 + [95.0])  # z(BTC)<<-1 -> пропуск
    eng.step("ALT/USDT", _candle(95.0, l=94.9))
    assert eng.states["ALT/USDT"].pending is not None


def test_btc_gate_passes_without_btc_data():
    cfg = PaperConfig(symbols=["ALT/USDT"], use_btc_filter=True)  # BTC нет в корзине
    eng = PaperEngine(cfg, DryRunBroker())
    for _ in range(47):
        eng.step("ALT/USDT", _candle(100.0))
    eng.step("ALT/USDT", _candle(95.0, l=94.9))
    assert eng.states["ALT/USDT"].pending is not None   # деградация в baseline


def test_btc_gate_applies_to_ladder():
    eng = _engine_with_btc([100.0] * 48)          # BTC z=0 -> гейт закрыт
    st = eng.states["ALT/USDT"]
    st.position = Position(entry=95.0, qty=0.5, entry_bar=st.bar, target=99.0)
    eng.step("ALT/USDT", _candle(90.0, l=89.9))   # z(ALT)<<-3
    assert st.pending_ladder is None              # лесенка заблокирована гейтом
    # BTC упал -> гейт открыт -> лесенка ставится
    eng.states["BTC/USDT"].closes = [100.0] * 47 + [95.0]
    eng.step("ALT/USDT", _candle(89.0, l=88.9))
    assert st.pending_ladder is not None


# --- state round-trip ---

def test_state_roundtrip_with_ladder(tmp_path):
    eng = _engine_no_filter()
    st = eng._st("X/USDT")
    st.closes.extend([100.0] * 48)
    st.lows.extend([99.0] * 48)
    st.bar = 48
    st.position = Position(entry=95.0, qty=1.0, entry_bar=40, sell_oid=7,
                           target=99.5, ladder_used=True)
    st.pending_ladder = Pending(oid=8, price=94.0, placed_bar=47)
    path = str(tmp_path / "state.json")
    state_mod.save(eng, path)

    eng2 = _engine_no_filter()
    state_mod.load(eng2, path)
    st2 = eng2.states["X/USDT"]
    assert st2.position.ladder_used is True
    assert st2.position.entry == 95.0 and st2.position.qty == 1.0
    assert st2.pending_ladder is not None
    assert st2.pending_ladder.oid == 8 and st2.pending_ladder.price == 94.0


def test_state_loads_old_format(tmp_path):
    """Стейт старого формата (без ladder_used/pending_ladder) грузится с дефолтами."""
    old = {
        "equity": 1000.0,
        "trades": [],
        "states": {
            "X/USDT": {
                "closes": [100.0] * 48, "lows": [99.0] * 48, "bar": 48,
                "position": {"entry": 95.0, "qty": 1.0, "entry_bar": 40,
                             "sell_oid": 7, "target": 99.5},
                "pending": None,
            }
        },
    }
    path = tmp_path / "old.json"
    path.write_text(json.dumps(old), encoding="utf-8")
    eng = _engine_no_filter()
    state_mod.load(eng, str(path))
    st = eng.states["X/USDT"]
    assert st.position is not None and st.position.ladder_used is False
    assert st.pending_ladder is None


# --- reconcile ---

class StubBroker(DryRunBroker):
    """«Биржа» с заданными открытыми ордерами и балансом base-актива."""

    def __init__(self, oids, held):
        super().__init__()
        self._oids, self._held = oids, held

    def open_order_ids_on_exchange(self, symbol):
        return self._oids

    def held_qty(self, symbol):
        return self._held


def test_reconcile_drops_ghost_ladder():
    eng = _engine_no_filter()
    st = eng._st("X/USDT")
    st.position = Position(entry=95.0, qty=0.5, entry_bar=1, sell_oid="222", target=99.0)
    st.pending_ladder = Pending(oid="333", price=94.0, placed_bar=1)
    broker = StubBroker(oids={"222"}, held=1.0)   # лесенки 333 на бирже нет
    reconcile(eng, broker)
    assert st.pending_ladder is None              # призрачная лесенка снята
    assert st.position is not None and st.position.sell_oid == "222"


def test_reconcile_keeps_live_ladder():
    eng = _engine_no_filter()
    st = eng._st("X/USDT")
    st.position = Position(entry=95.0, qty=0.5, entry_bar=1, sell_oid="222", target=99.0)
    st.pending_ladder = Pending(oid="333", price=94.0, placed_bar=1)
    broker = StubBroker(oids={"222", "333"}, held=1.0)
    reconcile(eng, broker)
    assert st.pending_ladder is not None
