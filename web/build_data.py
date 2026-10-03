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
from mstr_cebe import events as EV       # noqa: E402
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
            # 出處:這一週的數字來自哪一份 8-K(EDGAR accession)。
            # 沒有 a 的週次(只有持有量觀測)就沒有,前端顯示為純文字。
            "acc": a.get("acc"),
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
    """工具箱 —— **單一來源是 toolbox**(公式解那一欄的實作)。

    曾經有兩份平行清單:chronicle.TOOLS(7 把,把「發優先股募資去買幣」
    算成一把)與 toolbox.TOOLS(原子動作),ID 幾乎不重疊。網站顯示前者、
    代數與測試在後者 —— 同一個系統對外講的工具跟內部驗的工具不是同一組。

    現在只有 toolbox:**9 把原子工具 + 4 個組合**,分別對應講義的 L2 與 L3。
    ↑↓— 由 moves 推(toolbox.arrows),不手寫 —— 手寫就會與 apply 漂開。
    """
    from mstr_cebe import toolbox as TB         # noqa: E402

    def row(t, kind: str) -> dict:
        a = TB.arrows(TB.net_delta(t))
        return {"id": t.id, "label": t.label, "kind": kind,
                "claims": a["claims"], "shares": a["shares"], "btc": a["btc"],
                "cebe": t.verdict, "note": t.note,
                "bps": t.latex_b, "eq": t.latex_e,
                "moves": list(t.path or t.moves)}

    return ([row(t, "atom") for t in TB.TOOLS]
            + [row(c, "combo") for c in TB.COMBOS])


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

    end_date = daily["date"][end]
    # L2:資金流由事件的週聚合視圖算出來,不再讀 web/raw/*.json。
    # 這樣歸因的每一個參數都能沿著 事件 → 文件 追回出處。
    ev = EV.connect()

    def ops_for(i):
        """把區間內的資金流組成操作表。四因子拆的是會計結果,這裡拆的是決策。"""
        a = daily["date"][i]
        f = EV.flows_between(ev, a, end_date)
        raised = f["common_raised"]
        discount = f["repurchase_discount"]
        pref_proceeds = f["pref_proceeds"]
        # 期間新掛上的清算優先權 = 餘額變動 + 這段期間被回購掉的面額
        pref_par_issued = ((daily["pref_total"][end] - daily["pref_total"][i]) * 1e9
                           + f["repurchase_par"])
        d_debt = (daily["debt"][end] - daily["debt"][i]) * 1e9
        days = (dt.date.fromisoformat(end_date) - dt.date.fromisoformat(a)).days
        obligations = D.FWP_2026_08_24_ANNUAL_OBLIGATIONS * max(days, 0) / 365
        bought = f["btc_bought_usd"]
        sold = f["btc_sold_usd"]
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
            # ΔB 的兩因子拆解(sats／股)。B = H/S 沒有幣價項也沒有求償權項,
            # 所以它是「不受行情污染」的那一把尺 —— 前端拿來與 ops 並排,
            # 讓同一筆操作對兩個指標的效果可以橫著比。
            "bpsOps": {k: round(v) for k, v in A.gross_bps_ops(
                daily["held"][i], daily["shares"][i] * 1e6,
                daily["held"][end], daily["shares"][end] * 1e6).items()},
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

