#!/usr/bin/env python3
"""資料管線 —— 產出前端要吃的三個 JSON。

    python3 web/build_data.py

輸入:
    mstr_cebe/          公式與人工整理的事實來源
    mstr_cebe.sqlite    市場日線(BTC / MSTR)
    web/raw/*.json      8-K 爬回來的逐週原始資料(用 mstr_cebe.fetch_8k_* 重抓)

輸出(給 Vite bundle 用,不是給 fetch 用):
    app/data/daily.json   533 天日頻序列
    app/data/weekly.json  逐週持有量 / 買賣 / 融資來源 / ATM 募資
    app/data/meta.json    IPO、政策斷點、FWP 錨點、敏感度表、findings

⚠️ 前端不做任何金融計算,只做顯示。所有 mNAV / CEBE / 求償權都在這裡用
   mstr_cebe.core 算好 —— 那些公式有 125 個測試守著,不該在 TS 裡重寫一份。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mstr_cebe import core as C          # noqa: E402
from mstr_cebe import data as D          # noqa: E402
from mstr_cebe import db as DB           # noqa: E402
from mstr_cebe import interpolate as I   # noqa: E402

WEB = os.path.join(ROOT, "web")
OUT = os.path.join(ROOT, "app", "data")
RAW = os.path.join(WEB, "raw")

SECURITIES = ("STRF", "STRC", "STRK", "STRD", "STRE", "MSTR")


def _load_raw(name: str):
    with open(os.path.join(RAW, name), encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# daily.json
# ---------------------------------------------------------------------------

def build_daily() -> dict:
    conn = DB.connect(os.path.join(ROOT, "mstr_cebe.sqlite"))
    market = {dt.date.fromisoformat(r["date"]): r for r in DB.load_market_daily(conn)}
    pref_prices = _load_raw("preferred_prices.json")

    anchors = dict(
        btc_a=I.btc_held_anchors(), debt_a=I.debt_anchors(), cash_a=I.cash_anchors(),
        shares_a=I.shares_basic_anchors(), pref_a=I.preferred_share_anchors(),
    )

    dates = sorted(d for d, r in market.items()
                   if r["btc_close_usd"] and r["mstr_close_usd"])

    keys = ["date", "btc", "mstr", "held", "shares", "debt", "cash", "pref_total",
            "mnav_basic", "mnav_cebe", "claims_pct", "bps", "amp",
            "claims_btc", "common_btc", "stale"]
    out = {k: [] for k in keys}
    for t in I.PREFERRED_TICKERS:
        out[f"{t.lower()}_lp"] = []
        out[f"{t.lower()}_price"] = []

    for day in dates:
        row = market[day]
        btc, mstr = row["btc_close_usd"], row["mstr_close_usd"]
        cs, stale = I.interpolated_structure(day, **anchors)

        claims_usd = C.net_senior_claims_usd(cs, C.ClaimsBasis.CEBETRACKER, 0.0)
        claims_btc = claims_usd / btc
        cp = claims_btc / cs.btc_held

        out["date"].append(day.isoformat())
        out["btc"].append(round(btc, 2))
        out["mstr"].append(round(mstr, 2))
        out["held"].append(round(cs.btc_held, 0))
        out["shares"].append(round(cs.shares_basic / 1e6, 3))
        out["debt"].append(round(cs.debt_notional_usd / 1e9, 4))
        out["cash"].append(round(cs.cash_and_equiv_usd / 1e9, 4))
        out["pref_total"].append(round(cs.preferred_total_usd / 1e9, 4))
        out["mnav_basic"].append(round(C.mnav(cs, btc, mstr, C.MNavVariant.BASIC).value, 5))
        out["mnav_cebe"].append(round(C.mnav(cs, btc, mstr, C.MNavVariant.CEBE).value, 5))
        out["claims_pct"].append(round(cp, 6))
        out["bps"].append(round(cs.btc_held / cs.shares_basic * 1e8, 1))
        out["amp"].append(round(1 / (1 - cp), 4) if cp < 1 else None)
        # BTC 計價的資本結構 —— 供 riverBtc 圖用
        out["claims_btc"].append(round(claims_btc, 0))
        out["common_btc"].append(round(cs.btc_held - claims_btc, 0))
        # 只看真正牽動 mNAV 的欄位,四個小型優先股系列的稀疏度不該主導信心標示
        out["stale"].append(max(stale.get(k, 0) for k in
                                ("btc", "shares", "debt", "cash", "pref_STRC")))

        for t in I.PREFERRED_TICKERS:
            p = next((x for x in cs.preferreds if x.ticker == t), None)
            out[f"{t.lower()}_lp"].append(
                round(p.liquidation_preference_usd / 1e9, 4) if p else 0.0)
            out[f"{t.lower()}_price"].append(
                pref_prices.get(t, {}).get(day.isoformat()))

    return out


# ---------------------------------------------------------------------------
# weekly.json
# ---------------------------------------------------------------------------

def build_weekly() -> list:
    holdings = {d: v for d, v in _load_raw("btc_holdings_weekly.json")}
    activity = {a["week_end"]: a for a in _load_raw("btc_activity_weekly.json")}
    atm = {a["week_end"]: a for a in _load_raw("atm_weekly.json")}

    all_weeks = sorted(set(holdings) | set(activity) | set(atm))
    rows = []
    for w in all_weeks:
        a = activity.get(w, {})
        t = atm.get(w)
        raised = {}
        if t:
            for sec, v in t["by_security"].items():
                if v["net_proceeds_m"]:
                    raised[sec] = round(v["net_proceeds_m"], 1)

        funding = list(a.get("funding") or [])
        derived = False
        # 8-K 的敘述句有時只寫「under the ATM」沒指名券種,但同一份文件的
        # ATM Program Summary 表格已經逐券種列出當週淨募資 —— 有錢進來的
        # 券種就是資金來源。用表格補上敘述句的缺口,並標記為推得而非明示。
        if not funding and raised:
            funding = sorted(raised, key=lambda k: -raised[k])
            derived = True

        if (a.get("btc_delta") or 0) < 0:
            source = "btc_sale"
        elif funding:
            source = "derived" if derived else "named"
        elif a:
            source = "unspecified"
        else:
            source = None

        rows.append({
            "week_end": w,
            "week_start": a.get("week_start"),
            "holdings": holdings.get(w) or a.get("holdings"),
            "delta": a.get("btc_delta"),
            "avg_price": a.get("avg_price"),
            "funding": funding,
            "funding_derived": derived,
            "funding_raw": a.get("funding_raw", ""),
            "sale_use": a.get("sale_use", ""),
            "source_kind": source,
            "raised_m": raised,
            "raised_total_m": round(t["total_m"], 1) if t and t.get("total_m") else None,
        })
    return rows


# ---------------------------------------------------------------------------
# meta.json
# ---------------------------------------------------------------------------

def build_meta() -> dict:
    fwp = D.fwp_snapshot()
    p = D.PARAMS_2026_08_13
    return {
        "ipos": [{"t": i.ticker, "name": i.name, "d": i.pricing_date.isoformat(),
                  "lp": round(i.ipo_liquidation_pref / 1e9, 3), "rate": i.dividend_rate_pct,
                  "rank": i.rank, "note": i.note, "cur": i.currency}
                 for i in D.PREFERRED_IPOS],
        "breaks": [{"d": b.as_of.isoformat(), "title": b.title,
                    "detail": b.detail, "hard": b.breaks_timeseries}
                   for b in D.POLICY_BREAKS],
        "fwp": {
            "held": p["btc_held"], "btc": D.FWP_BTC_PRICE, "price": D.FWP_MSTR_PRICE,
            "fdso": p["fdso"], "basic": fwp.shares_basic,
            "assumed": D.FWP_SHARES_ASSUMED_DILUTED,
            "debt": p["debt_otm_notional"] / 1e9,
            "reserve": p["usd_reserve"] / 1e9,
            "pref": {k: round(v / 1e9, 4) for k, v in fwp.preferred_by_ticker.items()},
            "gross_bps": round(C.gross_bps_sats(fwp.btc_held, fwp.shares_assumed_diluted)),
            "net_bps": round(C.net_bps_sats(
                C.net_reserve_per_share_from(fwp, D.FWP_BTC_PRICE, D.FWP_MSTR_PRICE),
                D.FWP_BTC_PRICE)),
        },
        "sens": [{"btc": b, "off": o,
                  "got": round(C.net_reserve_per_share(b, **p), 4)}
                 for b, o in D.FWP_SENSITIVITY_TABLE],
        "be": [{"k": k, "v": round(v)} for k, v in sorted(
            C.break_even_all_bases(fwp, D.FWP_MSTR_PRICE).items(),
            key=lambda kv: kv[1])],
        "anchors": {
            "btc_held": [[a[0].isoformat(), a[1]] for a in I.btc_held_anchors()],
            "shares": [[a[0].isoformat(), a[1]] for a in I.shares_basic_anchors()],
            "debt": [[a[0].isoformat(), a[1]] for a in I.debt_anchors()],
        },
        "findings": [
            {"t": "BTC 持有量其實每週都在 8-K 裡,只是換了格式",
             "b": "早期是 prose 敘述,2025-03-31 之後改成「BTC Update」表格。單一關鍵字搜尋"
                  "會漏掉格式切換,導致誤判為「公司不再揭露」。修正後解出 90 個真實週觀測點,"
                  "平均間隔 8.7 天。"},
            {"t": "§5.9 的 2026-07-05 求償權數字自相矛盾",
             "b": "同列的 claims% 38.3%、BPS 227,057、CEBE 140,200 三者一致於 $19.63B 與 "
                  "371.6M 股,不是標示的 ~$21,000M。採用 $19.63B。"},
            {"t": "股數分母有三個,不是兩個",
             "b": "官方 Gross BPS 用 423.8M assumed diluted、Net BPS 用 398.2M FDSO,"
                  "而對照表的「basic 基準」用的是第三個:394.2M basic shares,差 7%。"},
            {"t": "$543 是盤中高點,不是收盤價",
             "b": "2024-11-21 收盤為 $397.28。用盤中高點對收盤價比較,會把壓縮幅度誇大約 37%。"},
            {"t": "融資來源:明示與推得要分開看",
             "b": "76 個有買賣的週次中,41 週在 8-K 敘述句明確寫出動用了哪些 ATM。"
                  "其餘只寫「under the ATM」,但同一份文件的 ATM 表格已逐券種列出當週淨募資,"
                  "有錢進來的券種即為資金來源 —— 這樣可再補 18 週,涵蓋率從 54% 提升到 78%。"
                  "表格中以「推得」標記,與敘述句明示者區分。仍有 2 週兩種來源都沒有資料。"},
            {"t": "優先股分系列仍是季頻",
             "b": "STRF/STRK/STRD/STRE 各自只有 3 個錨點(IPO + 2026-06-30),中間為線性推估。"
                  "四者合計約佔優先股總額的 32%,誤差有限但不是零。"},
        ],
    }


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    daily, weekly, meta = build_daily(), build_weekly(), build_meta()

    for name, payload in (("daily", daily), ("weekly", weekly), ("meta", meta)):
        path = os.path.join(OUT, f"{name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        print(f"  app/data/{name}.json  {os.path.getsize(path)//1024} KB")

    n = len(daily["date"])
    print(f"\ndaily : {n} 天  {daily['date'][0]} → {daily['date'][-1]}")
    print(f"weekly: {len(weekly)} 週  "
          f"{sum(1 for w in weekly if w['delta'])} 週有買賣")
    print(f"meta  : {len(meta['findings'])} findings, "
          f"{len(meta['ipos'])} IPOs, {len(meta['sens'])} 敏感度列")

    # 黃金測試:管線不能悄悄改掉官方錨點
    got = C.net_reserve_per_share(D.FWP_BTC_PRICE, **D.PARAMS_2026_08_13)
    assert abs(got - 92.11) < 0.02, f"FWP 每股淨值回歸: {got}"
    print(f"\n✓ 黃金錨點 BTC ${D.FWP_BTC_PRICE:,.0f} → ${got:.4f}/股(官方 $92.11)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
