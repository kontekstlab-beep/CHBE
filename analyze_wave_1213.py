"""Wave 12-13 Oct 2026 post-mortem: what could the bots have done differently?

Parses paper.log (main, z<-2) and paper_b2.log (sparring, z<-1.5), excluding the
test-replay garbage (timestamp 2026-10-10 00:57). Downloads fresh 1h candles to
tmp_fresh/ (never touches data/). Answers:
  a) stop-outs: price 24h after the stop - false breakdown or saved us?
  b) red time-stops: price +12h/+24h after exit - did the bounce come right after?
  c) entry quality: MAE after entry; hypothetical deeper limit -0.5%/-1.0%;
     entry at signal close vs next bar open;
  d) B2 (z<-1.5) vs main (z<-2) on overlapping symbols;
  e) ladder: did z reach -3, what if the second leg filled?

All prints ASCII-only.
"""
from __future__ import annotations

import os
import re
from statistics import mean, pstdev

from smartmoney.data import load_binance_paged, save_csv

HOUR = 3_600_000
TMP = "tmp_fresh"
WAVE_START = "2026-10-12 00:00"

RE_ENTRY = re.compile(r"^(\S+ \S+) INFO (\S+) ВХОД лимитка @([\d.]+)")
RE_OPEN = re.compile(r"^(\S+ \S+) INFO (\S+) ПОЗИЦИЯ открыта @([\d.]+)")
RE_CLOSE = re.compile(r"^(\S+ \S+) INFO (\S+) ЗАКРЫТА @([\d.]+) \[(\w+)\] pnl=([-\d.]+)")
RE_LADDER_FILL = re.compile(r"^(\S+ \S+) INFO (\S+) ЛЕСЕНКА @[\d.]+: усреднение entry=([\d.]+)")


def hour_ms(ts_str):
    import datetime
    ts_str = ts_str.replace(",", ".")
    dt = datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S.%f")
    ms = int(dt.replace(tzinfo=datetime.UTC).timestamp() * 1000)
    return ms - (ms % HOUR)          # floor to the hour bar


def parse_log(path, bot):
    """-> list of trades: dict(sym, sig_bar, entry_bar, entry, exit_bar, exit,
    reason, pnl, bot, ladder_avg). sig_bar/entry_bar/exit_bar in ms."""
    open_pos = {}     # sym -> trade dict being built
    pend = {}         # sym -> entry order info
    trades = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if "2026-10-10 00:57" in line:      # test replay garbage
                continue
            m = RE_ENTRY.match(line)
            if m:
                ts, sym, px = m.group(1), m.group(2), float(m.group(3))
                pend[sym] = dict(sig_bar=hour_ms(ts) - HOUR, limit=px)
                continue
            m = RE_LADDER_FILL.match(line)
            if m and m.group(2) in open_pos:
                open_pos[m.group(2)]["entry"] = float(m.group(3))  # averaged entry
                continue
            m = RE_OPEN.match(line)
            if m:
                ts, sym, px = m.group(1), m.group(2), float(m.group(3))
                p = pend.pop(sym, {})
                if p.get("sig_bar", 0) and p["sig_bar"] < hour_ms(WAVE_START + ":00.000"):
                    continue
                open_pos[sym] = dict(sym=sym, bot=bot, sig_bar=p.get("sig_bar"),
                                     entry_bar=hour_ms(ts) - HOUR, entry=px,
                                     limit=p.get("limit"))
                continue
            m = RE_CLOSE.match(line)
            if m:
                ts, sym = m.group(1), m.group(2)
                if sym not in open_pos:
                    continue
                t = open_pos.pop(sym)
                t.update(exit_bar=hour_ms(ts) - HOUR, exit=float(m.group(3)),
                         reason=m.group(4), pnl=float(m.group(5)))
                trades.append(t)
    for t in open_pos.values():                  # still open at log end
        t.update(exit_bar=None, exit=None, reason="open", pnl=None)
        trades.append(t)
    return trades


