"""Генерация сигналов.

`SmartMoneyStrategy` — упрощённый одно-таймфреймовый автомат (для прототипа):
контекст (тренд + сильный OB как зона интереса) и вход на одной серии, но с
ТРЕМЯ масштабами свингов, имитирующими мультиТФ-связку §5 ТЗ:
    trend_pivot_strength   — крупные свинги -> тренд (HTF-контекст);
    pivot_strength         — средние свинги -> зона/OB;
    confirm_pivot_strength — мелкие свинги -> слом структуры (LTF-вход).

Автомат:
    ARM     — цена коснулась зоны сильного OB по тренду;
    CONFIRM — после этого произошёл слом структуры (BOS) в сторону сделки;
    SIGNAL  — вход: SL за блок, TP в противоположный пул ликвидности, RR>=min.

Производительность: примитивы считаются ОДИН раз в `prepare()`, а `evaluate_at(t)`
работает «as-of» (фильтрует всё по confirmed_at<=t) — это сохраняет запрет
look-ahead и даёт линейную сложность на бэктест.

`ScriptedStrategy` — детерминированный источник сигналов для тестов движка.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import List, Optional, Protocol

from .config import Config
from .liquidity import find_pools, mark_swept
from .models import Candle, PoolType, Side, Trend
from .orderblocks import find_order_blocks, update_mitigation
from .sizing import risk_reward, valid_bracket
from .structure import atr, classify_trend, detect_bos, find_swings


@dataclass
class Signal:
    side: Side
    entry: float          # цена входа (лимитка, если is_limit); иначе рыночный ориентир
    stop_loss: float
    take_profit: float
    ob_index: int
    at_index: int
    reason: str
    is_limit: bool = True


class Strategy(Protocol):
    def prepare(self, candles: List[Candle]) -> None: ...
    def evaluate_at(self, t: int) -> Optional[Signal]: ...


def build_bracket(cfg, candles, side: Side, bos, cur, a, pools):
    """Расчёт входа/стопа/цели из LTF-блока, вызвавшего слом (параметризуемо EntryConfig).

    Возвращает (entry, sl, tp, is_limit) или None. Общая логика для одно-ТФ и мультиТФ
    стратегий: `candles` — серия входа (LTF), `bos.ob_candle_index` — её индекс.
    """
    rc = cfg.risk
    ec = cfg.entry
    ob_cndl = candles[bos.ob_candle_index]
    lo, hi = ob_cndl.low, ob_cndl.high

    # 1) цена входа
    if rc.use_limit_entry:
        is_limit = True
        if side == Side.SHORT:
            edge = {"proximal": lo, "mid": (lo + hi) / 2, "distal": hi}
        else:
            edge = {"proximal": hi, "mid": (lo + hi) / 2, "distal": lo}
        entry = edge.get(ec.entry_edge, edge["proximal"])
    else:
        is_limit = False
        entry = cur.close

    # 2) стоп-лосс
    if ec.sl_mode == "atr":
        sl = entry + rc.sl_buffer_atr * a + ec.sl_atr_mult * a * (1 if side == Side.SHORT else -1)
    else:  # block
        sl = hi + rc.sl_buffer_atr * a if side == Side.SHORT else lo - rc.sl_buffer_atr * a

    # 3) цель
    if side == Side.SHORT:
        candidates = [p.price for p in pools if p.type == PoolType.SSL and p.price < entry]
    else:
        candidates = [p.price for p in pools if p.type == PoolType.BSL and p.price > entry]

    if ec.target_mode == "rr":
        risk = abs(entry - sl)
        tp = entry - ec.target_rr * risk if side == Side.SHORT else entry + ec.target_rr * risk
        rr_ok = ec.target_rr > 0
    else:
        if not candidates:
            return None
        if side == Side.SHORT:
            nearest, farthest = max(candidates), min(candidates)
        else:
            nearest, farthest = min(candidates), max(candidates)
        tp = nearest if ec.target_mode == "pool_nearest" else farthest
        if risk_reward(side, entry, sl, tp) < rc.min_rr:
            tp = farthest if ec.target_mode == "pool_nearest" else nearest
        rr_ok = risk_reward(side, entry, sl, tp) >= rc.min_rr

    if not rr_ok or not valid_bracket(side, entry, sl, tp):
        return None
    return entry, sl, tp, is_limit


class ScriptedStrategy:
    """Выдаёт заранее заданные сигналы на указанных барах (для тестов движка)."""

    def __init__(self, signals_by_index: dict):
        self._by_index = signals_by_index

    def prepare(self, candles: List[Candle]) -> None:
        pass

    def evaluate_at(self, t: int) -> Optional[Signal]:
        return self._by_index.get(t)


class SmartMoneyStrategy:
    def __init__(self, cfg: Config, allow_longs: bool = False,
                 arm_ttl_bars: int = 20):
        self.cfg = cfg
        self.allow_longs = allow_longs
        self.arm_ttl_bars = arm_ttl_bars
        self._armed_short: Optional[tuple] = None
        self._armed_long: Optional[tuple] = None
        self._candles: List[Candle] = []
        self._swings = self._tsw = self._csw = None
        self._atr = None
        self._blocks = None

    # ---- разовый precompute примитивов на всей серии ----
    def prepare(self, candles: List[Candle]) -> None:
        cfg = self.cfg
        self._candles = candles
        self._swings = find_swings(candles, cfg.structure.pivot_strength)
        self._tsw = find_swings(candles, cfg.structure.trend_pivot_strength)
        self._csw = find_swings(candles, cfg.structure.confirm_pivot_strength)
        # confirmed_at отсортированы по возрастанию -> bisect для as-of срезов
        self._swings_conf = [s.confirmed_at for s in self._swings]
        self._tsw_conf = [s.confirmed_at for s in self._tsw]
        self._csw_conf = [s.confirmed_at for s in self._csw]
        self._atr = atr(candles, cfg.orderblock.atr_period)
        blocks = find_order_blocks(candles, self._swings, cfg.orderblock)
        update_mitigation(blocks, candles)  # invalidated_at/mitigated_at по всей серии
        self._blocks = blocks
        self._armed_short = None
        self._armed_long = None

    # ---- back-compat: пересчёт + оценка на последнем баре (используется в тестах) ----
    def evaluate(self, candles: List[Candle]) -> Optional[Signal]:
        self.prepare(candles)
        return self.evaluate_at(len(candles) - 1)

    def _asof_strong(self, side: Side, t: int):
        """Сильные, подтверждённые к бару t и НЕ инвалидированные к t блоки."""
        out = []
        for b in self._blocks:
            if b.side != side:
                continue
            if b.score < self.cfg.orderblock.min_ob_score:
                continue
            if b.confirmed_at > t:
                continue
            if b.invalidated_at is not None and b.invalidated_at <= t:
                continue
            out.append(b)
        return out

    def evaluate_at(self, t: int) -> Optional[Signal]:
        cfg = self.cfg
        c = self._candles
        warmup = cfg.orderblock.atr_period + 2 * cfg.structure.pivot_strength + 2
        if t < warmup:
            return None

        a = self._atr[t]
        cur = c[t]
        # as-of срезы свингов через bisect (confirmed_at <= t)
        kt = bisect.bisect_right(self._tsw_conf, t)
        tsw_asof = self._tsw[:kt]
        kc = bisect.bisect_right(self._csw_conf, t)
        csw_asof = self._csw[:kc]
        ks = bisect.bisect_right(self._swings_conf, t)
        sw_asof = self._swings[max(0, ks - cfg.liquidity.lookback_swings):ks]

        trend = classify_trend(tsw_asof, t, cfg.structure)
        # пулы ликвидности «as-of»: снятие проверяем только по барам <= t
        pools = mark_swept(find_pools(sw_asof, cfg.liquidity), c, upto=t)

        # ---- SHORT ----
        if trend == Trend.DOWN:
            sig = self._short_flow(csw_asof, pools, cur, t, a)
            if sig:
                return sig
        else:
            self._armed_short = None

        # ---- LONG (опционально) ----
        if self.allow_longs and trend == Trend.UP:
            sig = self._long_flow(csw_asof, pools, cur, t, a)
            if sig:
                return sig
        elif trend != Trend.UP:
            self._armed_long = None

        return None

    # ---- шорт-ветка автомата ----
    def _short_flow(self, csw_asof, pools, cur, t, a) -> Optional[Signal]:
        if self._armed_short is None:
            for ob in sorted(self._asof_strong(Side.SHORT, t), key=lambda b: -b.index):
                tapped = cur.high >= ob.low and cur.low <= ob.high
                if tapped and ob.confirmed_at < t:
                    self._armed_short = (ob, t)
                    break
            return None

        ob, arm_index = self._armed_short
        invalidated = ob.invalidated_at is not None and ob.invalidated_at <= t
        if invalidated or (t - arm_index) > self.arm_ttl_bars:
            self._armed_short = None
            return None

        bos = detect_bos(self._candles, csw_asof, t, Trend.DOWN)
        if bos is None:
            return None

        bracket = self._build_bracket(Side.SHORT, bos, ob, cur, a, pools)
        self._armed_short = None
        if bracket is None:
            return None
        entry, sl, tp, is_limit = bracket
        return Signal(Side.SHORT, entry, sl, tp, ob.index, t,
                      "short OB tap + BOS down + SSL target", is_limit)

    # ---- лонг-ветка (зеркально) ----
    def _long_flow(self, csw_asof, pools, cur, t, a) -> Optional[Signal]:
        if self._armed_long is None:
            for ob in sorted(self._asof_strong(Side.LONG, t), key=lambda b: -b.index):
                tapped = cur.high >= ob.low and cur.low <= ob.high
                if tapped and ob.confirmed_at < t:
                    self._armed_long = (ob, t)
                    break
            return None

        ob, arm_index = self._armed_long
        invalidated = ob.invalidated_at is not None and ob.invalidated_at <= t
        if invalidated or (t - arm_index) > self.arm_ttl_bars:
            self._armed_long = None
            return None

        bos = detect_bos(self._candles, csw_asof, t, Trend.UP)
        if bos is None:
            return None

        bracket = self._build_bracket(Side.LONG, bos, ob, cur, a, pools)
        self._armed_long = None
        if bracket is None:
            return None
        entry, sl, tp, is_limit = bracket
        return Signal(Side.LONG, entry, sl, tp, ob.index, t,
                      "long OB tap + BOS up + BSL target", is_limit)

    # ---- расчёт входа/стопа/цели (через общую функцию build_bracket) ----
    def _build_bracket(self, side: Side, bos, zone_ob, cur, a, pools):
        return build_bracket(self.cfg, self._candles, side, bos, cur, a, pools)