def build_operations_feed(daily: dict) -> list:
    """L3 的具名資本操作 —— 儀表板「工具」與「配對」兩頁的素材。

    這是**數值解**那一欄的 L2/L3:公式解講「ATM 增發在 m > 1 時加分」,
    這裡講「2026-09-27 那一週實際增發了多少、當時的 m 讓它加分還是減分」。

    ΔB / ΔE 一律由 `toolbox.effect()` 算,參數的翻譯收在
    `operations.tool_params()` —— 否則「網站顯示的效果」與「測試驗的效果」
    會各自漂開,而那正是 CLAUDE.md 第一條規則在防的事。
    """
    from mstr_cebe import operations as O          # noqa: E402
    from mstr_cebe import toolbox as T             # noqa: E402

    conn = O.connect()
    try:
        O.rebuild(conn)
        ops = O.build(conn)
        acc = {r[0]: r[1] for r in conn.execute(
            "SELECT doc_id, accession FROM documents WHERE accession <> ''")}
        doc_of = {r[0]: r[1] for r in conn.execute(
            "SELECT event_id, doc_id FROM events")}

        idx = {d: i for i, d in enumerate(daily["date"])}

        def state_at(day: str) -> T.State:
            i = idx.get(day)
            if i is None:
                i = next((j for j, d in enumerate(daily["date"]) if d >= day),
                         len(daily["date"]) - 1)
            return T.State(
                held=daily["held"][i],
                claims=(daily["debt"][i] + daily["pref_total"][i]
                        - daily["cash"][i]) * 1e9,
                shares=daily["shares"][i] * 1e6,
                price=daily["btc"][i])

        out = []
        for op in sorted(ops, key=lambda o: (o.window_hi, o.combo_id)):
            eff = O.effect_of(op, state_at(op.window_hi), conn)
            accs = sorted({acc[doc_of[e]] for e, _, _ in op.members
                           if doc_of.get(e) in acc})
            out.append({
                "id": op.op_id,
                "tool": op.combo_id,
                "kind": "combo" if op.combo_id in {c.id for c in T.COMBOS}
                        else "atom",
                "lo": op.window_lo, "hi": op.window_hi,
                # 組合操作的參數是 (n, P) / (c, F) 這種代數形狀,沒有 usd 欄位 ——
                # 金額從證據裡取,否則前端會顯示一排空白
                "qty": op.params.get("qty"),
                "usd": (op.params.get("usd")
                        or op.evidence.get("sources_total_usd")
                        or op.evidence.get("stated_usd")),
                "dB": round(eff["dB"], 2) if eff else None,
                "dE": round(eff["dE"], 2) if eff else None,
                # None = 這把工具結構上恆中性,不是「算不出來」
                "accretive": eff["accretive"] if eff else None,
                "rule": op.rule, "conf": op.confidence,
                "quote": op.evidence.get("quoted"),
                "acc": accs,
            })
    finally:
        conn.close()
    return out


def build_posts(daily: dict, chronicle: list, meta: dict) -> list:
    """觀點 —— 大事記(事件)與資本結構(主張)。

    markdown 在**建置期**轉成 HTML,與 reference/ 共用同一個轉換器
    (`mstr_cebe.md`),所以同一段文字在講義與文章裡長得一樣。

    `pins` 的現值也在這裡查:文章釘住寫作當下的數字,資料層給今天的 ——
    兩個並排,就看得到一個觀點寫下時的世界與它後來變成什麼。
    """
    from mstr_cebe import posts as P            # noqa: E402

    return P.to_json(P.load_all(
        {"daily": daily, "chronicle": chronicle, "meta": meta}))


def build_formulas() -> dict:
    """**公式解**那一欄的資料檔 —— `app/data/formulas.json`。

    講義只准吃這一份。裡面沒有任何觀測值:位置、工具、組合、各自的代數
    與判準,全部來自 `toolbox`(公式解的實作),改了幣價也不會變一個字。

    與 `meta.toolkit` 同源(`build_toolkit()`),但分成兩個檔案是刻意的 ——
    `meta.json` 裡有大量數值(錨點、findings、敏感度表),讓講義 import 它
    就等於把數值解的大門開著。見 CLAUDE.md 的「公式解 vs 數值解」。
    """
    from mstr_cebe import toolbox as TB         # noqa: E402

    return {
        "places": [{"id": k, "label": v} for k, v in TB.PLACES.items()],
        "assets": list(TB.ASSET_PLACES),
        "sources": list(TB.SOURCE_PLACES),
        "tools": build_toolkit(),
    }


