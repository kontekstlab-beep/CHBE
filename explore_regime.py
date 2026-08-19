"""M3.7: гипотеза «фильтр режима по дневной SMA».

Протокол (без утечки OOS):
  1) на ТЮНИНГ-наборе (8 старых монет) walk-forward подбираем regime_ma_len;
  2) замораживаем лучший и ОДИН раз гоняем на OOS-наборе (10 новых монет),
     сравниваем с baseline (regime off, = mtf_1d_v1).

    python explore_regime.py
"""
from __future__ import annotations

from typing import List

from smartmoney.backtest import Backtester, BacktestConfig
from smartmoney.data import _TF_MS, get_cached
from smartmoney.models import Candle
from smartmoney.mtf import MultiTFStrategy
from smartmoney.presets import mtf_1d_v1

TUNE = ["SOL/USDT", "LINK/USDT", "NEAR/USDT", "FIL/USDT", "APE/USDT", "XRP/USDT", "BNB/USDT", "CRV/USDT"]
OOS = ["1INCH/USDT", "GALA/USDT", "CHR/USDT", "ETH/USDT", "ADA/USDT", "DOGE/USDT",
       "AVAX/USDT", "DOT/USDT", "LTC/USDT", "ATOM/USDT"]
LTF, HTF, K = "1h", "1d", 5


def reindex(seq):
    return [Candle(i, c.ts, c.open, c.high, c.low, c.close, c.volume) for i, c in enumerate(seq)]


def stats(R: List[float]):
    n = len(R)
    exp = sum(R) / n if n else 0.0
    wr = sum(1 for r in R if r > 0) / n * 100 if n else 0.0
    gw = sum(r for r in R if r > 0)
    gl = -sum(r for r in R if r < 0)
    pf = gw / gl if gl > 0 else float("inf")
    return n, wr, exp, pf


def cfg_with(ma_len: int):
    cfg = mtf_1d_v1()
    cfg.structure.regime_ma_len = ma_len
    return cfg


def run_symbol(ltf, htf, ma_len):
    st = MultiTFStrategy(htf, _TF_MS[HTF], _TF_MS[LTF], cfg_with(ma_len),
                         allow_longs=True, arm_ttl_bars=30)
    return [t.r_multiple for t in Backtester(cfg_with(ma_len), BacktestConfig()).run(ltf, st).trades]


def load(symbols):
    return {s: (get_cached(s, LTF, 4000), get_cached(s, HTF, 1000)) for s in symbols}


def walkforward(data, ma_len):
    folds = [[] for _ in range(K)]
    for s, (ltf, htf) in data.items():
        m = len(ltf) // K
        for k in range(K):
            folds[k].append((reindex(ltf[k * m:(k + 1) * m]), htf))
    pos = 0
    allR: List[float] = []
    for k in range(K):
        R = []
        for cs, htf in folds[k]:
            R += run_symbol(cs, htf, ma_len)
        allR += R
        if stats(R)[2] > 0:
            pos += 1
    n, wr, exp, pf = stats(allR)
    return n, wr, exp, pf, pos


def full(data, ma_len):
    allR: List[float] = []
    posc = 0
    for s, (ltf, htf) in data.items():
        R = run_symbol(ltf, htf, ma_len)
        allR += R
        if stats(R)[2] > 0:
            posc += 1
    n, wr, exp, pf = stats(allR)
    return n, wr, exp, pf, posc


def main() -> None:
    tune = load(TUNE)
    print("=== 1) Подбор regime_ma_len на ТЮНИНГ-наборе (walk-forward) ===")
    print(f"{'ma_len':>7s} {'сделок':>6s} {'win%':>6s} {'exp,R':>7s} {'pf':>5s} {'+окон':>6s}")
    best = None
    for ma in (0, 10, 20, 50):
        n, wr, exp, pf, pos = walkforward(tune, ma)
        pfs = "inf" if pf == float("inf") else f"{pf:.2f}"
        tag = " (baseline)" if ma == 0 else ""
        print(f"{ma:7d} {n:6d} {wr:6.1f} {exp:+7.3f} {pfs:>5s} {pos:>4d}/{K}{tag}")
        if ma != 0 and (best is None or (pos, exp) > (best[1], best[2])):
            best = (ma, pos, exp)
    best_ma = best[0]
    print(f"\nЛучший фильтр на тюнинге: regime_ma_len={best_ma}")

    print("\n=== 2) OOS-проверка (10 новых монет), заморожено ===")
    oos = load(OOS)
    for label, ma in (("baseline (off)", 0), (f"regime SMA{best_ma}", best_ma)):
        n, wr, exp, pf, posc = full(oos, ma)
        pfs = "inf" if pf == float("inf") else f"{pf:.2f}"
        print(f"  {label:18s}: сделок={n:4d} win={wr:4.1f}% exp={exp:+.3f}R pf={pfs} монет+={posc}/{len(OOS)}")

    print("\n=== Вердикт ===")
    nb = full(oos, 0)
    nf = full(oos, best_ma)
    d = nf[2] - nb[2]
    if nf[2] > 0 and d > 0.02:
        print(f"Фильтр УЛУЧШИЛ OOS: exp {nb[2]:+.3f}R -> {nf[2]:+.3f}R (Δ{d:+.3f}R), монет+ {nb[4]}->{nf[4]}.")
    elif abs(d) <= 0.02:
        print(f"Фильтр не изменил OOS существенно (Δ{d:+.3f}R). Гипотеза не подтверждена.")
    else:
        print(f"Фильтр УХУДШИЛ OOS (Δ{d:+.3f}R). Гипотеза отвергнута.")


if __name__ == "__main__":
    main()