def load_fresh(sym):
    base = sym.replace("/", "")
    path = os.path.join(TMP, base + "_1h_fresh.csv")
    if not os.path.exists(path):
        cs = load_binance_paged(sym, "1h", 300, futures=True)
        save_csv(cs, path)
    ts, o, h, lo, c = [], [], [], [], []
    import csv
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ts.append(int(float(r["ts"])))
            o.append(float(r["open"]))
            h.append(float(r["high"]))
            lo.append(float(r["low"]))
            c.append(float(r["close"]))
    return dict(ts=ts, o=o, h=h, lo=lo, c=c, idx={t: i for i, t in enumerate(ts)})


def z48_series(c):
    z = [None] * len(c)
    for i in range(47, len(c)):
        w = c[i - 47:i + 1]
        m = sum(w) / 48
        sd = pstdev(w) or 1e-9
        z[i] = (w[-1] - m) / sd
    return z


DATA = {}


def d_of(sym):
    if sym not in DATA:
        DATA[sym] = load_fresh(sym)
    return DATA[sym]


def main() -> None:
    os.makedirs(TMP, exist_ok=True)
    trades = parse_log("paper.log", "MAIN") + parse_log("paper_b2.log", "B2")
    trades.sort(key=lambda t: (t["entry_bar"] or 0))
    print(f"parsed trades (wave 12-13 Oct): {len(trades)} "
          f"(MAIN={sum(1 for t in trades if t['bot']=='MAIN')}, "
          f"B2={sum(1 for t in trades if t['bot']=='B2')})")

    print("\n=== TRADE TABLE ===")
    print(f"{'bot':4s} {'sym':10s} {'entry_bar':>17s} {'entry':>10s} {'exit_bar':>17s} "
          f"{'exit':>10s} {'reason':>9s} {'pnl':>8s} {'pct':>7s}")
    for t in trades:
        import datetime
        eb = datetime.datetime.fromtimestamp(t["entry_bar"] / 1000, datetime.UTC)
        xb = (datetime.datetime.fromtimestamp(t["exit_bar"] / 1000, datetime.UTC)
              if t["exit_bar"] else None)
        pct = (t["exit"] / t["entry"] - 1) * 100 if t["exit"] else None
        print(f"{t['bot']:4s} {t['sym']:10s} {eb:%m-%d %H:%M} {t['entry']:>10.4f} "
              f"{xb:%m-%d %H:%M} " if xb else f"{t['bot']:4s} {t['sym']:10s} {eb:%m-%d %H:%M} {t['entry']:>10.4f} {'--':>17s} ",
              end="")
        if t["exit"]:
            print(f"{t['exit']:>10.4f} {t['reason']:>9s} {t['pnl']:>8.2f} {pct:>+6.2f}%")
        else:
            print(f"{'--':>10s} {'OPEN':>9s} {'--':>8s} {'--':>7s}")

    # ---------- per-trade analysis ----------
    print("\n=== A. STOP-OUTS: price after exit (window available: bars after exit) ===")
    for t in trades:
        if t["reason"] != "stop":
            continue
        d = d_of(t["sym"])
        i0 = d["idx"].get(t["exit_bar"])
        if i0 is None:
            continue
        fut_h = d["h"][i0 + 1:i0 + 25]
        fut_lo = d["lo"][i0 + 1:i0 + 25]
        rec = max(fut_h) > t["entry"] if fut_h else None
        print(f"{t['bot']:4s} {t['sym']:10s} stop @{t['exit']:.4f} entry={t['entry']:.4f} | "
              f"next {len(fut_h)}h: max_high={max(fut_h):.4f} min_low={min(fut_lo):.4f} | "
              f"back above entry: {rec}")

    print("\n=== B. RED TIME-STOPS: price after exit (available window only) ===")
    for t in trades:
        if t["reason"] != "time" or t["exit"] >= t["entry"]:
            continue
        d = d_of(t["sym"])
        i0 = d["idx"].get(t["exit_bar"])
        if i0 is None:
            continue
        c, h = d["c"], d["h"]
        avail = c[i0 + 1:]                    # bars after exit, as many as we have
        if not avail:
            continue
        mx = max(h[i0 + 1:])
        print(f"{t['bot']:4s} {t['sym']:10s} exit @{t['exit']:.4f} ({t['exit']/t['entry']-1:+.2%}) | "
              f"next {len(avail)}h: max_high {(mx/t['exit']-1)*100:+.2f}% "
              f"last_close {(avail[-1]/t['exit']-1)*100:+.2f}% "
              f"(vs entry: max {(mx/t['entry']-1)*100:+.2f}%)")

    print("\n=== C. ENTRY QUALITY: MAE, deeper-limit hypotheticals, close vs next open ===")
    for t in trades:
        if not t["exit"]:
            continue
        d = d_of(t["sym"])
        i_s = d["idx"].get(t["sig_bar"])
        i_e = d["idx"].get(t["entry_bar"])
        i_x = d["idx"].get(t["exit_bar"])
        if i_e is None or i_x is None:
            continue
        mae = min(d["lo"][i_e:i_x + 1]) / t["entry"] - 1
        next_open = d["o"][i_e]
        row = f"{t['bot']:4s} {t['sym']:10s} MAE={mae*100:+6.2f}% nextOpen_vs_fill={(next_open/t['entry']-1)*100:+5.2f}%"
        for dp in (0.005, 0.01):
            deep = t["entry"] * (1 - dp)
            fillw = min(d["lo"][i_e:i_e + 3])
            if fillw <= deep:
                hyp = (t["exit"] / deep - 1) * 100
                real = (t["exit"] / t["entry"] - 1) * 100
                row += f" | -{dp*100:.1f}%: FILL pnl {hyp:+.2f}% vs {real:+.2f}%"
            else:
                row += f" | -{dp*100:.1f}%: NO FILL"
        print(row)

    print("\n=== D. B2 (z<-1.5) vs MAIN (z<-2) on overlapping symbols ===")
    by_sym = {}
    for t in trades:
        by_sym.setdefault(t["sym"], {})[t["bot"]] = t
    for sym, pair in sorted(by_sym.items()):
        if "MAIN" in pair and "B2" in pair:
            m, b = pair["MAIN"], pair["B2"]
            pm = f"{(m['exit']/m['entry']-1)*100:+.2f}% ({m['reason']})" if m["exit"] else "OPEN"
            pb = f"{(b['exit']/b['entry']-1)*100:+.2f}% ({b['reason']})" if b["exit"] else "OPEN"
            print(f"{sym:10s} MAIN in@{m['entry']:.4f} out {pm} | "
                  f"B2 in@{b['entry']:.4f} out {pb}")

    print("\n=== E. LADDER: did z reach -3 during the position? hypothetical 2nd leg ===")
    for t in trades:
        if not t["exit"]:
            continue
        d = d_of(t["sym"])
        z = z48_series(d["c"])
        i_e = d["idx"].get(t["entry_bar"])
        i_x = d["idx"].get(t["exit_bar"])
        if i_e is None or i_x is None:
            continue
        hit = None
        for k in range(i_e + 1, i_x + 1):
            if z[k] is not None and z[k] < -3.0:
                hit = k
                break
        if hit is None:
            continue
        lad_px = d["c"][hit]
        filled = hit + 1 < len(d["c"]) and d["lo"][hit + 1] <= lad_px
        real = (t["exit"] / t["entry"] - 1) * 100
        if filled:
            avg = (t["entry"] + lad_px) / 2
            hyp = (t["exit"] / avg - 1) * 100
            print(f"{t['bot']:4s} {t['sym']:10s} z<-3 at bar {hit - i_e} of life, "
                  f"ladder @{lad_px:.4f} FILL: pnl {real:+.2f}% -> {hyp:+.2f}%")
        else:
            print(f"{t['bot']:4s} {t['sym']:10s} z<-3 at bar {hit - i_e} of life, "
                  f"ladder @{lad_px:.4f} NO FILL")


    print("\n=== F. BTC GATE (z48 of BTC) at each MAIN signal bar ===")
    btc = d_of("BTC/USDT")
    zb = z48_series(btc["c"])
    for t in trades:
        if t["bot"] != "MAIN" or t["sig_bar"] is None:
            continue
        i = btc["idx"].get(t["sig_bar"])
        zv = zb[i] if i is not None else None
        print(f"MAIN {t['sym']:10s} sig {t['sig_bar']} BTC z48 = "
              f"{zv if zv is None else round(zv, 2)} (gate needs < -1)")


if __name__ == "__main__":
    main()
