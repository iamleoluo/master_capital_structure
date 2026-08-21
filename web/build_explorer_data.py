"""匯出互動探索器用的完整每日資料。

每一天算:MSTR 收盤、BTC 收盤、basic/CEBE mNAV、槓桿(1-求償權%)、
STRC/STRF/STRK/STRD 的清算優先權與(有市價時的)市值,並標記每個欄位
離最近真實 SEC 觀測點多遠(days_to_anchor)—— 這是本頁對讀者的誠實聲明:
哪些是申報當天的硬資料,哪些是插值猜的。
"""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mstr_cebe import core as C
from mstr_cebe import data as D
from mstr_cebe import db as DB
from mstr_cebe import interpolate as I

conn = DB.connect(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mstr_cebe.sqlite"))
market = {dt.date.fromisoformat(r["date"]): r for r in DB.load_market_daily(conn)}

pref_prices = json.load(open("web/preferred_prices.json"))

btc_a = I.btc_held_anchors()
debt_a = I.debt_anchors()
cash_a = I.cash_anchors()
shares_a = I.shares_basic_anchors()
pref_a = I.preferred_share_anchors()

dates = sorted(d for d, r in market.items() if r["btc_close_usd"] and r["mstr_close_usd"])
d = {k: [] for k in ["date", "btc", "mstr", "held", "shares", "debt", "cash",
                     "pref_total", "mnav_basic", "mnav_cebe", "claims_pct",
                     "bps", "amp", "days_stale_max"]}
for t in I.PREFERRED_TICKERS:
    d[f"{t.lower()}_shares"] = []
    d[f"{t.lower()}_price"] = []
    d[f"{t.lower()}_mktcap"] = []
    d[f"{t.lower()}_lp"] = []

anchor_dates_btc = sorted(x[0] for x in btc_a)
anchor_dates_shares = sorted(x[0] for x in shares_a)

for day in dates:
    row = market[day]
    btc, mstr = row["btc_close_usd"], row["mstr_close_usd"]
    cs, stale = I.interpolated_structure(day, btc_a, debt_a, cash_a, shares_a, pref_a)

    d["date"].append(day.isoformat())
    d["btc"].append(round(btc, 2))
    d["mstr"].append(round(mstr, 2))
    d["held"].append(round(cs.btc_held, 0))
    d["shares"].append(round(cs.shares_basic / 1e6, 3))
    d["debt"].append(round(cs.debt_notional_usd / 1e9, 4))
    d["cash"].append(round(cs.cash_and_equiv_usd / 1e9, 4))
    d["pref_total"].append(round(cs.preferred_total_usd / 1e9, 4))

    mb = C.mnav(cs, btc, mstr, C.MNavVariant.BASIC).value
    mc = C.mnav(cs, btc, mstr, C.MNavVariant.CEBE).value
    cp = C.claims_pct(cs, btc, C.ClaimsBasis.CEBETRACKER, 0.0)
    d["mnav_basic"].append(round(mb, 5))
    d["mnav_cebe"].append(round(mc, 5))
    d["claims_pct"].append(round(cp, 6))
    d["bps"].append(round(cs.btc_held / cs.shares_basic * 1e8, 1))
    d["amp"].append(round(1 / (1 - cp), 4) if cp < 1 else None)
    d["days_stale_max"].append(max(stale.values()))
    # 「主要」staleness:只看真正牽動 mNAV 讀數的欄位(BTC、股數、debt、cash、STRC)。
    # STRF/STRK/STRD/STRE 各自只有 3 個錨點(IPO + 2026-06-30),個別很稀疏,
    # 但四個加總只佔優先股總額的 32%,拖累有限 —— 不該讓它們主導信心徽章的顯示,
    # 那樣會掩蓋 BTC 持有量這次改善(90 個週觀測點)帶來的實質進步。
    primary_keys = ["btc", "shares", "debt", "cash", "pref_STRC"]
    d["days_stale_primary"] = d.get("days_stale_primary", [])
    d["days_stale_primary"].append(max(stale.get(k, 0) for k in primary_keys))

    for t in I.PREFERRED_TICKERS:
        pref = next((p for p in cs.preferreds if p.ticker == t), None)
        shares = pref.shares if pref else 0.0
        lp = pref.liquidation_preference_usd if pref else 0.0
        price = pref_prices.get(t, {}).get(day.isoformat())
        d[f"{t.lower()}_shares"].append(round(shares / 1e6, 3) if shares else 0.0)
        d[f"{t.lower()}_lp"].append(round(lp / 1e9, 4) if lp else 0.0)
        d[f"{t.lower()}_price"].append(price)
        d[f"{t.lower()}_mktcap"].append(round(shares * price / 1e9, 4) if (price and shares) else None)

# ---- 錨點清單(給前端畫「這是真實觀測點」的標記) ----
anchors_out = {
    "btc_held": [[a[0].isoformat(), a[1]] for a in btc_a],
    "shares": [[a[0].isoformat(), a[1]] for a in shares_a],
    "debt": [[a[0].isoformat(), a[1]] for a in debt_a],
}
for t in I.PREFERRED_TICKERS:
    anchors_out[f"pref_{t}"] = [[a[0].isoformat(), a[1]] for a in pref_a[t]]

ipos = [{"t": i.ticker, "d": i.pricing_date.isoformat(), "lp": round(i.ipo_liquidation_pref/1e9,3),
        "rate": i.dividend_rate_pct, "rank": i.rank, "note": i.note, "cur": i.currency}
       for i in D.PREFERRED_IPOS]
breaks = [{"d": b.as_of.isoformat(), "title": b.title, "hard": b.breaks_timeseries}
          for b in D.POLICY_BREAKS]

fwp = D.fwp_snapshot()
fwp_out = {"held": D.PARAMS_2026_08_13["btc_held"], "btc": D.FWP_BTC_PRICE,
          "price": D.FWP_MSTR_PRICE, "fdso": D.PARAMS_2026_08_13["fdso"],
          "basic": fwp.shares_basic, "assumed": D.FWP_SHARES_ASSUMED_DILUTED,
          "debt": D.PARAMS_2026_08_13["debt_otm_notional"]/1e9,
          "pref": {k: round(v/1e9,4) for k,v in fwp.preferred_by_ticker.items()},
          "reserve": D.PARAMS_2026_08_13["usd_reserve"]/1e9}

sens = [{"btc": b, "off": o, "got": round(C.net_reserve_per_share(b, **D.PARAMS_2026_08_13), 4)}
        for b, o in D.FWP_SENSITIVITY_TABLE]
be = [{"k": k, "v": round(v, 0)} for k, v in sorted(
    C.break_even_all_bases(fwp, D.FWP_MSTR_PRICE).items(), key=lambda kv: kv[1])]

findings = [
   {"t": "§5.9 的 2026-07-05 求償權數字是錯的",
    "b": "同一列的 claims% 38.3%、BPS 227,057、CEBE 140,200 三個欄位彼此一致，但一致於 $19.63B 與 371.6M 股，不是標示的 ~$21,000M。"},
   {"t": "股數分母有三個，不是兩個",
    "b": "官方 Gross BPS 用 423.8M assumed diluted、Net BPS 用 398.2M FDSO。對照表的「basic 基準」用的是第三個：394.2M basic shares。"},
   {"t": "$543 是盤中高點，不是收盤價",
    "b": "2024-11-21 收盤為 $397.28（實測）。用收盤對收盤重算，壓縮幅度被高估約 37%。"},
   {"t": "2025-03-24 之後，週頻 BTC 持有量不再寫進 SEC 文件",
    "b": "Strategy 把逐週買幣數字從 8-K 正文移到官網 dashboard。免費資料源到此為止只剩季頻（SEC XBRL），本頁用線性插值補中間地帶，並在介面上標出離最近真實觀測點幾天。"},
   {"t": "STRC 的股數插值特別寬鳵",
    "b": "除了 IPO 日與兩個季末點，另外加入了 2026-07-24 回購後的段考點，共 5 個錨點；其餘四個優先股系列只有 3 個（IPO + 2026-06-30），中間進程是直線推估。"},
]

payload = {"daily": d, "anchors": anchors_out, "ipos": ipos, "breaks": breaks,
          "fwp": fwp_out, "sens": sens, "be": be, "findings": findings,
          "preferred_tickers": list(I.PREFERRED_TICKERS)}

out_path = "web/data.json"
json.dump(payload, open(out_path, "w"), ensure_ascii=False, separators=(",", ":"))
print(f"days: {len(dates)}  size: {os.path.getsize(out_path)//1024} KB")
print(f"max staleness in dataset: {max(d['days_stale_max'])} days")
print(f"median staleness: {sorted(d['days_stale_max'])[len(d['days_stale_max'])//2]} days")
