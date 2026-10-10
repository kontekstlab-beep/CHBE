"""Общий движок исследования M6 (mean-reversion, свежие данные до 2026-10-09).

Переиспользует формулу z из meanrev.zseries (та же, что в paper/signal.py).
Модель исполнения — консервативная, как в meanrev_maker.py: лимит-покупка
исполняется, только если low одного из fill_window следующих баров коснулся
лимит-цены; иначе сигнал пропускается. Выходы: reversion (z >= exit_z, лимит на
SMA ~ maker), катастроф-стоп (adverse-first по low, taker), тайм-стоп (taker).

Комиссии — по факту maker/taker каждой ноги сделки:
  вход всегда maker (лимитка), выход reversion/partial = maker, stop/time = taker.

Наборы: EXPL18 (вся разведка) и FRESH12 (строгая финальная валидация).
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from statistics import mean, median, pstdev
from typing import Dict, List, Optional, Tuple

from meanrev import zseries

# --- наборы M6 (суффикс /USDT) ---
EXPL18 = ["SOL", "LINK", "NEAR", "FIL", "APE", "XRP", "BNB", "CRV", "1INCH",
          "GALA", "CHR", "ETH", "ADA", "DOGE", "AVAX", "DOT", "LTC", "ATOM"]
FRESH12 = ["TON", "HBAR", "XLM", "ALGO", "ICP", "ETC",
           "FET", "RENDER", "TIA", "SEI", "ONDO", "IMX"]

# --- модели комиссий: (maker, taker), за сторону ---
FEES = {
    "FUTURES": (0.0002, 0.0005),
    "SPOT_VIP0": (0.001, 0.001),
    "SPOT_BNB": (0.00075, 0.00075),
}

DATA_DIR = "data"
CACHE: Dict[str, dict] = {}


def load(sym: str) -> dict:
    """OHLCV по базовой монете ('SOL') из data/<SYM>USDT_1h_4000.csv."""
    if sym in CACHE:
        return CACHE[sym]
    path = os.path.join(DATA_DIR, sym + "USDT_1h_4000.csv")
    ts, o, h, lo, c, v = [], [], [], [], [], []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ts.append(int(float(r["ts"])))
            o.append(float(r["open"]))
            h.append(float(r["high"]))
            lo.append(float(r["low"]))
            c.append(float(r["close"]))
            v.append(float(r["volume"]))
    d = dict(sym=sym, ts=ts, o=o, h=h, lo=lo, c=c, v=v)
    CACHE[sym] = d
    return d


@dataclass
class Cfg:
    n: int = 48
    entry_z: float = -2.0
    exit_z: float = 0.0
    max_hold: int = 8
    stop: float = 0.08
    offset: float = 0.0          # глубина лимитки ниже close (лонг)
    fill_window: int = 3
    side: str = "long"           # 'long' | 'short'
    ladder_z: Optional[float] = None   # вторая порция 5% при z < ladder_z
    confirm: bool = False        # ждать первый зелёный бар после триггера
    confirm_window: int = 3
    partial_z: Optional[float] = None  # частичная фиксация 50% при z >= partial_z
    btc_mode: Optional[str] = None     # 'req_z' (BTC z<=btc_z) | 'req_z_inv' | 'block_crash'
    btc_z: float = -1.0
    btc_crash: float = -0.05           # запрет, если BTC 24ч ретерн < btc_crash
    vol_z: Optional[float] = None      # входить только при всплеске объёма z > vol_z
    knife: bool = False                # запрет при ускоряющемся падении
    hours: Optional[set] = None        # разрешённые часы UTC (None = все)
    ladder_hours: bool = False         # True -> часовой фильтр действует и на лесенку
    fee_model: str = "FUTURES"
    flat_fee: Optional[float] = None   # если задано — плоская комиссия за сторону


@dataclass
class Trade:
    sym: str
    entry_i: int
    exit_i: int
    hour: int
    reason: str
    gross: float    # доходность до комиссий
    fees: float     # суммарные комиссии (round-trip, в долях)
    net: float      # gross - fees
    mfe: float = 0.0   # макс. благоприятное отклонение за жизнь сделки (доли)
    mae: float = 0.0   # макс. неблагоприятное отклонение (доли, <= 0)


def hour_of(ts_ms: int) -> int:
    return (ts_ms // 3_600_000) % 24


def _btc_context() -> Dict[int, Tuple[float, float]]:
    """ts -> (z_btc48, ret24) по BTC/USDT."""
    btc = load("BTC")
    z = zseries(btc["c"], 48)
    out: Dict[int, Tuple[float, float]] = {}
    for i, t in enumerate(btc["ts"]):
        r24 = btc["c"][i] / btc["c"][i - 24] - 1 if i >= 24 else 0.0
        out[t] = (z[i] if z[i] is not None else 0.0, r24)
    return out


_BTC: Optional[Dict[int, Tuple[float, float]]] = None


def btc_ctx() -> Dict[int, Tuple[float, float]]:
    global _BTC
    if _BTC is None:
        _BTC = _btc_context()
    return _BTC


def _vol_z_ok(d: dict, i: int, n: int, thr: float) -> bool:
    if i < n:
        return False
    w = d["v"][i - n:i]
    m = sum(w) / n
    sd = pstdev(w) or 1e-9
    return (d["v"][i] - m) / sd > thr


def _knife(d: dict, i: int) -> bool:
    """Падение ускоряется: ретерн последних 3 баров хуже предыдущих 3."""
    if i < 6:
        return False
    c = d["c"]
    r_last = c[i] / c[i - 3] - 1
    r_prev = c[i - 3] / c[i - 6] - 1
    return r_last < r_prev


def _btc_ok(cfg: Cfg, ts_ms: int) -> bool:
    if cfg.btc_mode is None:
        return True
    bz, r24 = btc_ctx().get(ts_ms, (0.0, 0.0))
    if cfg.btc_mode == "req_z":
        return bz <= cfg.btc_z
    if cfg.btc_mode == "req_z_inv":      # комплементарная рука: BTC НЕ в проливе
        return bz > cfg.btc_z
    if cfg.btc_mode == "block_crash":
        return r24 > cfg.btc_crash
    raise ValueError(cfg.btc_mode)


def _fees(cfg: Cfg, reason: str, partial: bool) -> float:
    """Round-trip комиссии: вход maker; выход maker при reversion/partial, иначе taker."""
    if cfg.flat_fee is not None:
        mk = tk = cfg.flat_fee
    else:
        mk, tk = FEES[cfg.fee_model]
    fee_out = mk if reason == "reversion" else tk
    if partial:                       # половина вышла maker на partial_z, половина — fee_out
        return mk + 0.5 * mk + 0.5 * fee_out
    return mk + fee_out


def backtest_coin(d: dict, cfg: Cfg) -> List[Trade]:
    c, lo, hi, ts, o = d["c"], d["lo"], d["h"], d["ts"], d["o"]
    z = zseries(c, cfg.n)
    L = len(c)
    trades: List[Trade] = []
    long = cfg.side == "long"
    i = cfg.n
    while i < L - 1:
        zi = z[i]
        trig = (zi is not None and zi < cfg.entry_z) if long \
            else (zi is not None and zi > -cfg.entry_z)
        if not trig:
            i += 1
            continue
        # фильтры на баре триггера
        if cfg.hours is not None and hour_of(ts[i]) not in cfg.hours:
            i += 1
            continue
        if cfg.vol_z is not None and not _vol_z_ok(d, i, cfg.n, cfg.vol_z):
            i += 1
            continue
        if cfg.knife and _knife(d, i):
            i += 1
            continue
        if not _btc_ok(cfg, ts[i]):
            i += 1
            continue
        # вход (опционально — с подтверждением зелёным баром)
        sig = i
        if cfg.confirm:
            j = i + 1
            last = min(i + cfg.confirm_window, L - 1)
            while j <= last and not (c[j] > o[j]):
                j += 1
            if j > last:
                i += 1
                continue
            sig = j
        limit = c[sig] * (1 - cfg.offset) if long else c[sig] * (1 + cfg.offset)
        entry_bar = None
        for jj in range(sig + 1, min(sig + 1 + cfg.fill_window, L)):
            touch = lo[jj] <= limit if long else hi[jj] >= limit
            if touch:
                entry_bar = jj
                break
        if entry_bar is None:
            i = sig + 1
            continue
        # сопровождение позиции
        portions = 1
        entry = limit
        add_limit = None
        partial_px = None
        exit_px = None
        reason = None
        mfe = mae = 0.0
        k = entry_bar + 1
        while k < L:
            zk = z[k]
            # MFE/MAE относительно текущего (усредняемого) entry
            if long:
                mfe = max(mfe, hi[k] / entry - 1)
                mae = min(mae, lo[k] / entry - 1)
            else:
                mfe = max(mfe, entry / lo[k] - 1)
                mae = min(mae, entry / hi[k] - 1)
            if cfg.stop > 0:
                if long and lo[k] <= entry * (1 - cfg.stop):
                    exit_px, reason = entry * (1 - cfg.stop), "stop"
                    break
                if not long and hi[k] >= entry * (1 + cfg.stop):
                    exit_px, reason = entry * (1 + cfg.stop), "stop"
                    break
            # лесенка: вторая порция (заявка ставится на баре сигнала,
            # исполняется не раньше следующего бара)
            if cfg.ladder_z is not None and portions < 2:
                if add_limit is not None:
                    filled_add = lo[k] <= add_limit if long else hi[k] >= add_limit
                    if filled_add:
                        entry = (entry * portions + add_limit) / (portions + 1)
                        portions += 1
                    add_limit = None
                deep = (zk is not None and zk < cfg.ladder_z) if long \
                    else (zk is not None and zk > -cfg.ladder_z)
                if cfg.ladder_hours and cfg.hours is not None \
                        and hour_of(ts[k]) not in cfg.hours:
                    deep = False
                if deep and portions < 2:
                    add_limit = c[k]
            # частичная фиксация 50%
            if cfg.partial_z is not None and partial_px is None and zk is not None:
                if long and cfg.partial_z <= zk < cfg.exit_z:
                    partial_px = c[k]
                if not long and cfg.exit_z < zk <= -cfg.partial_z:
                    partial_px = c[k]
            exitc = (zk is not None and zk >= cfg.exit_z) if long \
                else (zk is not None and zk <= cfg.exit_z)
            if exitc:
                exit_px, reason = c[k], "reversion"
                break
            if (k - entry_bar) >= cfg.max_hold:
                exit_px, reason = c[k], "time"
                break
            k += 1
        if exit_px is None:
            exit_px, reason, k = c[L - 1], "end", L - 1
        gross = (exit_px / entry - 1) if long else (entry / exit_px - 1)
        if partial_px is not None:
            pg = (partial_px / entry - 1) if long else (entry / partial_px - 1)
            gross = 0.5 * pg + 0.5 * gross
        fees = _fees(cfg, reason, partial_px is not None)
        trades.append(Trade(d["sym"], entry_bar, k, hour_of(ts[i]), reason,
                            gross, fees, gross - fees, mfe, mae))
        i = k + 1
    return trades


def run_set(symbols: List[str], cfg: Cfg) -> List[Trade]:
    out: List[Trade] = []
    for s in symbols:
        out += backtest_coin(load(s), cfg)
    return out


def basic_stats(trades: List[Trade]) -> dict:
    n = len(trades)
    if not n:
        return dict(n=0, win=0.0, net=0.0, pf=0.0, med=0.0, worst=0.0,
                    gross=0.0, feeavg=0.0)
    R = [t.net for t in trades]
    m = mean(R)
    wr = sum(1 for r in R if r > 0) / n * 100
    gw = sum(r for r in R if r > 0)
    gl = -sum(r for r in R if r < 0)
    pf = gw / gl if gl > 0 else float("inf")
    per_coin: Dict[str, List[float]] = {}
    for t in trades:
        per_coin.setdefault(t.sym, []).append(t.net)
    med = median(mean(v) for v in per_coin.values())
    return dict(n=n, win=wr, net=m, pf=pf, med=med, worst=min(R),
                gross=mean(t.gross for t in trades),
                feeavg=mean(t.fees for t in trades))


def portfolio(trades: List[Trade], frac: float = 0.05) -> Tuple[float, float]:
    """Портфельная симуляция: frac капитала на позицию, без компаундинга.
    Возвращает (суммарный P&L в долях капитала, max drawdown)."""
    by_exit: Dict[int, float] = {}
    for t in trades:
        by_exit[t.exit_i] = by_exit.get(t.exit_i, 0.0) + frac * t.net
    pnl = peak = mdd = 0.0
    for i in sorted(by_exit):
        pnl += by_exit[i]
        peak = max(peak, pnl)
        mdd = max(mdd, peak - pnl)
    return pnl, mdd


def report(label: str, trades: List[Trade], show_port: bool = True) -> dict:
    s = basic_stats(trades)
    pnl, mdd = portfolio(trades)
    pfs = "inf" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    port = f" P&Lпорт={pnl*100:+7.2f}% MDD={mdd*100:5.2f}%" if show_port else ""
    print(f"{label:44s} n={s['n']:4d} win={s['win']:5.1f}% "
          f"нетто={s['net']*100:+7.3f}% pf={pfs:>5s} мед={s['med']*100:+7.3f}% "
          f"худш={s['worst']*100:6.2f}%{port}")
    return {**s, "pnl": pnl, "mdd": mdd}


def per_coin_table(symbols: List[str], cfg: Cfg) -> None:
    rows = []
    for s in symbols:
        tr = backtest_coin(load(s), cfg)
        st = basic_stats(tr)
        rows.append((s, st))
    rows.sort(key=lambda x: x[1]["net"])
    for s, st in rows:
        pfs = "inf" if st["pf"] == float("inf") else f"{st['pf']:.2f}"
        print(f"  {s:7s} n={st['n']:3d} win={st['win']:5.1f}% "
              f"нетто={st['net']*100:+7.3f}% pf={pfs:>5s} худш={st['worst']*100:6.2f}%")
