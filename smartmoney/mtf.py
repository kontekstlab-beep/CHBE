"""Мультитаймфреймовая стратегия: настоящие две серии (HTF + LTF).

HTF (старший ТФ) даёт контекст: тренд, блоки заказов (зоны интереса), пулы
ликвидности. LTF (младший ТФ) — подтверждение слома структуры и точный вход.

Запрет look-ahead между ТФ: при обработке LTF-бара t доступны только те HTF-бары,
которые ЗАКРЫЛИСЬ не позже открытия этого LTF-бара (htf.close <= ltf[t].open).
Соответствие считается через bisect по временам закрытия HTF.

Бэктестер по-прежнему итерирует LTF-серию (входы/выходы на LTF); HTF передаётся
в конструктор, LTF — в prepare().
"""
from __future__ import annotations

import bisect
from typing import List, Optional

from .config import Config
from .liquidity import find_pools, mark_swept
from .models import Candle, Side, Trend
from .orderblocks import find_order_blocks, update_mitigation
from .strategy import Signal, build_bracket
from .structure import atr, classify_trend, detect_bos, find_swings


class MultiTFStrategy:
    def __init__(self, htf_candles: List[Candle], htf_ms: int, ltf_ms: int,
                 cfg: Config, allow_longs: bool = False, arm_ttl_bars: int = 20):
        self.htf = htf_candles
        self.htf_ms = htf_ms
        self.ltf_ms = ltf_ms
        self.cfg = cfg
        self.allow_longs = allow_longs
        self.arm_ttl_bars = arm_ttl_bars
        self._armed_short = None
        self._armed_long = None

    def prepare(self, ltf_candles: List[Candle]) -> None:
        cfg = self.cfg
        self.ltf = ltf_candles
        # --- HTF контекст ---
        self._htf_tsw = find_swings(self.htf, cfg.structure.trend_pivot_strength)
        self._htf_sw = find_swings(self.htf, cfg.structure.pivot_strength)
        self._htf_blocks = find_order_blocks(self.htf, self._htf_sw, cfg.orderblock)
        update_mitigation(self._htf_blocks, self.htf)
        self._htf_close = [h.ts + self.htf_ms for h in self.htf]
        # префиксные суммы close для быстрого HTF-SMA (фильтр режима)
        self._htf_px = [h.close for h in self.htf]
        self._htf_cumsum = [0.0]
        for x in self._htf_px:
            self._htf_cumsum.append(self._htf_cumsum[-1] + x)
        # --- LTF для подтверждения/входа ---
        self._ltf_csw = find_swings(ltf_candles, cfg.structure.confirm_pivot_strength)
        self._ltf_atr = atr(ltf_candles, cfg.orderblock.atr_period)
        self._armed_short = None
        self._armed_long = None

    def _htf_known(self, t: int) -> int:
        """Число HTF-баров, закрывшихся к открытию LTF-бара t (защита от look-ahead)."""
        return bisect.bisect_right(self._htf_close, self.ltf[t].ts)

    def _strong_htf(self, side: Side, k: int):
        oc = self.cfg.orderblock
        out = []
        for b in self._htf_blocks:
            if b.side != side or b.score < oc.min_ob_score:
                continue
            if b.confirmed_at > k - 1:            # блок ещё не подтверждён (не закрыт)
                continue
            if b.invalidated_at is not None and b.invalidated_at < k:  # уже инвалидирован
                continue
            out.append(b)
        return out

    def evaluate_at(self, t: int) -> Optional[Signal]:
        cfg = self.cfg
        k = self._htf_known(t)
        warmup = cfg.orderblock.atr_period + 2 * cfg.structure.pivot_strength + 3
        if k < warmup:
            return None

        trend = classify_trend(self._htf_tsw, k - 1, cfg.structure)
        cur = self.ltf[t]
        a = self._ltf_atr[t]
        # HTF пулы «as-of» (нужны только для target_mode=pool*)
        sw_asof = [s for s in self._htf_sw if s.confirmed_at <= k - 1][-cfg.liquidity.lookback_swings:]
        pools = mark_swept(find_pools(sw_asof, cfg.liquidity), self.htf, upto=k - 1)

        if trend == Trend.DOWN:
            sig = self._flow(Side.SHORT, k, pools, cur, t, a)
            if sig:
                return sig
        else:
            self._armed_short = None

        if self.allow_longs and trend == Trend.UP:
            sig = self._flow(Side.LONG, k, pools, cur, t, a)
            if sig:
                return sig
        elif trend != Trend.UP:
            self._armed_long = None
        return None

    def _regime_ok(self, side: Side, k: int) -> bool:
        """Фильтр режима: шорт только под HTF-SMA, лонг — над (as-of k известных баров)."""
        n = self.cfg.structure.regime_ma_len
        if n <= 0:
            return True
        if k < n:
            return False
        sma = (self._htf_cumsum[k] - self._htf_cumsum[k - n]) / n
        last_close = self._htf_px[k - 1]
        return last_close < sma if side == Side.SHORT else last_close > sma

    def _flow(self, side: Side, k: int, pools, cur, t, a) -> Optional[Signal]:
        if not self._regime_ok(side, k):
            self._set_armed(side, None)
            return None
        armed = self._armed_short if side == Side.SHORT else self._armed_long

        # ARM: LTF-цена коснулась зоны сильного HTF-блока
        if armed is None:
            for ob in sorted(self._strong_htf(side, k), key=lambda b: -b.index):
                if cur.high >= ob.low and cur.low <= ob.high:
                    armed = (ob, t)
                    break
            self._set_armed(side, armed)
            return None

        ob, arm_index = armed
        invalidated = ob.invalidated_at is not None and ob.invalidated_at < k
        if invalidated or (t - arm_index) > self.arm_ttl_bars:
            self._set_armed(side, None)
            return None

        # CONFIRM: слом структуры на LTF
        direction = Trend.DOWN if side == Side.SHORT else Trend.UP
        bos = detect_bos(self.ltf, self._ltf_csw, t, direction)
        if bos is None:
            return None

        bracket = build_bracket(self.cfg, self.ltf, side, bos, cur, a, pools)
        self._set_armed(side, None)
        if bracket is None:
            return None
        entry, sl, tp, is_limit = bracket
        tag = "MTF short: HTF zone + LTF BOS" if side == Side.SHORT else "MTF long: HTF zone + LTF BOS"
        return Signal(side, entry, sl, tp, ob.index, t, tag, is_limit)

    def _set_armed(self, side: Side, value) -> None:
        if side == Side.SHORT:
            self._armed_short = value
        else:
            self._armed_long = value