def build_provenance(daily: dict, chronicle: list) -> dict:
    """出處、粒度、資金對帳 —— 資料品質頁的三個新區塊。

    全部從 L1 檔案庫與 L2 事件現算。寫死的話,下一次資料更新就會悄悄過時,
    而資料品質頁恰恰是最不該有過時數字的一頁。
    """
    from mstr_cebe import events as EV                       # noqa: E402
    from mstr_cebe import phases as PH                       # noqa: E402

    conn = EV.connect()
    try:
        forms = conn.execute(
            "SELECT source, COUNT(*), MIN(filed_at), MAX(filed_at),"
            " SUM(byte_len) FROM documents GROUP BY source"
            " ORDER BY COUNT(*) DESC").fetchall()
        kinds = conn.execute(
            "SELECT granularity, COUNT(*) FROM events"
            " GROUP BY granularity").fetchall()
        resolved = EV.resolve_flows(conn)
        ops = EV.all_events(conn, family="action", granularity=None)
    finally:
        conn.close()

    # 年頻的淨貢獻趨近零 = 年報被季報與週報完整解釋掉。這是三種粒度
    # 互相對得起來最硬的證據,因為年報是另一次獨立申報。
    years = [{"y": r.period_start[:4],
              "stated_b": round(r.stated_usd / 1e9, 3),
              "left_b": round(r.usd / 1e9, 3),
              "pct": round(abs(r.usd / r.stated_usd) * 100, 1)}
             for r in resolved if r.granularity == "year" and r.stated_usd]

    conflicts = [{"kind": r.kind, "grp": r.group,
                  "lo": r.period_start, "hi": r.period_end,
                  "stated_b": round(r.stated_usd / 1e9, 3),
                  "fine_b": round(r.covered_usd / 1e9, 3)}
                 for r in resolved if r.conflict]

    conn = EV.connect()
    try:
        recon = []
        for e in chronicle:
            hi = e["end"] or daily["date"][-1]
            u = PH.sources_and_uses(conn, daily, e["start"], hi)
            recon.append({
                "title": e["title"], "lo": e["start"], "hi": hi,
                "uses_b": round(u["uses_usd"] / 1e9, 2),
                "sources_b": round(u["sources_usd"] / 1e9, 2),
                "gap_b": round(u["unexplained_usd"] / 1e9, 2),
                "gap_pct": round(abs(u["unexplained_usd"])
                                 / max(u["uses_usd"], u["sources_usd"]) * 100, 1),
                "prorated_b": round(u["prorated_usd"] / 1e9, 1),
                "resolvable": u["resolvable"],
            })
    finally:
        conn.close()

    return {
        "docs": [{"src": f[0], "n": f[1], "lo": f[2], "hi": f[3],
                  "mb": round((f[4] or 0) / 1e6, 1)} for f in forms],
        "doc_total": sum(f[1] for f in forms),
        "events": {g: n for g, n in kinds},
        "event_total": sum(n for _, n in kinds),
        "action_total": len(ops),
        "years": years,
        "conflicts": conflicts,
        "recon": recon,
    }


def build_vol_ladder(daily: dict, window: int = 30) -> dict:
    """已實現波動階梯 —— 把「波動阻尼」從公司的宣稱變成量測值。

    順序刻意按**實測波動**排,不按清償順位。兩者不一致的地方正是重點:
    STRK 比 STRD 優先,但波動高得多 —— 因為它嵌了轉換權,
    所以它繼承了股權的波動。**波動階梯跟著條款走,不跟著順位走。**
    """
    import mstr_cebe.volatility as VOL
    eq = VOL.realized_vol(daily["mstr"], window)
    rows = []
    for key, label in (("btc", "BTC"), ("mstr", "MSTR"),
                       ("strk_price", "STRK"), ("strd_price", "STRD"),
                       ("strf_price", "STRF"), ("strc_price", "STRC")):
        v = VOL.realized_vol(daily[key], window)
        if v is None:
            continue
        rows.append({
            "t": label,
            "vol": round(v * 100, 1),
            # BTC 沒有「相對普通股剝離了多少」這個概念 —— 它是底層不是衍生層
            "damp": (None if label in ("BTC", "MSTR")
                     else round(VOL.damping(v, eq) * 100, 0)),
        })
    rows.sort(key=lambda r: -r["vol"])
    btc = next((r["vol"] for r in rows if r["t"] == "BTC"), None)
    mstr = next((r["vol"] for r in rows if r["t"] == "MSTR"), None)
    return {"window": window, "rows": rows,
            "amp": round(mstr / btc, 2) if btc and mstr else None}


def build_meta(daily: dict) -> dict:
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
        "findings": _findings(daily),
    }


_PREF = ("strf", "strc", "strk", "strd", "stre")


