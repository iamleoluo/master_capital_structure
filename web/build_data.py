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
import math
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
# chronicle.json —— 資本結構大事記
#
# 階段的標題與敘述是人工撰寫的(mstr_cebe/chronicle.py),但每一個數字都在這裡
# 從 daily.json 與原始週資料重算。所以資料一更新,每一則的數字就跟著更新。
# ---------------------------------------------------------------------------

def _pair(series: list, lo: int, hi: int, nd: int = 0) -> dict:
    """期初 → 期末 + 變化率。變化率在期初為 0 時回 None,不硬算。"""
    a, b = float(series[lo]), float(series[hi])
    pct = ((b / a - 1) * 100) if a else None
    return {"from": round(a, nd), "to": round(b, nd),
            "pct": round(pct, 1) if pct is not None else None}


def _era_window(daily: dict, era) -> tuple:
    """回傳 (日線索引 lo, hi, 宣告起日, 宣告迄日)。

    ⚠️ 日線索引會被對齊到交易日,週資料**不能**用對齊後的日期去篩 ——
    宣告的迄日若落在週末(例如 2026-05-31),對齊後會變成 05-29,那一週的
    week_end=2026-05-31 就會同時被前後兩期排除、整週憑空消失。
    實測就是這樣讓「信用壓力」期的賣幣量變成 0 顆。週資料一律用宣告日期篩。
    """
    dates = daily["date"]
    start = era.start.isoformat()
    end = era.end.isoformat() if era.end else dates[-1]
    lo = next((i for i, d in enumerate(dates) if d >= start), 0)
    hi = max(lo, max((i for i, d in enumerate(dates) if d <= end), default=lo))
    return lo, hi, start, end


def _chain_increments(daily: dict) -> tuple:
    """逐日的(行情增量, 決策增量)。前綴和之後,任意區間都是 O(1) 查詢。

    每一天先讓幣價走(結構凍結)= 行情,再讓結構走(用當天幣價評價)= 決策。
    決策只用它當下能知道的價格評價,所以不含後見之明 ——
    這是與「兩端同代入期末幣價」最關鍵的差別。

    同時算兩種單位:
      sats  —— 給頭條用,「每股多拿到幾顆聰」是讀者直覺看得懂的
      對數  —— 給三層歸因用。股價恆等式取對數之後三層是相加的,
               每股含幣量那一層要再切成決策／行情,也必須在對數空間切,
               否則切出來的兩塊加起來不等於那一層本身。
    """
    from mstr_cebe import attribution as A      # noqa: E402

    n = len(daily["date"])
    mkt = [0.0] * n
    dec = [0.0] * n
    mktL = [0.0] * n
    decL = [0.0] * n
    for t in range(1, n):
        h0 = daily["held"][t - 1]
        c0 = (daily["debt"][t - 1] + daily["pref_total"][t - 1]
              - daily["cash"][t - 1]) * 1e9
        s0 = daily["shares"][t - 1] * 1e6
        p0 = daily["btc"][t - 1]
        h1 = daily["held"][t]
        c1 = (daily["debt"][t] + daily["pref_total"][t]
              - daily["cash"][t]) * 1e9
        s1 = daily["shares"][t] * 1e6
        p1 = daily["btc"][t]
        before = A.cebe_sats(h0, c0, p0, s0)
        moved = A.cebe_sats(h0, c0, p1, s0)     # 只有幣價動
        after = A.cebe_sats(h1, c1, p1, s1)     # 結構再動,用今天的 p1
        mkt[t] = moved - before
        dec[t] = after - moved
        # 實測每股含幣量最低也有 8.3 萬 sats,離零很遠,取對數是安全的;
        # 真的碰到非正值就讓那一天不貢獻,寧可對不起來被下面的斷言抓到
        if before > 0 and moved > 0 and after > 0:
            mktL[t] = math.log(moved) - math.log(before)
            decL[t] = math.log(after) - math.log(moved)

    # 前綴和:區間 (lo, hi] 的貢獻 = pre[hi] - pre[lo]
    pm, pd = [0.0] * n, [0.0] * n
    pmL, pdL = [0.0] * n, [0.0] * n
    for t in range(1, n):
        pm[t] = pm[t - 1] + mkt[t]
        pd[t] = pd[t - 1] + dec[t]
        pmL[t] = pmL[t - 1] + mktL[t]
        pdL[t] = pdL[t - 1] + decL[t]
    return pm, pd, pmL, pdL


