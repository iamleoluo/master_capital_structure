"""L4 — 階段:把時間序加進來。

設計圖:reference/06-architecture.md §6

設計圖主張「**階段 = 工具組合的穩定期**,邊界在組合改變的地方,
不在新聞發生的地方」。這份模組實作那個偵測器,**並且量化它現在還不能用的原因**。

量化的結果是這一步最重要的產出:L3 的操作只涵蓋每週 8-K 表格揭露的動作,
而人工分期的三個邊界裡有兩個是由**不在那些表格裡**的結構事件定義的 ——
可轉債發行與優先股 IPO。`explained_share()` 把這個缺口算成數字。

所以偵測器可以跑、可以比對,但**還不能取代人工分期**。
要能取代,缺的不是演算法,是 L1 的涵蓋範圍(見 06-architecture.md §9 第 6 步)。
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from . import operations as O

# 工具在結構上做的事。偵測器看的是這個,不是工具本身 ——
# 「發優先股」與「發可轉債」對結構是同一件事(掛上求償權),
# 而「普通股 ATM」雖然也募到錢,做的卻是稀釋 + 抵減求償權。
STRUCTURAL_ROLE: Dict[str, str] = {
    "buy_btc": "accumulate",            # 持幣增加
    "sell_btc": "liquidate",            # 持幣減少
    "issue_preferred": "lever_up",      # 掛上求償權
    "common_atm": "dilute",             # 股數增加、求償權減少
    "buyback_preferred": "delever",     # 消滅求償權
    "sell_to_buyback": "delever",       # 賣幣換來的錢去消滅求償權
    "convert_conversion": "delever",
    "common_buyback": "concentrate",
}


@dataclass(frozen=True)
class Boundary:
    week: str
    before: str
    after: str
    persisted_weeks: int


def weekly_mix(conn: sqlite3.Connection, *, by: str = "role") -> Dict[str, Dict[str, float]]:
    """每週各工具(或各結構角色)動用的資本佔比。

    by="role" 用結構角色分組,by="tool" 用工具本身。
    金額取絕對值 —— 這裡問的是「資本往哪個方向動」,不是淨流向。
    """
    raw: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for op in O.build(conn):
        key = (STRUCTURAL_ROLE.get(op.combo_id, op.combo_id)
               if by == "role" else op.combo_id)
        if op.combo_id == "sell_to_buyback":
            # 組合操作的兩邊是同一筆錢,只算一次
            usd = max(abs(u or 0) for _, _, u in op.members)
        else:
            usd = abs(op.params.get("usd") or 0.0)
        if usd:
            raw[op.window_hi][key] += usd
    return {w: {k: v / sum(row.values()) for k, v in row.items()}
            for w, row in sorted(raw.items()) if sum(row.values())}


def detect(conn: sqlite3.Connection, *, persist: int = 3,
           by: str = "role") -> List[Boundary]:
    """主導成分改變、而且維持 `persist` 週以上,就記一個邊界。

    要求持續是為了擋掉單週的雜訊 —— 某一週剛好買了一大筆幣,
    不代表策略變了。
    """
    mix = weekly_mix(conn, by=by)
    weeks = list(mix)
    dom = [max(mix[w], key=mix[w].get) for w in weeks]

    out: List[Boundary] = []
    i = 1
    while i < len(dom):
        if dom[i] == dom[i - 1]:
            i += 1
            continue
        run = 1
        while i + run < len(dom) and dom[i + run] == dom[i]:
            run += 1
        if run >= persist:
            out.append(Boundary(week=weeks[i], before=dom[i - 1],
                                after=dom[i], persisted_weeks=run))
        i += run
    return out


def claims_delta(op) -> Optional[float]:
    """這個操作讓求償權變動多少。用 toolbox 的工具算,不自己寫符號。

    **發優先股有兩個結構效果**:拿到現金(求償權減少)與掛上清算優先權
    (求償權增加)。事件只記了現金那一邊,面額要從股數 × $100 推 ——
    漏掉它會讓解釋率算出 219% 這種數字。
    """
    from . import toolbox as T

    base = T.State(held=1.0, claims=0.0, shares=1.0, price=1.0)
    p = op.params
    usd, qty = p.get("usd"), p.get("qty")

    if op.combo_id == "sell_to_buyback":
        # 賣幣所得換成消滅的面額:求償權淨減少「面額」那麼多
        after = T.BUYBACK_PREFERRED(base, c=0.0, F=p.get("F") or 0.0)
    elif op.combo_id == "buy_btc":
        after = T.BUY_BTC(base, c=-(usd or 0.0))          # usd 為負(現金流出)
    elif op.combo_id == "sell_btc":
        after = T.State(base.held, base.claims - (usd or 0.0),
                        base.shares, base.price)
    elif op.combo_id == "issue_preferred":
        after = T.ISSUE_PREFERRED(base, c=usd or 0.0, F=(qty or 0.0) * 100)
    elif op.combo_id == "common_atm":
        after = T.State(base.held, base.claims - (usd or 0.0),
                        base.shares + (qty or 0.0), base.price)
    elif op.combo_id == "buyback_preferred":
        after = T.BUYBACK_PREFERRED(base, c=-(usd or 0.0),
                                    F=(qty or 0.0) * 100)
    else:
        return None
    return after.claims - base.claims


def explained_share(conn: sqlite3.Connection, daily: dict,
                    lo: str, hi: str) -> Dict[str, float]:
    """這一段的求償權變動,有多少是 L3 的操作解釋得了的。

    這是偵測器能不能用的**前提檢查**。解釋率低,代表結構在動但操作層
    看不到 —— 那時候任何「從操作推分期」的結論都是虛的。
    """
    i, j = daily["date"].index(lo), daily["date"].index(hi)
    claims = [(daily["debt"][k] + daily["pref_total"][k]
               - daily["cash"][k]) * 1e9 for k in (i, j)]
    actual = claims[1] - claims[0]

    # 按結構角色攤開。只給一個比率會把兩種相反的缺口混成一個數字:
    # 「用途被記了但來源沒有」與「來源被記了但用途沒有」都會讓比率偏離 100%,
    # 方向卻完全不同。
    by_role: Dict[str, float] = defaultdict(float)
    explained = 0.0
    for op in O.build(conn):
        if not (lo <= op.window_hi <= hi):
            continue
        d = claims_delta(op)
        if d is None:
            continue
        explained += d
        by_role[STRUCTURAL_ROLE.get(op.combo_id, op.combo_id)] += d
    return {
        "actual_usd": actual,
        "explained_usd": explained,
        "share": explained / actual if actual else float("nan"),
        "unexplained_usd": actual - explained,
        "by_role": dict(by_role),
    }


def sources_and_uses(conn: sqlite3.Connection, daily: dict,
                     lo: str, hi: str) -> Dict[str, float]:
    """這一段的錢從哪來、到哪去 —— 用顆粒解析過的資金流,不只看週顆粒。

    `explained_share()` 問的是「求償權變動解釋得了多少」,走的是 L3 的
    操作,而 L3 目前只吃週顆粒 —— 所以 8-K 還沒開始揭露的那段必然低估。
    這一支改走 `events.resolve_flows()`,把季與年補洞的部分也算進來,
    於是早期那幾段也有數字。

    對帳等式:**買幣 + 股息 + 儲備增加 = 各種募資 + 賣幣**。
    兩邊都是現金口徑,所以不需要面額,也就不受「優先股按面額還是按
    募資金額計」那個未決問題影響 —— 那正是這一支能先做的原因。
    """
    from . import events as E

    def overlap(ps: str, pe: str) -> float:
        """這筆事件的期間有多少比例落在 [lo, hi] 內。

        階段邊界是按結構轉折劃的,不會剛好切在季底 —— 例如「折價回收」
        從 2026-06-29 開始,而 2026Q2 那一季只有最後兩天在裡面。整季算進來
        會憑空多出 $6B 的資金流。週顆粒幾乎不受影響(一週最多錯幾天),
        季與年則非攤不可。
        """
        a = max(dt.date.fromisoformat(ps), dt.date.fromisoformat(lo))
        b = min(dt.date.fromisoformat(pe), dt.date.fromisoformat(hi))
        if b < a:
            return 0.0
        span = (dt.date.fromisoformat(pe) - dt.date.fromisoformat(ps)).days + 1
        return ((b - a).days + 1) / span if span > 0 else 0.0

    flows: Dict[str, float] = defaultdict(float)
    prorated = 0.0
    for r in E.resolve_flows(conn):
        if not r.usd:
            continue
        w = overlap(r.period_start, r.period_end)
        if w <= 0:
            continue
        if 0 < w < 1:
            prorated += abs(r.usd) * w
        key = f"{r.kind}:{r.group}" if r.kind == "atm_issue" else r.kind
        flows[key] += r.usd * w

    i, j = daily["date"].index(lo), daily["date"].index(hi)
    reserve = (daily["cash"][j] - daily["cash"][i]) * 1e9

    buyback = abs(flows["preferred_repurchase"])
    uses = (abs(flows["btc_purchase"]) + abs(flows["dividend_payment"])
            + buyback + reserve)
    sources = (flows["atm_issue:MSTR"] + flows["atm_issue:PREFERRED"]
               + flows["convert_issue"] + flows["convert_repurchase"]
               + flows["btc_sale"])
    return {
        "buy_usd": abs(flows["btc_purchase"]),
        "dividend_usd": abs(flows["dividend_payment"]),
        "buyback_usd": buyback,
        "reserve_delta_usd": reserve,
        "common_atm_usd": flows["atm_issue:MSTR"],
        "preferred_usd": flows["atm_issue:PREFERRED"],
        "convert_net_usd": flows["convert_issue"] + flows["convert_repurchase"],
        "sell_usd": flows["btc_sale"],
        "uses_usd": uses,
        "sources_usd": sources,
        "unexplained_usd": uses - sources,
        "prorated_usd": prorated,       # 有多少金額是按天數攤進來的
        # 攤分佔比:超過 0.3 就代表這段期間**比可用顆粒還短**,
        # 對帳結果主要由攤分假設決定而不是由資料決定 —— 不該當結論用。
        # 「壓力測試」只有 26 天,而最細的來源在那段是季頻,就是這種情況。
        "prorated_share": prorated / uses if uses else float("nan"),
        "resolvable": bool(uses) and prorated / uses < 0.3,
        "share": sources / uses if uses else float("nan"),
    }


def compare(detected: Sequence[Boundary],
            hand: Sequence[str], tol_days: int = 21) -> List[dict]:
    """偵測到的邊界與人工分期對照。tol_days 內算對得上。"""
    out = []
    for h in hand:
        hd = dt.date.fromisoformat(h)
        best, gap = None, None
        for b in detected:
            d = abs((dt.date.fromisoformat(b.week) - hd).days)
            if gap is None or d < gap:
                best, gap = b, d
        out.append({"hand": h,
                    "detected": best.week if best else None,
                    "gap_days": gap,
                    "matched": gap is not None and gap <= tol_days,
                    "shift": f"{best.before} → {best.after}" if best else None})
    return out


def main(argv: Optional[List[str]] = None) -> int:
    import json
    import os

    conn = O.connect()
    O.rebuild(conn)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "app", "data", "daily.json"),
              encoding="utf-8") as f:
        daily = json.load(f)
    with open(os.path.join(root, "app", "data", "chronicle.json"),
              encoding="utf-8") as f:
        eras = json.load(f)

    print("每週主導的結構角色(組合改變處標 ←):\n")
    mix = weekly_mix(conn)
    prev = None
    for w, row in mix.items():
        dom = max(row, key=row.get)
        print(f"  {w}  {dom:<12}{row[dom]*100:>5.0f}%"
              + ("   ←" if dom != prev else ""))
        prev = dom

    bounds = detect(conn)
    print(f"\n偵測到 {len(bounds)} 個邊界(主導角色改變且維持 ≥3 週):")
    for b in bounds:
        print(f"  {b.week}  {b.before} → {b.after}  (維持 {b.persisted_weeks} 週)")

    hand = [e["start"] for e in eras[1:]]
    print("\n與人工分期對照:")
    for c in compare(bounds, hand):
        mark = "✓" if c["matched"] else "✗"
        print(f"  {mark} 人工 {c['hand']}  偵測 {c['detected'] or '—'}"
              f"  差 {c['gap_days'] if c['gap_days'] is not None else '—'} 天"
              f"  {c['shift'] or ''}")

    print("\n資金來源與用途(顆粒解析後,含季與年補洞)——"
          " 買幣+股息+儲備增加 = 募資+賣幣:")
    print(f"  {'階段':<10}{'買幣':>7}{'股息':>6}{'儲備':>7}"
          f"{'回購':>6}{'普通ATM':>8}{'優先':>7}{'可轉債':>7}{'賣幣':>6}{'未解釋':>8}{'其中攤分':>9}")
    for e in eras:
        lo = e["start"]
        hi = e["end"] or daily["date"][-1]
        u = sources_and_uses(conn, daily, lo, hi)
        print(f"  {e['title']:<10}{u['buy_usd']/1e9:>7.1f}{u['dividend_usd']/1e9:>6.2f}"
              f"{u['reserve_delta_usd']/1e9:>7.2f}{u['buyback_usd']/1e9:>6.1f}"
              f"{u['common_atm_usd']/1e9:>8.1f}"
              f"{u['preferred_usd']/1e9:>7.1f}{u['convert_net_usd']/1e9:>7.1f}"
              f"{u['sell_usd']/1e9:>6.1f}{u['unexplained_usd']/1e9:>8.1f}"
              f"{u['prorated_usd']/1e9:>9.1f}"
              + ("" if u["resolvable"] else "   ⚠️ 期間短於可用顆粒,對帳不成立"))

    print("\n前提檢查 —— 各階段的求償權變動有多少是操作層解釋得了的"
          "(L3 目前只吃週顆粒,所以早期必然低估):")
    for e in eras:
        lo = e["start"]
        hi = e["end"] or daily["date"][-1]
        s = explained_share(conn, daily, lo, hi)
        roles = "  ".join(f"{k}={v/1e9:+.1f}B"
                          for k, v in sorted(s["by_role"].items(),
                                             key=lambda x: -abs(x[1])))
        print(f"  {e['title']:<8} {lo} → {hi}"
              f"  實際 ${s['actual_usd']/1e9:>7.2f}B"
              f"  可解釋 ${s['explained_usd']/1e9:>7.2f}B"
              f"  {s['share']*100:>6.0f}%")
        print(f"           {roles}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