def _par_vs_market(daily: dict, i: int) -> dict:
    """優先股按面額扣 vs 按市價扣,對 CEBE 與 CEBE mNAV 的差別。

    本站(與 CEBETRACKER)一律按<b>面額</b>扣,理由是清算優先權在法律上就是
    那個金額。但市場把優先股標在面額以下時,面額口徑就會高估求償權 ——
    於是低估實得每股、高估 CEBE mNAV。這裡把兩種口徑都算出來當作已知偏差。

    STRE 沒有公開報價,保守地按面額計入(當成零會反過來低估求償權)。
    可轉債同樣沒有市價,兩種口徑都按面額 —— 所以下面的差距是<b>下限</b>。
    """
    px = daily["btc"][i]
    shares = daily["shares"][i] * 1e6
    par = sum(daily[f"{k}_lp"][i] for k in _PREF) * 1e9
    mkt = sum(daily[f"{k}_lp"][i] * 1e9
              * ((daily[f"{k}_price"][i] / 100) if daily[f"{k}_price"][i] else 1.0)
              for k in _PREF)
    base = (daily["debt"][i] - daily["cash"][i]) * 1e9        # 兩種口徑相同的部分
    e_par = (daily["held"][i] - (base + par) / px) / shares * 1e8
    e_mkt = (daily["held"][i] - (base + mkt) / px) / shares * 1e8
    mcap = daily["mstr"][i] * shares
    return {
        "date": daily["date"][i],
        "par_b": par / 1e9, "mkt_b": mkt / 1e9,
        # 第一檔優先股發行之前 par = 0,那些日子沒有這個偏差可談
        "pct_of_par": (mkt / par * 100) if par > 0 else 100.0,
        "e_par": e_par, "e_mkt": e_mkt,
        "mnav_par": mcap / (e_par / 1e8 * shares * px),
        "mnav_mkt": mcap / (e_mkt / 1e8 * shares * px),
    }


def _grain_facts() -> dict:
    """粒度相關 finding 需要的數字。全部現算。"""
    from mstr_cebe import events as EV                       # noqa: E402

    conn = EV.connect()
    try:
        rows = conn.execute(
            "SELECT period_start, period_end, qty, granularity FROM events"
            " WHERE kind='btc_purchase' AND qty IS NOT NULL").fetchall()
        resolved = EV.resolve_flows(conn)
        act = conn.execute(
            "SELECT effective_at, qty, usd FROM events WHERE kind='btc_purchase'"
            " AND effective_at='2026-03-08'").fetchone()
    finally:
        conn.close()

    # 重複計算最嚴重的那一年:季合計列 = 該季實際變化,週列是同一段的拆解
    by_year = {}
    for ps, pe, qty, g in rows:
        y = (pe or ps)[:4]
        by_year.setdefault(y, {"week": 0.0, "quarter": 0.0})
        if g in ("week", "quarter"):
            by_year[y][g] += qty
    dup_year = max(by_year, key=lambda y: by_year[y]["quarter"])
    wk, qt = by_year[dup_year]["week"], by_year[dup_year]["quarter"]

    # 該年實際增加多少顆 —— 這是判斷有沒有重複計算的基準,
    # 而且它完全不含價格成分(美元會讓人懷疑是幣價口徑不同造成的)。
    hold = dict(json.load(open(os.path.join(RAW, "btc_holdings_weekly.json"),
                               encoding="utf-8")))
    def _at(day: str) -> float:
        prior = [d for d in hold if d <= day]
        return hold[max(prior)] if prior else 0.0
    actual = _at(f"{dup_year}-12-31") - _at(f"{int(dup_year) - 1}-12-31")

    years = [r for r in resolved if r.granularity == "year" and r.stated_usd]
    pcts = sorted(round(abs(r.usd / r.stated_usd) * 100, 1) for r in years)

    c = next((r for r in resolved if r.conflict), None)
    if c:
        txt = (f"兩者對同一季的金額差 "
               f"${abs(c.covered_usd - c.stated_usd) / 1e6:,.0f}M —— "
               f"{c.period_start[:7]}–{c.period_end[:7]} 的優先股 ATM,"
               f"8-K 週表加總 ${c.covered_usd / 1e9:.3f}B、"
               f"10-Q 現金流量表 ${c.stated_usd / 1e9:.3f}B。"
               f"原因是季末最後幾天成交的部分,現金到下一季才入帳。"
               f"<strong>這是系統性的口徑差,不是解析錯誤</strong>,所以粒度解析把它標記出來"
               f"(貢獻取 0)而不是悄悄倒扣。全部 "
               f"{sum(1 for r in resolved if r.granularity != 'week')} 筆粗粒度"
               f"事件裡只有這一筆。")
    else:
        txt = "目前沒有跨文件對不上的粗粒度事件。"

    return {
        "dup_year": dup_year,
        "dup_week": wk, "dup_quarter": qt, "dup_sum": wk + qt,
        "dup_actual": actual, "dup_times": (wk + qt) / actual if actual else 0,
        "n_year": len(years),
        "year_pct_lo": min(pcts) if pcts else 0,
        "year_pct_hi": max(pcts) if pcts else 0,
        "conflict_text": txt,
        "nbsp_week": act[0] if act else "2026-03-08",
        "nbsp_coins": act[1] if act else 0,
        "nbsp_usd": abs(act[2] or 0) / 1e9 if act else 0,
    }