def _layers4(daily: dict, pmL: list, pdL: list, lo: int, hi: int) -> dict:
    """四層對數歸因。四項相加 = ln(MSTR 報酬比),沒有殘差。

    前三層直接來自股價恆等式 P = m × E/1e8 × p 取對數;
    中間的 E 再用逐日鏈結切成「公司決策」與「求償權縮放」。
    """
    out = {
        "btc": math.log(daily["btc"][hi] / daily["btc"][lo]),
        "decision": pdL[hi] - pdL[lo],
        "claims": pmL[hi] - pmL[lo],
        "mnav": math.log(daily["mnav_cebe"][hi] / daily["mnav_cebe"][lo]),
    }
    # 恆等式查核:恆等式本身已驗到 0.019bp,這裡的門檻放在 5e-4(≈0.05%)
    actual = math.log(daily["mstr"][hi] / daily["mstr"][lo])
    gap = abs(sum(out.values()) - actual)
    assert gap < 5e-4, (f"{daily['date'][lo]}→{daily['date'][hi]} "
                        f"四層加總對不上 MSTR 報酬:{gap}")
    return {k: round(v, 4) for k, v in out.items()}


def build_chronicle(daily: dict, weekly: list) -> list:
    from mstr_cebe import chronicle as CH      # noqa: E402

    atm = _load_raw("atm_weekly.json")
    rep = (_load_raw("repurchase_weekly.json")
           if os.path.exists(os.path.join(RAW, "repurchase_weekly.json")) else [])
    pref_px = _load_raw("preferred_prices.json")

    pm, pd, pmL, pdL = _chain_increments(daily)
    claims = [round(daily["debt"][i] + daily["pref_total"][i] - daily["cash"][i], 4)
              for i in range(len(daily["date"]))]
    cebe = [round(daily["common_btc"][i] / (daily["shares"][i] * 1e6) * 1e8, 1)
            for i in range(len(daily["date"]))]

    out = []
    for era in CH.ERAS:
        lo, hi, wa, wb = _era_window(daily, era)
        a, b = daily["date"][lo], daily["date"][hi]

        # 週資料用宣告日期(wa/wb),不是對齊後的交易日(a/b)—— 見 _era_window
        in_window = [w for w in weekly if wa <= w["week_end"] <= wb]
        atm_w = [x for x in atm if wa <= x["week_end"] <= wb]
        rep_w = [x for x in rep if wa <= x["week_end"] <= wb]

        pref_raised = sum((v.get("net_proceeds_m") or 0.0)
                          for x in atm_w for s, v in x["by_security"].items()
                          if s != "MSTR")
        common_raised = sum((x["by_security"].get("MSTR", {}).get("net_proceeds_m") or 0.0)
                            for x in atm_w)
        rep_shares = sum(v.get("shares", 0.0) for x in rep_w
                         for s, v in x["by_security"].items() if s != "MSTR")
        rep_cost = sum(v.get("cost_m", 0.0) for x in rep_w
                       for s, v in x["by_security"].items() if s != "MSTR")
        common_rep = sum(x["by_security"].get("MSTR", {}).get("shares", 0.0)
                         for x in rep_w)
        bought = sum(w["delta"] for w in in_window if (w["delta"] or 0) > 0)
        sold = -sum(w["delta"] for w in in_window if (w["delta"] or 0) < 0)

        # 工具是否真的動用,一律由資料判定,不採信 chronicle.py 的人工標註
        debt_delta = daily["debt"][hi] - daily["debt"][lo]
        active = {
            "common_atm": common_raised > 0,
            "preferred_issue": pref_raised > 0,
            "convert_issue": debt_delta > 0.05,
            "btc_sale": sold > 0,
            "preferred_buyback": rep_shares > 0,
            "common_buyback": common_rep > 0,
            "convert_buyback": debt_delta < -0.05,
        }

        strc = sorted((d, v) for d, v in pref_px.get("STRC", {}).items() if wa <= d <= wb)

        out.append({
            "id": era.id, "title": era.title, "subtitle": era.subtitle,
            "start": a, "end": None if era.end is None else b,
            "ongoing": era.end is None,
            "trigger": era.trigger, "body": list(era.body), "watch": era.watch,
            "range": [lo, hi],
            # 日曆天,不是交易日 —— 讀者看日期區間時預期的是日曆天
            "days": (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days + 1,
            "tools": list(era.tools),
            "toolsActive": [k for k, v in active.items() if v],
            "metrics": {
                "btcPrice": _pair(daily["btc"], lo, hi),
                "held": _pair(daily["held"], lo, hi),
                "claims": _pair(claims, lo, hi, 2),
                "pref": _pair(daily["pref_total"], lo, hi, 2),
                "shares": _pair(daily["shares"], lo, hi, 1),
                "cebe": _pair(cebe, lo, hi),
                "grossBps": _pair(daily["bps"], lo, hi),
                "mnavCebe": _pair(daily["mnav_cebe"], lo, hi, 2),
                "mstrPrice": _pair(daily["mstr"], lo, hi, 2),
                "strcPrice": ({"from": strc[0][1], "to": strc[-1][1],
                               "pct": round((strc[-1][1] / strc[0][1] - 1) * 100, 1),
                               "low": min(v for _, v in strc),
                               "lowDate": min(strc, key=lambda x: x[1])[0]}
                              if len(strc) > 1 else None),
            },
            # 逐日鏈結:每天先讓幣價動(行情)、再讓結構動並以當天幣價評價(決策)。
            # 兩者相加精確等於實現變化,且決策不含後見之明。
            "split": {"market": round(pm[hi] - pm[lo]),
                      "decision": round(pd[hi] - pd[lo])},
            # 與績效歸因頁同一個口徑的四層拆解
            "layers4": _layers4(daily, pmL, pdL, lo, hi),
            "flows": {
                "prefRaisedM": round(pref_raised, 1),
                "commonRaisedM": round(common_raised, 1),
                "prefRepurchasedShares": round(rep_shares),
                "prefRepurchasedM": round(rep_cost, 1),
                "btcBought": round(bought), "btcSold": round(sold),
            },
            "events": (
                [{"d": x.as_of.isoformat(), "label": x.title, "kind": "policy"}
                 for x in D.POLICY_BREAKS if a <= x.as_of.isoformat() <= b]
                + [{"d": i.pricing_date.isoformat(),
                    "label": f"{i.ticker} 上市(${i.ipo_liquidation_pref / 1e9:.2f}B)",
                    "kind": "ipo"}
                   for i in D.PREFERRED_IPOS if a <= i.pricing_date.isoformat() <= b]
            ),
        })

    # 最新一期的回購剩餘授權(前瞻數字,寫死在文案裡會過時)
    if rep and out:
        last_auth = next((x.get("remaining_authority_m") for x in reversed(rep)
                          if x.get("remaining_authority_m")), None)
        if last_auth:
            out[-1]["remainingAuthorityM"] = last_auth

    return out


def build_toolkit() -> list:
    from mstr_cebe import chronicle as CH      # noqa: E402
    return [{"id": t.id, "label": t.label, "claims": t.claims, "shares": t.shares,
             "btc": t.btc, "cebe": t.cebe, "note": t.note} for t in CH.TOOLS]


def build_strategy(daily: dict, weekly: list, chronicle: list) -> dict:
    """策略歸因 —— 對<b>每一個</b>可能的起始日都算好,讓前端能任意拉動起點。

    全部在這裡算完的理由跟其他頁一樣:前端不做金融計算。Shapley 與對數拆解
    有 tests/test_attribution.py 守著加總恆等,不該在 TS 裡重寫一份。

    payload 是 1-D 的(終點恆為最新一天),四捨五入後約數十 KB,可以接受。
    """
    from mstr_cebe import attribution as A      # noqa: E402

    n = len(daily["date"])
    end = n - 1

    def st(i):
        return {
            "held": float(daily["held"][i]),
            "claims": (daily["debt"][i] + daily["pref_total"][i]
                       - daily["cash"][i]) * 1e9,
            "price": float(daily["btc"][i]),
            "shares": daily["shares"][i] * 1e6,
        }

    end_st = st(end)
    end_cebe = A.cebe_of(end_st)
    pm, pd, pmL, pdL = _chain_increments(daily)

    atm = _load_raw("atm_weekly.json")
    rep = (_load_raw("repurchase_weekly.json")
           if os.path.exists(os.path.join(RAW, "repurchase_weekly.json")) else [])
    end_date = daily["date"][end]

    def ops_for(i):
        """把區間內的資金流組成操作表。四因子拆的是會計結果,這裡拆的是決策。"""
        a = daily["date"][i]
        rows_w = [w for w in weekly if a <= w["week_end"] <= end_date]
        raised = sum((x["by_security"].get("MSTR", {}).get("net_proceeds_m") or 0.0)
                     for x in atm if a <= x["week_end"] <= end_date) * 1e6
        discount = sum(v.get("shares", 0.0) * 100 - v.get("cost_m", 0.0) * 1e6
                       for x in rep if a <= x["week_end"] <= end_date
                       for sec, v in x["by_security"].items() if sec != "MSTR")
        rep_par = sum(v.get("shares", 0.0) * 100
                      for x in rep if a <= x["week_end"] <= end_date
                      for sec, v in x["by_security"].items() if sec != "MSTR")
        pref_proceeds = sum(
            (v.get("net_proceeds_m") or 0.0)
            for x in atm if a <= x["week_end"] <= end_date
            for sec, v in x["by_security"].items() if sec != "MSTR") * 1e6
        # 期間新掛上的清算優先權 = 餘額變動 + 這段期間被回購掉的面額
        pref_par_issued = ((daily["pref_total"][end] - daily["pref_total"][i]) * 1e9
                           + rep_par)
        d_debt = (daily["debt"][end] - daily["debt"][i]) * 1e9
        days = (dt.date.fromisoformat(end_date) - dt.date.fromisoformat(a)).days
        obligations = D.FWP_2026_08_24_ANNUAL_OBLIGATIONS * max(days, 0) / 365
        bought = sum((w["delta"] or 0) * (w["avg_price"] or 0)
                     for w in rows_w if (w["delta"] or 0) > 0)
        sold = sum(-(w["delta"] or 0) * (w["avg_price"] or 0)
                   for w in rows_w if (w["delta"] or 0) < 0)
        s0 = st(i)
        modeled = (s0["claims"] - raised - discount + obligations + bought - sold
                   + (pref_par_issued - pref_proceeds) + d_debt)
        return A.build_operations(
            raised=raised, discount=discount, obligations=obligations,
            btc_bought_usd=bought, btc_sold_usd=sold,
            d_held=end_st["held"] - s0["held"],
            d_shares=end_st["shares"] - s0["shares"],
            end_price=end_st["price"],
            residual=end_st["claims"] - modeled,
            pref_par_issued=pref_par_issued, pref_proceeds=pref_proceeds,
            d_debt=d_debt,
        ), {"raisedM": raised / 1e6, "discountM": discount / 1e6,
            "carryM": obligations / 1e6, "prefParM": pref_par_issued / 1e6,
            "prefProceedsM": pref_proceeds / 1e6, "debtM": d_debt / 1e6,
            "residualM": (end_st["claims"] - modeled) / 1e6}

    rows = []
    for i in range(end + 1):
        a = st(i)
        try:
            c0 = A.cebe_of(a)
        except ValueError:
            rows.append(None)
            continue
        layers = A.price_layers(
            daily["mnav_cebe"][i], c0, daily["btc"][i],
            daily["mnav_cebe"][end], end_cebe, daily["btc"][end])
        flows = A.flows_between(weekly, daily["date"][i], daily["date"][end])
        ops, opMeta = ops_for(i)
        op_parts = A.shapley_operations(a, ops)

        # 恆等式:決策 + 行情 = 每股含幣量那一層的對數變化。差到 1e-7 就是有 bug
        gap = abs((pmL[end] - pmL[i]) + (pdL[end] - pdL[i]) - layers["cebe"])
        assert gap < 1e-7, f"{daily['date'][i]} 對數鏈結對不上 layers.cebe:{gap}"

        rows.append({
            "cebe0": round(c0),
            # 三層價格歸因:存對數變化量。前端把 cebe 那層再用 splitLog 切成兩半,
            # 佔比也由前端算(純算術,不是金融計算)
            "layers": {k: round(v, 4) for k, v in layers.items()},
            "mstrRet": round((daily["mstr"][end] / daily["mstr"][i] - 1) * 100, 1),
            "btcRet": round((daily["btc"][end] / daily["btc"][i] - 1) * 100, 1),
            "bought": round(flows["btcBought"]), "sold": round(flows["btcSold"]),
            # 操作層級:各項加總 = ΔCEBE。這才對應真實決策。
            # 但它依賴完整的資金流揭露(ATM 表、回購表、USD Reserve),
            # 2026-06 之前 8-K 沒有這些欄位,對不起來的部分會全部擠進殘差 ——
            # 殘差大於總變化的四分之一時就不該拿來下結論,用 opsOk 標記。
            "ops": {k: round(v) for k, v in op_parts.items()},
            "opMeta": {k: round(v) for k, v in opMeta.items()},
            # Gross BPS(公司的 BTC Yield):公式裡沒有幣價,天生不受幣價污染
            "split": {"market": round(pm[end] - pm[i]),
                      "decision": round(pd[end] - pd[i])},
            # 同一個拆解,但在對數空間 —— 三層歸因要把「每股含幣量」那一層
            # 再切成決策／行情時用這個,兩塊相加恰好等於 layers["cebe"]
            "splitLog": {"market": round(pmL[end] - pmL[i], 4),
                         "decision": round(pdL[end] - pdL[i], 4)},
            "bps0": round(daily["bps"][i], 1),
            "opsOk": bool(abs(op_parts.get("other", 0.0))
                          <= 0.25 * max(abs(end_cebe - c0), 1.0)),
        })

    return {
        "end": daily["date"][end],
        "cebeNow": round(end_cebe),      # 所有列共用的終點,不必每列重複
        "bpsNow": round(daily["bps"][end], 1),
        "priceNow": daily["btc"][end],
        "rows": rows,
        # 預設起點候選:各階段起點 + 第一次賣幣
        "presets": (
            [{"id": e["id"], "label": e["title"], "date": e["start"]}
             for e in chronicle]
            + [{"id": "first-sale", "label": "第一次賣幣", "date": "2026-05-31"}]
        ),
    }


def build_program(daily: dict, weekly: list) -> dict:
    """大事記最上面的整體框架:長期論述 + 全期數字。

    全期數字存在的理由是擋住「用三五個月論斷這套結構」——
    單一階段永遠只是這台機器的某一個轉速。
    """
    from mstr_cebe import chronicle as CH      # noqa: E402

    n = len(daily["date"])
    lo, hi = 0, n - 1
    cebe = [daily["common_btc"][i] / (daily["shares"][i] * 1e6) * 1e8
            for i in range(n)]
    claims = [daily["debt"][i] + daily["pref_total"][i] - daily["cash"][i]
              for i in range(n)]

    sold = sum(-w["delta"] for w in weekly if (w["delta"] or 0) < 0)
    bought = sum(w["delta"] for w in weekly if (w["delta"] or 0) > 0)

    pm, pd, pmL, pdL = _chain_increments(daily)

    return {
        "lede": CH.PROGRAM.lede,
        "split": {"market": round(pm[hi] - pm[lo]),
                  "decision": round(pd[hi] - pd[lo])},
        "layers4": _layers4(daily, pmL, pdL, lo, hi),
        "principles": [{"t": t, "b": b} for t, b in CH.PROGRAM.principles],
        "span": [daily["date"][lo], daily["date"][hi]],
        "metrics": {
            "cebe": _pair(cebe, lo, hi),
            "held": _pair(daily["held"], lo, hi),
            "btcPrice": _pair(daily["btc"], lo, hi),
            "mstrPrice": _pair(daily["mstr"], lo, hi, 2),
            "claims": _pair(claims, lo, hi, 2),
        },
        # 「賣幣求生」這個說法能不能成立,就看這兩個數字
        "btcSoldEver": round(sold),
        "btcBoughtEver": round(bought),
        "soldPctOfHoldings": round(sold / daily["held"][hi] * 100, 2),
        "reserveYears": round(D.PARAMS_2026_08_24["usd_reserve"]
                              / D.FWP_2026_08_24_ANNUAL_OBLIGATIONS, 1),
    }


# ---------------------------------------------------------------------------
# meta.json
# ---------------------------------------------------------------------------

def build_meta() -> dict:
    # 前端顯示的官方錨點一律用**最新一份** FWP(2026-08-24)。
    # 舊的 08-13 那份留在 data.py 與 tests/ 裡當回歸錨點,不對外顯示 ——
    # 兩份的口徑不同(優先股 notional、股數、USD 加回項都變了),混用會出錯。
    fwp = D.fwp_snapshot_2026_08_24()
    p = D.PARAMS_2026_08_24
    btc_px, mstr_px = D.FWP_2026_08_24_BTC_PRICE, D.FWP_2026_08_24_MSTR_PRICE
    return {
        "ipos": [{"t": i.ticker, "name": i.name, "d": i.pricing_date.isoformat(),
                  "lp": round(i.ipo_liquidation_pref / 1e9, 3), "rate": i.dividend_rate_pct,
                  "rank": i.rank, "note": i.note, "cur": i.currency}
                 for i in D.PREFERRED_IPOS],
        "breaks": [{"d": b.as_of.isoformat(), "title": b.title,
                    "detail": b.detail, "hard": b.breaks_timeseries}
                   for b in D.POLICY_BREAKS],
        "fwp": {
            "held": p["btc_held"], "btc": btc_px, "price": mstr_px,
            "fdso": p["fdso"], "basic": fwp.shares_basic,
            "assumed": D.FWP_2026_08_24_SHARES_ASSUMED_DILUTED,
            "debt": p["debt_otm_notional"] / 1e9,
            "reserve": p["usd_reserve"] / 1e9,
            "pref": {k: round(v / 1e9, 4) for k, v in fwp.preferred_by_ticker.items()},
            "gross_bps": round(C.gross_bps_sats(fwp.btc_held, fwp.shares_assumed_diluted)),
            "net_bps": round(C.net_bps_sats(
                C.net_reserve_per_share_from(fwp, btc_px, mstr_px), btc_px)),
            "date": "2026-08-24",
        },
        "sens": [{"btc": b, "off": o,
                  "got": round(C.net_reserve_per_share(b, **p), 4)}
                 for b, o in D.FWP_2026_08_24_SENSITIVITY_TABLE],
        "be": [{"k": k, "v": round(v)} for k, v in sorted(
            C.break_even_all_bases(fwp, mstr_px).items(),
            key=lambda kv: kv[1])],
        "anchors": {
            "btc_held": [[a[0].isoformat(), a[1]] for a in I.btc_held_anchors()],
            "shares": [[a[0].isoformat(), a[1]] for a in I.shares_basic_anchors()],
            "debt": [[a[0].isoformat(), a[1]] for a in I.debt_anchors()],
        },
        "findings": _findings(),
    }


def _findings() -> list:
    """資料品質頁的 findings。數字一律從實際資料算,避免寫死之後悄悄過時。"""
    holdings = _load_raw("btc_holdings_weekly.json")
    days = [dt.date.fromisoformat(d) for d, _ in holdings]
    gaps = [(days[i + 1] - days[i]).days for i in range(len(days) - 1)]

    # 口徑與前端 accumulationStats() 一致:分母只算真的有進出幣的週次,
    # 分子看 funding 欄位本身(明示 vs 由 ATM 表推得),不看 source_kind ——
    # source_kind 會把「賣幣週」獨立成一類,即使那一週其實有指名資金來源。
    weekly = build_weekly()
    act = [w for w in weekly if w["delta"]]
    stated = [w for w in act if w["funding"] and not w["funding_derived"]]
    derived = [w for w in act if w["funding"] and w["funding_derived"]]
    uncovered = len(act) - len(stated) - len(derived)
    named_pct = len(stated) / len(act) * 100
    covered_pct = (len(stated) + len(derived)) / len(act) * 100

    rep = _load_raw("repurchase_weekly.json") if os.path.exists(
        os.path.join(RAW, "repurchase_weekly.json")) else []
    rep_sh = sum(r["by_security"].get("STRC", {}).get("shares", 0.0) for r in rep)
    rep_cost = sum(r["by_security"].get("STRC", {}).get("cost_m", 0.0) for r in rep)

    p = D.PARAMS_2026_08_24
    assumed = D.FWP_2026_08_24_SHARES_ASSUMED_DILUTED
    basic = D.fwp_snapshot_2026_08_24().shares_basic

    return [
        {"t": "公司已經從「發優先股」轉成「買回優先股」",
         "b": f"2026-07-27 起 8-K 多出一張 Shares Repurchased 表,2026-09-08 起原本的 "
              f"ATM Program Summary 表整張消失。至今已回購 STRC {rep_sh:,.0f} 股、"
              f"成本 ${rep_cost/1000:.2f}B,均價 ${rep_cost*1e6/rep_sh:.2f}(低於 $100 面額"
              f"{(1 - rep_cost*1e6/rep_sh/100)*100:.1f}%)。折價買回會永久消滅清算優先權,"
              f"是少數會讓 CEBE 真正上升的動作 —— 不納入模型的話求償權會被高估約 "
              f"${rep_sh*100/1e9:.2f}B。"},
        {"t": "BTC 持有量其實每週都在 8-K 裡,只是換了格式",
         "b": f"早期是 prose 敘述,2025-03-31 之後改成「BTC Update」表格,2026-08 又出現"
              f"「BTC Purchased /(Sold)」買賣合併欄(正負號要看括號,不能看表頭字樣)。"
              f"單一關鍵字搜尋會漏掉格式切換,導致誤判為「公司不再揭露」。目前解出 "
              f"{len(holdings)} 個真實週觀測點,平均間隔 {sum(gaps)/len(gaps):.1f} 天。"},
        {"t": "股數分母有三個,不是兩個",
         "b": f"官方 Gross BPS 用 {assumed/1e6:.1f}M assumed diluted、Net BPS 用 "
              f"{p['fdso']/1e6:.1f}M FDSO,而本站圖表的「basic 基準」用的是第三個:"
              f"{basic/1e6:.1f}M basic shares,assumed 比 basic 多 "
              f"{(assumed/basic-1)*100:.0f}%。三者不可混用。"},
        {"t": "§5.9 的 2026-07-05 求償權數字自相矛盾",
         "b": "同列的 claims% 38.3%、BPS 227,057、CEBE 140,200 三者一致於 $19.63B 與 "
              "371.6M 股,不是標示的 ~$21,000M。採用 $19.63B。"},
        {"t": "$543 是盤中高點,不是收盤價",
         "b": "2024-11-21 收盤為 $397.28。用盤中高點對收盤價比較,會把壓縮幅度誇大約 37%。"},
        {"t": "融資來源:明示與推得要分開看",
         "b": f"{len(act)} 個有買賣的週次中,{len(stated)} 週在 8-K 敘述句明確寫出動用了"
              f"哪些 ATM({named_pct:.0f}%)。其餘只寫「under the ATM」,但同一份文件的 ATM "
              f"表格已逐券種列出當週淨募資,有錢進來的券種即為資金來源 —— 這樣可再補 "
              f"{len(derived)} 週,涵蓋率提升到 {covered_pct:.0f}%。表格中以「推得」標記,"
              f"與敘述句明示者區分。仍有 {uncovered} 週兩種來源都沒有資料。"},
        {"t": "優先股股數已是逐週,但尾段是外推",
         "b": "STRF/STRC/STRK/STRD 用 ATM 表的逐週賣股數當形狀、再用已知季末股數校正,"
              "解析度從 3-5 個季度錨點提升到每週一點。但最後一個已知精確股數"
              "(STRC 為 2026-07-24)之後沒有可對齊的申報值,只能用逐週發行減回購外推;"
              "STRE 沒有 ATM,維持單點。"},
    ]


# ---------------------------------------------------------------------------
# 變化偵測 —— 讓「每次更新都重新檢視結構」有實際機制,而不是靠人記得
# ---------------------------------------------------------------------------

def structural_watch(daily: dict, chronicle: list) -> list:
    """比對目前狀態與當前階段的起點,回報值得注意的結構變化。

    這不是自動開新主題(那是編輯判斷),而是提醒維護者「可能該開新主題了」。
    """
    notes = []
    if not chronicle:
        return notes
    cur = chronicle[-1]
    lo, hi = cur["range"]
    dates = daily["date"]

    m = cur["metrics"]
    if m["claims"]["pct"] is not None and abs(m["claims"]["pct"]) >= 5:
        notes.append(
            f"本期({cur['title']})淨求償權已變動 {m['claims']['pct']:+.1f}%"
            f"(${m['claims']['from']:.2f}B → ${m['claims']['to']:.2f}B)")

    # 優先股價格穿越面額:信用狀況換檔的訊號
    pref_px = _load_raw("preferred_prices.json")
    for t, series in pref_px.items():
        win = sorted((d, v) for d, v in series.items()
                     if dates[lo] <= d <= dates[hi])
        if len(win) < 2:
            continue
        below = [d for d, v in win if v < 100]
        above = [d for d, v in win if v >= 100]
        if below and above:
            notes.append(
                f"{t} 在本期內穿越面額($100):最低 ${min(v for _, v in win):.2f}、"
                f"最新 ${win[-1][1]:.2f}")

    # 最後一期還開著、而且已經跑了很久 —— 提醒重新檢視分期是否還成立
    if cur["ongoing"] and cur["days"] > 180:
        notes.append(
            f"本期已持續 {cur['days']} 天,值得重新檢視是否該切出新階段")

    # 工具箱的啟用組合與人工標註不一致
    declared, actual = set(cur["tools"]), set(cur["toolsActive"])
    if declared - actual:
        notes.append(f"chronicle.py 標註了但資料上沒有動作的工具:"
                     f"{', '.join(sorted(declared - actual))}")
    if actual - declared:
        notes.append(f"資料上有動作但 chronicle.py 沒標註的工具:"
                     f"{', '.join(sorted(actual - declared))}")

    return notes


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    daily, weekly, meta = build_daily(), build_weekly(), build_meta()
    chronicle = build_chronicle(daily, weekly)
    meta["toolkit"] = build_toolkit()
    meta["program"] = build_program(daily, weekly)
    strategy = build_strategy(daily, weekly, chronicle)
    meta["watch"] = structural_watch(daily, chronicle)

    for name, payload in (("daily", daily), ("weekly", weekly),
                          ("meta", meta), ("chronicle", chronicle),
                          ("strategy", strategy)):
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

    print(f"\n大事記: {len(chronicle)} 個階段")
    for e in chronicle:
        m = e["metrics"]
        tail = "進行中" if e["ongoing"] else e["end"]
        print(f"  {e['start']} → {tail:<12} {e['title']:<8} "
              f"持幣 {m['held']['pct']:+6.1f}%  求償權 {m['claims']['pct']:+6.1f}%  "
              f"CEBE {m['cebe']['pct']:+6.1f}%")

    if meta["watch"]:
        print("\n⚠️  結構變化提醒(考慮是否該開新主題):")
        for w in meta["watch"]:
            print(f"  • {w}")

    # 黃金測試:管線不能悄悄改掉官方錨點。兩份 FWP 都釘住 ——
    # 舊的那份是歷史回歸基準,新的那份是前端實際顯示的口徑。
    old = C.net_reserve_per_share(D.FWP_BTC_PRICE, **D.PARAMS_2026_08_13)
    assert abs(old - 92.11) < 0.02, f"2026-08-13 FWP 每股淨值回歸: {old}"
    print(f"\n✓ 黃金錨點(2026-08-13)BTC ${D.FWP_BTC_PRICE:,.0f} → ${old:.4f}/股(官方 $92.11)")

    new = C.net_reserve_per_share(D.FWP_2026_08_24_BTC_PRICE, **D.PARAMS_2026_08_24)
    assert abs(new - 118.31) < 0.02, f"2026-08-24 FWP 每股淨值回歸: {new}"
    print(f"✓ 黃金錨點(2026-08-24)BTC ${D.FWP_2026_08_24_BTC_PRICE:,.0f} → "
          f"${new:.4f}/股(官方 $118.31)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
