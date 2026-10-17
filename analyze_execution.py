"""Execution report for the spot-testnet run (MAIN z<-2 + B2 z<-1.5, one account).

Parses paper.log / paper_b2.log, EXCLUDING offline replay bursts (run_paper.py
--once): replay = a burst of >=8 trade events within the SAME second (the
offline replay processes all coins at once; the live loop steps them serially
over ~40s and never produces such bursts).

Outputs:
  1) trade stats per bot (n, winrate, total/avg P&L USDT, avg net%/trade by
     entry price incl. ladder-averaged entries), by exit reason and by wave;
  2) limit-order fill rates (placed / filled / TTL-canceled / postOnly-rejected
     / insufficient-balance-rejected), per bot and per coin;
  3) real fees via fetch_my_trades on the spot testnet (keys from .env,
     read-only) - account level;
  4) market-exit slippage: testnet fill price vs MAINNET close of the same
     1h bar (binanceusdm public klines);
  5) manual orphan sales on 14.10 (from the restart-fill bug) as a separate line.

All prints ASCII-only. No orders are created or canceled anywhere.
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from statistics import mean, median

HOUR = 3_600_000
TRADE_WORDS = ("ВХОД", "ПОЗИЦИЯ", "ЗАКРЫТА", "ЛЕСЕНКА")
RE_ENTRY = re.compile(r"^(\S+ \S+) INFO (\S+) ВХОД лимитка @([\d.]+)")
RE_OPEN = re.compile(r"^(\S+ \S+) INFO (\S+) ПОЗИЦИЯ открыта @([\d.]+)")
RE_CLOSE = re.compile(r"^(\S+ \S+) INFO (\S+) ЗАКРЫТА @([\d.]+) \[(\w+)\] pnl=([-\d.]+)")
RE_LADDER = re.compile(r"^(\S+ \S+) INFO (\S+) ЛЕСЕНКА лимитка @([\d.]+)")
RE_LADDER_FILL = re.compile(r"^(\S+ \S+) INFO (\S+) ЛЕСЕНКА @[\d.]+: усреднение entry=([\d.]+)")
RE_TTL = re.compile(r"INFO (\S+) (?:лимитка|лесенка) отменена")
RE_REJECT = re.compile(r"(?:INFO|WARNING) (\S+) ордер отклонён \(buy\): (.+)$")


def parse(path):
    """-> (trades, orders, rejects) with replay bursts excluded."""
    raw = open(path, encoding="utf-8").read().splitlines()
    # 1) mark replay bursts: >=8 trade lines in the same second
    by_sec = defaultdict(list)
    for i, ln in enumerate(raw):
        if any(w in ln for w in TRADE_WORDS):
            by_sec[ln[:19]].append(i)
    replay_idx = set()
    for sec, idxs in by_sec.items():
        if len(idxs) >= 8:
            replay_idx.update(idxs)
    lines = [ln for i, ln in enumerate(raw) if i not in replay_idx]
    n_replay = len(replay_idx)

    trades, orders, rejects = [], [], []
    pend, open_pos = {}, {}
    for ln in lines:
        m = RE_ENTRY.search(ln)
        if m:
            ts, sym, px = m.group(1), m.group(2), float(m.group(3))
            pend[sym] = dict(ts=ts, limit=px)
            orders.append(dict(sym=sym, ts=ts, kind="entry", limit=px))
            continue
        m = RE_LADDER.search(ln)
        if m:
            orders.append(dict(sym=m.group(2), ts=m.group(1),
                               kind="ladder", limit=float(m.group(3))))
            continue
        m = RE_LADDER_FILL.search(ln)
        if m and m.group(2) in open_pos:
            open_pos[m.group(2)]["entry"] = float(m.group(3))
            continue
        m = RE_OPEN.search(ln)
        if m:
            ts, sym, px = m.group(1), m.group(2), float(m.group(3))
            open_pos[sym] = dict(sym=sym, entry=px, entry_ts=ts)
            continue
        m = RE_CLOSE.search(ln)
        if m and m.group(2) in open_pos:
            sym = m.group(2)
            t = open_pos.pop(sym)
            t.update(exit=float(m.group(3)), reason=m.group(4),
                     pnl=float(m.group(5)), exit_ts=m.group(1))
            trades.append(t)
            continue
        m = RE_TTL.search(ln)
        if m:
            orders.append(dict(sym=m.group(1), ts=ln[:19], kind="ttl"))
            continue
        m = RE_REJECT.search(ln)
        if m:
            rejects.append(dict(sym=m.group(1), ts=ln[:19], msg=m.group(2)))
    return trades, orders, rejects, open_pos, n_replay


def stats_block(label, trades):
    if not trades:
        print(f"{label}: no trades")
        return
    n = len(trades)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    tot = sum(t["pnl"] for t in trades)
    pcts = [t["exit"] / t["entry"] - 1 for t in trades]
    net01 = mean(pcts) - 0.002         # спот VIP0 0.1% за сторону
    net075 = mean(pcts) - 0.0015       # спот BNB 0.075% за сторону
    print(f"{label:28s} n={n:3d} win={wins/n*100:5.1f}% "
          f"sumP&L={tot:+9.2f} avgP&L={tot/n:+7.3f} "
          f"avg%={mean(pcts)*100:+6.3f}% med%={median(pcts)*100:+6.3f}% "
          f"net@0.1%={net01*100:+6.3f}% net@0.075%={net075*100:+6.3f}%")


def wave_of(ts):
    day = ts[:10]
    if day <= "2026-10-09":
        return "wave 8-9 Oct"
    if day <= "2026-10-13":
        return "wave 12-13 Oct"
    return "wave 14-16 Oct"


def trade_stats(label, trades):
    print(f"\n--- {label} ---")
    stats_block("ALL", trades)
    by_reason = defaultdict(list)
    for t in trades:
        by_reason[t["reason"]].append(t)
    for r, tr in sorted(by_reason.items()):
        stats_block(f"  exit={r}", tr)
    by_wave = defaultdict(list)
    for t in trades:
        by_wave[wave_of(t["exit_ts"])].append(t)
    for w, tr in sorted(by_wave.items()):
        stats_block(f"  {w}", tr)


def fill_stats(label, orders, rejects):
    entries = [o for o in orders if o["kind"] in ("entry", "ladder")]
    ttl = [o for o in orders if o["kind"] == "ttl"]
    insuf = [r for r in rejects if "insufficient balance" in r["msg"]]
    postonly = [r for r in rejects if "immediately match" in r["msg"]]
    other = len(rejects) - len(insuf) - len(postonly)
    print(f"\n--- {label} ---")
    print(f"limits placed (entry+ladder, accepted): {len(entries)} | "
          f"TTL cancels: {len(ttl)} | rejects: insufficient={len(insuf)} "
          f"postOnly={len(postonly)} other={other}")
    by_coin = defaultdict(lambda: [0, 0, 0, 0])
    for o in entries:
        by_coin[o["sym"]][0] += 1
    for o in ttl:
        by_coin[o["sym"]][1] += 1
    for r in insuf:
        by_coin[r["sym"]][2] += 1
    for r in postonly:
        by_coin[r["sym"]][3] += 1
    print(f"{'sym':14s} {'placed':>6s} {'ttl':>5s} {'insuf':>6s} {'postOnly':>8s}")
    for sym, (p, t, i, po) in sorted(by_coin.items(), key=lambda kv: -kv[1][0]):
        print(f"{sym:14s} {p:6d} {t:5d} {i:6d} {po:8d}")


def real_fees(symbols):
    """fetch_my_trades on spot testnet (read-only), keys from .env."""
    try:
        import ccxt
    except ImportError:
        print("ccxt missing - skip")
        return None
    key = secret = None
    with open(".env", encoding="utf-8") as f:
        for ln in f:
            if ln.startswith("BINANCE_TESTNET_KEY="):
                key = ln.strip().split("=", 1)[1]
            if ln.startswith("BINANCE_TESTNET_SECRET="):
                secret = ln.strip().split("=", 1)[1]
    if not key or not secret:
        print("no testnet keys in .env - skip")
        return None
    ex = ccxt.binance({"apiKey": key, "secret": secret, "enableRateLimit": True})
    ex.set_sandbox_mode(True)
    tot_fee_usdt = 0.0
    tot_quote = 0.0
    assets = defaultdict(float)
    n_tr = 0
    for sym in sorted(symbols):
        try:
            rows = ex.fetch_my_trades(sym, limit=1000)
        except Exception as e:
            print(f"  {sym}: fetch_my_trades failed: {e}")
            continue
        for r in rows:
            n_tr += 1
            fee = float(r["fee"]["cost"])
            asset = r["fee"]["currency"]
            price = float(r["price"])
            qty = float(r["amount"])
            if asset == "USDT":
                fee_usdt = fee
            else:                       # base-asset fee -> convert at trade price
                fee_usdt = fee * price
            tot_fee_usdt += fee_usdt
            assets[asset] += fee
            tot_quote += price * qty
    print(f"\n=== REAL FEES (fetch_my_trades, account-level) ===")
    print(f"fills analyzed: {n_tr} | notional: {tot_quote:.2f} USDT | "
          f"total fees: {tot_fee_usdt:.2f} USDT")
    print(f"effective rate per side: {tot_fee_usdt/tot_quote*100 if tot_quote else 0:.4f}%")
    print("fee by asset (native units): " + ", ".join(
        f"{a}={v:.6f}" for a, v in sorted(assets.items())))
    return dict(n=n_tr, fee=tot_fee_usdt, quote=tot_quote)


def slippage(trades_all):
    """Market exits (stop/time): testnet fill vs MAINNET close of the same bar."""
    import ccxt
    import datetime
    ex = ccxt.binanceusdm({"enableRateLimit": True})
    rows_out = []
    for t in trades_all:
        if t["reason"] not in ("stop", "time"):
            continue
        sym = t["sym"]
        # exit bar = hour of exit_ts minus 1h (bot steps on closed bars)
        dt = datetime.datetime.strptime(t["exit_ts"], "%Y-%m-%d %H:%M:%S,%f")
        exit_hour = dt.replace(minute=0, second=0, microsecond=0)
        bar_open = exit_hour - datetime.timedelta(hours=1)
        ts_ms = int(bar_open.replace(tzinfo=datetime.UTC).timestamp() * 1000)
        try:
            kl = ex.fetch_ohlcv(sym, "1h", since=ts_ms, limit=3)
        except Exception as e:
            print(f"  {sym} klines failed: {e}")
            continue
        main_close = None
        for k in kl:
            if k[0] == ts_ms:
                main_close = k[4]
        if main_close is None:
            continue
        slip = (main_close - t["exit"]) / main_close * 100   # sell: + = sold below mainnet close (worse)
        rows_out.append((sym, t["bot"], t["reason"], t["exit_ts"],
                         t["exit"], main_close, slip))
    return rows_out


def main() -> None:
    bots = {}
    for label, path in (("MAIN", "paper.log"), ("B2", "paper_b2.log")):
        trades, orders, rejects, open_pos, n_replay = parse(path)
        for t in trades:
            t["bot"] = label
        bots[label] = dict(trades=trades, orders=orders, rejects=rejects,
                           open=open_pos)
        print(f"{label}: live trades={len(trades)}, replay lines excluded={n_replay}, "
              f"open positions now={len(open_pos)}")
        trade_stats(label, trades)
        fill_stats(label + " limit orders", orders, rejects)

    all_tr = bots["MAIN"]["trades"] + bots["B2"]["trades"]
    trade_stats("TOTAL (both bots)", all_tr)

    print("\n=== ORPHANS (manual sale 14.10, restart-fill bug) ===")
    orphan_in = {"BTC/USDT": 82592.01, "SOL/USDT": 108.78,
                 "ETC/USDT": 8.28, "IMX/USDT": 0.1821}
    orphan_out = {"BTC/USDT": (0.0043, 83494.98), "SOL/USDT": (3.253, 107.27),
                  "ETC/USDT": (42.74, 8.11), "IMX/USDT": (1943.28, 0.1741)}
    tot = 0.0
    for sym, (qty, px) in orphan_out.items():
        entry = orphan_in[sym]
        pnl = qty * (px - entry) - qty * (entry * 0.001 + px * 0.001)  # 0.1% spot both sides
        tot += pnl
        print(f"{sym:10s} qty={qty} in@{entry} out@{px} -> P&L={pnl:+.2f} USDT "
              f"({(px/entry-1)*100:+.2f}%)")
    print(f"orphans total P&L (incl. 0.1%/side fees): {tot:+.2f} USDT")

    symbols = sorted({t["sym"] for t in all_tr} | set(orphan_in))
    real_fees(symbols)

    print("\n=== MARKET-EXIT SLIPPAGE (testnet fill vs MAINNET 1h close) ===")
    rows = slippage(all_tr)
    if rows:
        slips = [r[6] for r in rows]
        print(f"n={len(rows)} | mean slip={mean(slips):+.3f}% | "
              f"median={median(slips):+.3f}% | "
              f"worse-than-mainnet share={sum(1 for s in slips if s>0)/len(slips)*100:.0f}%")
        for sym, bot, reason, ts, fill, mc, slip in rows:
            print(f"  {bot:4s} {sym:10s} {ts[:16]} {reason:9s} "
                  f"testnet={fill:.6g} mainnet={mc:.6g} slip={slip:+.2f}%")
        print("NOTE: testnet order book != mainnet; part of the slip is sandbox "
              "divergence, on real execution it should be better.")


if __name__ == "__main__":
    main()