def _findings(daily: dict) -> list:
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

    n = len(daily["date"])
    now = _par_vs_market(daily, n - 1)
    # 折價最深的那一天,用來說明這個偏差最大能有多大
    have_pref = [i for i in range(n)
                 if sum(daily[f"{k}_lp"][i] for k in _PREF) > 0]
    series = [_par_vs_market(daily, i) for i in have_pref]
    worst = min(series, key=lambda x: x["pct_of_par"])
    # 兩種口徑跨過 1.0 的日子:面額口徑看起來有溢價,市價口徑其實沒有。
    # 這才是這個偏差真正會誤導人的情況,所以獨立挑出來講。
    flips = [x for x in series if x["mnav_par"] >= 1.0 > x["mnav_mkt"]]
    flip = max(flips, key=lambda x: x["mnav_par"] - x["mnav_mkt"]) if flips else None

    grain = _grain_facts()

    return [
        {"t": "求償權按面額扣,優先股跌破面額時會低估實得每股",
         "b": f"本站與 CEBETRACKER 一致,把優先股按 $100 <b>面額</b>扣掉 —— "
              f"清算優先權在法律上就是那個金額。但市場把優先股標在面額以下時,"
              f"面額口徑就高估了求償權,於是<b>低估實得每股、高估 CEBE mNAV</b>。"
              f"目前優先股面額 ${now['par_b']:.2f}B、市值 ${now['mkt_b']:.2f}B"
              f"(市場只認 {now['pct_of_par']:.0f}%),實得每股 "
              f"{now['e_par']:,.0f} → {now['e_mkt']:,.0f} sats、"
              f"CEBE mNAV {now['mnav_par']:.3f}x → {now['mnav_mkt']:.3f}x。"
              f"折價最深是 {worst['date']}(市場只認 {worst['pct_of_par']:.0f}%),"
              f"那天兩種口徑的 CEBE mNAV 差 "
              f"{worst['mnav_par']:.3f}x 對 {worst['mnav_mkt']:.3f}x。"
              + (f"期間有 {len(flips)} 個交易日<b>兩種口徑跨過 1.0</b> —— "
                 f"面額口徑看起來有溢價,市價口徑其實沒有;"
                 f"差距最大的 {flip['date']} 是 {flip['mnav_par']:.3f}x 對 "
                 f"{flip['mnav_mkt']:.3f}x。這是這個偏差最會誤導人的地方。"
                 if flip else "期間沒有出現兩種口徑跨過 1.0 的日子。")
              + "<br><br>"
              "連帶影響歸因:「折價回購加分」這個結論<b>成立的前提是面額口徑</b>。"
              "按市價看,公司付的就是當下的公允價格,並沒有賺到價差。"
              "兩種口徑回答的是不同問題(清算價值 vs 市場價值),本站選面額 —— "
              "但要知道它偏在哪一邊。可轉債沒有市價,兩種口徑都按面額,"
              "所以上面的差距是<b>下限</b>;STRE 沒有報價,同樣保守地按面額計入。"},
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
        {"t": "季末那份 8-K 會多附一列季合計,格式與週列一模一樣",
         "b": f"每季第一份 8-K(Item 2.02 財報預告)在逐週活動表旁邊附一列該季合計。"
              f"把它當週紀錄就會把同一季算兩次。以 {grain['dup_year']} 年為例:"
              f"週列加總 {grain['dup_week']:,.0f} 顆、季合計列 {grain['dup_quarter']:,.0f} 顆,"
              f"兩者相加 {grain['dup_sum']:,.0f} 顆 —— 而該年<strong>實際只增加 "
              f"{grain['dup_actual']:,.0f} 顆</strong>,也就是 {grain['dup_times']:.2f} 倍。"
              f"(這裡刻意用顆數不用美元:幣價會波動,顆數沒有自由度。)現在三種粒度"
              f"(週 / 季 / 年)分開記,規則是<strong>粗粒度只能補洞,不能與細粒度相加</strong>。"
              f"驗證:{grain['n_year']} 筆年報買幣經過這個規則之後,淨貢獻只剩 "
              f"{grain['year_pct_lo']}–{grain['year_pct_hi']}% —— 年報是另一次獨立申報,"
              f"週與季若有系統性漏記或重複,這裡會留下一大塊殘差。"},
        {"t": "8-K 週表是成交日,10-Q 現金流量表是交割日",
         "b": grain["conflict_text"]},
        {"t": "一個不斷行空格讓整整一週的買幣消失了",
         "b": f"EDGAR 的表頭用 U+00A0,`BTC&#160;Acquired`。解析用的正則是一般空格,"
              f"<strong>比不中、不報錯、整列被丟掉</strong>。2026-10-02 查出來時已經存在很久:"
              f"{grain['nbsp_week']} 那一週的 {grain['nbsp_coins']:,.0f} 顆 / "
              f"${grain['nbsp_usd']:.2f}B 買幣在活動表裡完全不存在,"
              f"2025-11-30 的季末餘額 650,000 也一起消失(持幣序列因此空了 21 天)。"
              f"這與排版用撇號(U+2019)是同一類陷阱:<strong>看起來一樣的字元,"
              f"比對起來不一樣,而且失配是靜默的</strong>。修正放在最底層的逐格抽取,"
              f"並加了「完整週列不得缺 holdings」這條測試 —— 這個 bug 當初就是"
              f"以那個樣子存在的。"},
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


def write_scenario_golden(daily: dict) -> None:
    """定價頁情境模擬的黃金樣本,給前端的測試比對用。

    定價頁是互動模擬器(四個連續滑桿),不可能把結果預先算好塞進 JSON ——
    所以 TS 必須保留一份實作。CLAUDE.md 第一條規則的理由是「TS 那側沒有
    測試守著」,這份檔案就是那個「守著」:**Python 是公式的來源與推導處
    (mstr_cebe/scenario.py),TS 的實作由這 360 筆樣本釘住**。

    刻意**不**放進 app/data —— 它不是前端要顯示的資料,是測試夾具。
    """
    from mstr_cebe import scenario as SC                      # noqa: E402
    from mstr_cebe.toolbox import State                       # noqa: E402

    i = len(daily["date"]) - 1
    basis = State(
        held=daily["held"][i],
        claims=(daily["debt"][i] + daily["pref_total"][i]
                - daily["cash"][i]) * 1e9,
        shares=daily["shares"][i] * 1e6,
        price=daily["btc"][i],
    )
    payload = {
        "as_of": daily["date"][i],
        "basis": {"held": basis.held, "claims": basis.claims,
                  "shares": basis.shares, "px0": basis.price},
        "cases": SC.golden_grid(basis),
    }
    path = os.path.join(ROOT, "app", "test", "scenario-golden.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  app/test/scenario-golden.json  {len(payload['cases'])} 筆樣本")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    daily = build_daily()
    weekly, meta = build_weekly(), build_meta(daily)
    chronicle = build_chronicle(daily, weekly)
    meta["toolkit"] = build_toolkit()
    meta["program"] = build_program(daily, weekly)
    strategy = build_strategy(daily, weekly, chronicle)
    meta["watch"] = structural_watch(daily, chronicle)
    meta["prov"] = build_provenance(daily, chronicle)
    meta["vol"] = build_vol_ladder(daily)

    for name, payload in (("daily", daily), ("weekly", weekly),
                          ("meta", meta), ("chronicle", chronicle),
                          ("strategy", strategy), ("formulas", build_formulas()),
                          ("operations", build_operations_feed(daily)),
                          ("posts", build_posts(daily, chronicle, meta))):
        path = os.path.join(OUT, f"{name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        print(f"  app/data/{name}.json  {os.path.getsize(path)//1024} KB")

    write_scenario_golden(daily)

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
