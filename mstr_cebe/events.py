"""L2 — 事件:有名義的原子動作。

設計圖:reference/06-architecture.md §4

這一層是「資料」變成「動作」的地方。在此之前,`web/raw/atm_weekly.json`
只是「這一週各券種合計募了多少」—— 名義藏在**檔名**裡,所以問得出
「回購檔案裡 8 月那幾週是什麼」,問不出「2026 年 8 月有哪些動作」。

事件分兩個家族,這個區分寫進 schema 而不只是註解:

  action       動作 —— 公司做了什麼。對應 toolbox 的一把工具。
  observation  觀測 —— 狀態是多少。**沒有**對應工具。

混在一起的後果是把「餘額變了」讀成「公司做了什麼」,而那正是四層歸因
最想避免的錯誤(見 01-model.md §8)。

週聚合從此是**視圖**而不是真相:`weekly_*()` 由事件即時算出來,
並且與舊的 `web/raw/*.json` 逐筆相同(tests/test_events.py 驗)。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

from . import archive as A

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  event_id     TEXT PRIMARY KEY,   -- hash(doc_id, kind, instrument, locator)
  kind         TEXT NOT NULL,
  family       TEXT NOT NULL,      -- 'action' | 'observation'
  instrument   TEXT NOT NULL,      -- 'BTC' | 'MSTR' | 'STRC' | 'USD' | ...
  effective_at TEXT NOT NULL,      -- 動作發生日／觀測基準日
  period_start TEXT,               -- 文件宣告的期間(逐週揭露都有)
  period_end   TEXT,
  qty          REAL,
  unit         TEXT,               -- 'BTC' | 'shares' | 'USD'
  usd          REAL,               -- 現金流,流入為正、流出為負
  unit_price   REAL,
  attrs        TEXT,               -- JSON,**只放文件自己寫的**額外欄位
  doc_id       TEXT NOT NULL REFERENCES documents(doc_id),
  locator      TEXT NOT NULL,      -- 這筆在文件裡對應哪一列
  extraction   TEXT NOT NULL,      -- 'stated' | 'derived'
  confidence   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ev_kind_date ON events(kind, effective_at);
CREATE INDEX IF NOT EXISTS idx_ev_family ON events(family, effective_at);
CREATE INDEX IF NOT EXISTS idx_ev_doc ON events(doc_id);
"""

# 事件種類 → (家族, 對應的 toolbox 工具 id)。None 表示這是觀測,沒有工具。
# 這張表就是 L2 與 toolbox.py 的接點 —— 見 06-architecture.md §4。
KINDS: Dict[str, tuple] = {
    "btc_purchase":           ("action", "buy_btc"),
    "btc_sale":               ("action", "sell_btc"),
    "atm_issue":              ("action", None),   # 工具看 instrument,見 tool_for()
    "preferred_repurchase":   ("action", "buyback_preferred"),
    "holdings_observation":   ("observation", None),
    "reserve_observation":    ("observation", None),
    "atm_capacity":           ("observation", None),
    "repurchase_authority":   ("observation", None),
}


def tool_for(kind: str, instrument: str) -> Optional[str]:
    """這個事件對應 toolbox 的哪一把工具。觀測回傳 None。

    只有 atm_issue 需要看 instrument:發普通股是 COMMON_ATM,
    發優先股是 ISSUE_PREFERRED —— 兩者對 E 的效果完全不同。
    """
    family, tool = KINDS[kind]
    if family == "observation":
        return None
    if kind == "atm_issue":
        return "common_atm" if instrument == "MSTR" else "issue_preferred"
    return tool


@dataclass(frozen=True)
class Event:
    kind: str
    instrument: str
    effective_at: str
    doc_id: str
    locator: str
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    qty: Optional[float] = None
    unit: Optional[str] = None
    usd: Optional[float] = None
    unit_price: Optional[float] = None
    attrs: Dict = field(default_factory=dict)
    extraction: str = "stated"
    confidence: float = 1.0

    @property
    def family(self) -> str:
        return KINDS[self.kind][0]

    @property
    def event_id(self) -> str:
        """冪等:同一份文件重解兩次,得到同一個 id。"""
        key = f"{self.doc_id}|{self.kind}|{self.instrument}|{self.locator}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    @property
    def tool(self) -> Optional[str]:
        return tool_for(self.kind, self.instrument)


# --------------------------------------------------------------- 儲存

def connect(path: str = A.DEFAULT_PATH) -> sqlite3.Connection:
    """事件與文件放同一個檔案 —— 出處的外鍵才是真的。

    層次的分界不在檔案,而在「documents 永遠不得有衍生欄位」這條規則上。
    事件隨時可以整批刪掉再由文件重算(見 rebuild()),這就是可重放。
    """
    conn = A.connect(path)
    conn.executescript(SCHEMA)
    return conn


def insert(conn: sqlite3.Connection, events: Iterable[Event]) -> int:
    n = 0
    for e in events:
        conn.execute(
            "INSERT OR REPLACE INTO events (event_id, kind, family, instrument,"
            " effective_at, period_start, period_end, qty, unit, usd,"
            " unit_price, attrs, doc_id, locator, extraction, confidence)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (e.event_id, e.kind, e.family, e.instrument, e.effective_at,
             e.period_start, e.period_end, e.qty, e.unit, e.usd, e.unit_price,
             json.dumps(e.attrs, ensure_ascii=False, sort_keys=True),
             e.doc_id, e.locator, e.extraction, e.confidence))
        n += 1
    conn.commit()
    return n


def all_events(conn: sqlite3.Connection, *, kind: Optional[str] = None,
               family: Optional[str] = None) -> List[dict]:
    """取事件,附上該文件的申報日 —— 「後蓋前」的排序要靠它。"""
    where, args = [], []
    if kind:
        where.append("e.kind = ?")
        args.append(kind)
    if family:
        where.append("e.family = ?")
        args.append(family)
    sql = ("SELECT e.*, d.filed_at AS filed FROM events e"
           " JOIN documents d ON d.doc_id = e.doc_id")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY e.effective_at, d.filed_at, e.locator"
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(sql, args)]
    conn.row_factory = None
    for r in rows:
        r["attrs"] = json.loads(r["attrs"] or "{}")
    return rows


# --------------------------------------------------------------- 賣幣用途

# 8-K 有時會逐筆寫出賣幣所得的去向,例如 2026-08-02 那份:
#   "(1) $52.4 million in proceeds from the bitcoin sales were used to fund
#    dividends on Strategy's preferred stock and $52.3 million ... were used to
#    fund repurchases of STRC Stock under the Digital Credit Securities
#    Repurchase Program."
# 這是**文件自己寫的分配**,比任何金額相似度推論都強 —— L3 的配對要靠它,
# 所以在 L2 就解析成結構,而不是留一段自由文字給上層去猜。
_ALLOC_PAT = re.compile(
    r"\$([\d,.]+)\s*(million|billion)\s+in proceeds from the bitcoin sales?\s+"
    r"were used to\s+(.{0,160}?)(?=\s+and\s+\$[\d,.]+\s*(?:million|billion)|\.|\()",
    re.I)

# 用途字串 → 這筆錢流向哪一種動作。關鍵字取自申報文件的實際用語。
_PURPOSE_RULES = (
    ("preferred_repurchase", ("repurchase", "repurchases")),
    ("carry", ("dividend", "dividends", "distribution", "distributions")),
    ("reserve", ("usd reserve", "replenish")),
)


def classify_purpose(text: str) -> Optional[str]:
    """把文件寫的用途歸到一種動作。認不出來就回 None —— 不猜。"""
    low = (text or "").lower()
    for kind, words in _PURPOSE_RULES:
        if any(w in low for w in words):
            return kind
    return None


def parse_sale_allocation(html: str) -> List[Dict]:
    """解析「$X 用於 A、$Y 用於 B」的逐筆分配。沒有就回空清單。"""
    out = []
    for amount, unit, what in _ALLOC_PAT.findall(html):
        usd = float(amount.replace(",", "")) * (1e9 if unit.lower() == "billion"
                                                else 1e6)
        out.append({"usd": usd, "purpose": what.strip(),
                    "kind": classify_purpose(what)})
    return out


# --------------------------------------------------------------- 由文件推導

def _plain_text(html: str) -> str:
    """去標籤、壓空白。分配句式橫跨多個標籤,所以要先攤平。"""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def derive(conn: sqlite3.Connection, *, since: dt.date = dt.date(2024, 7, 1),
           verbose: bool = False) -> int:
    """走訪檔案庫,把每一份 8-K 解析成事件。不碰網路。

    解析用的還是原本那幾個 parse_* 函數 —— 這一步只是替它們的輸出
    補上出處(doc_id + locator)並給每一列一個名義。
    """
    from . import fetch_8k_atm, fetch_8k_btc, fetch_8k_repurchase, fetch_8k_reserve

    total = 0
    for f in A.iter_8k(conn, since=since):
        doc, html = f.meta.doc_id, f.html
        out: List[Event] = []

        # --- 持有量:這是觀測,不是動作 ---
        for d, v in list(fetch_8k_btc._parse_table_format(html)) + \
                list(fetch_8k_btc._parse_prose_format(html)):
            out.append(Event(
                kind="holdings_observation", instrument="BTC",
                effective_at=d.isoformat(), qty=float(v), unit="BTC",
                doc_id=doc, locator=f"holdings/{d.isoformat()}"))

        # --- 買賣比特幣:動作 ---
        alloc = parse_sale_allocation(_plain_text(html))
        for rec in fetch_8k_btc.parse_activity(html):
            delta = rec["btc_delta"]
            px = rec.get("avg_price")
            kind = "btc_purchase" if delta > 0 else "btc_sale"
            out.append(Event(
                kind=kind, instrument="BTC",
                effective_at=rec["week_end"],
                period_start=rec.get("week_start"), period_end=rec["week_end"],
                qty=abs(delta), unit="BTC",
                usd=(-abs(delta) * px if delta > 0 else abs(delta) * px)
                    if px else None,
                unit_price=px,
                attrs={**{k: rec[k] for k in
                          ("funding", "funding_raw", "sale_use") if k in rec},
                       # 文件逐筆寫出的用途分配(有才放)。L3 的配對靠這個。
                       **({"sale_allocation": alloc}
                          if kind == "btc_sale" and alloc else {})},
                doc_id=doc, locator=f"activity/{rec['week_end']}"))
            if rec.get("holdings") is not None:
                out.append(Event(
                    kind="holdings_observation", instrument="BTC",
                    effective_at=rec["week_end"], qty=float(rec["holdings"]),
                    unit="BTC", doc_id=doc,
                    locator=f"activity-holdings/{rec['week_end']}"))

        # --- ATM 發行:動作(普通股與優先股對應不同工具)---
        for rec in fetch_8k_atm.parse_atm_table(html):
            # 列序放進 locator:排序後就還原文件裡的表格順序。
            # 順序會影響浮點加總,而且這讓 locator 更接近「文件裡的實體位置」。
            for row_no, (sec, v) in enumerate(rec["by_security"].items()):
                out.append(Event(
                    kind="atm_issue", instrument=sec,
                    effective_at=rec["week_end"],
                    period_start=rec["week_start"], period_end=rec["week_end"],
                    qty=v.get("shares"), unit="shares",
                    usd=(v["net_proceeds_m"] * 1e6
                         if v.get("net_proceeds_m") is not None else None),
                    attrs={"notional_m": v.get("notional_m"),
                           "total_m": rec.get("total_m")},
                    doc_id=doc,
                    locator=f"atm/{rec['week_end']}/{row_no:02d}/{sec}"))
                if v.get("available_m") is not None:
                    out.append(Event(
                        kind="atm_capacity", instrument=sec,
                        effective_at=rec["week_end"],
                        qty=v["available_m"] * 1e6, unit="USD",
                        doc_id=doc,
                        locator=f"atm-capacity/{rec['week_end']}"
                                f"/{row_no:02d}/{sec}"))

        # --- 優先股回購:動作 ---
        authority = fetch_8k_repurchase.parse_remaining_authority(html)
        for rec in fetch_8k_repurchase.parse_repurchase_table(html):
            for row_no, (sec, v) in enumerate(rec["by_security"].items()):
                out.append(Event(
                    kind="preferred_repurchase", instrument=sec,
                    effective_at=rec["week_end"],
                    period_start=rec["week_start"], period_end=rec["week_end"],
                    qty=v.get("shares"), unit="shares",
                    usd=(-v["cost_m"] * 1e6
                         if v.get("cost_m") is not None else None),
                    # 文件自己列的合計。它是 L2 事實,不是我們算出來的 ——
                    # 留著才能拿來跟逐列加總對帳
                    attrs={"total_shares": rec.get("total_shares"),
                           "total_cost_m": rec.get("total_cost_m")},
                    doc_id=doc,
                    locator=f"repurchase/{rec['week_end']}"
                            f"/{row_no:02d}/{sec}"))
            # 剩餘授權是逐計畫揭露的(preferred / mstr),所以一個計畫一筆觀測
            for plan, amount_m in (authority or {}).items():
                out.append(Event(
                    kind="repurchase_authority", instrument=plan,
                    effective_at=rec["week_end"], qty=amount_m * 1e6,
                    unit="USD", doc_id=doc,
                    locator=f"authority/{rec['week_end']}/{plan}"))

        # --- USD 儲備:觀測 ---
        rec = fetch_8k_reserve.parse_reserve(html)
        if rec:
            out.append(Event(
                kind="reserve_observation", instrument="USD",
                effective_at=rec["as_of"], qty=rec["usd_reserve"], unit="USD",
                attrs={"usd_cash": rec.get("usd_cash")},
                doc_id=doc, locator=f"reserve/{rec['as_of']}"))

        total += insert(conn, out)
        if verbose and out:
            print(f"  {f.meta.filed_at}  {len(out):>3} 事件  {doc}")
    return total


def rebuild(conn: sqlite3.Connection, **kw) -> int:
    """整批刪掉再由文件重算 —— 這就是「每層可獨立重放」的實證。"""
    conn.execute("DELETE FROM events")
    conn.commit()
    return derive(conn, **kw)


# --------------------------------------------------------------- 週聚合視圖
#
# 週聚合從此是**視圖**,不是真相。同一週被多份 8-K 提到時取最新那份 ——
# 這個「後蓋前」的規則原本藏在 dict 覆寫的順序裡,現在是顯性的。

def _period_start(evs: Sequence[dict]) -> Optional[str]:
    """期間起日。觀測類事件沒有期間,所以要挑有的那一筆問。"""
    for e in evs:
        if e["period_start"]:
            return e["period_start"]
    return None


def _latest_per_period(rows: Sequence[dict]) -> Dict[str, List[dict]]:
    """依期間分組,每組只留申報日最新的那一份文件的事件。"""
    by_period: Dict[str, Dict[str, List[dict]]] = {}
    for r in rows:
        key = r["period_end"] or r["effective_at"]
        by_period.setdefault(key, {}).setdefault(r["filed"], []).append(r)
    return {p: docs[max(docs)] for p, docs in by_period.items()}


def weekly_holdings(conn: sqlite3.Connection) -> List[list]:
    """[[日期, 顆數], ...] —— 等同舊的 btc_holdings_weekly.json。"""
    seen: Dict[str, tuple] = {}
    for r in all_events(conn, kind="holdings_observation"):
        if r["locator"].startswith("holdings/"):
            # 同一天被多份文件提到時,取申報日最新的
            prev = seen.get(r["effective_at"])
            if prev is None or r["filed"] >= prev[0]:
                seen[r["effective_at"]] = (r["filed"], int(r["qty"]))
    return [[d, v] for d, (_, v) in sorted(seen.items())]


def weekly_activity(conn: sqlite3.Connection) -> List[dict]:
    """逐週買賣 —— 等同舊的 btc_activity_weekly.json。"""
    rows = [r for r in all_events(conn)
            if r["kind"] in ("btc_purchase", "btc_sale")]
    out = []
    for period, evs in sorted(_latest_per_period(rows).items()):
        e = evs[0]
        sign = 1 if e["kind"] == "btc_purchase" else -1
        holdings = None
        for h in all_events(conn, kind="holdings_observation"):
            if h["doc_id"] == e["doc_id"] and \
                    h["locator"] == f"activity-holdings/{period}":
                holdings = h["qty"]
                break
        out.append({
            "week_start": e["period_start"], "week_end": e["period_end"],
            "btc_delta": sign * e["qty"], "avg_price": e["unit_price"],
            "holdings": holdings,
            "funding": e["attrs"].get("funding", []),
            "funding_raw": e["attrs"].get("funding_raw", ""),
            "sale_use": e["attrs"].get("sale_use", ""),
            "filed": e["filed"],
        })
    return out


def weekly_atm(conn: sqlite3.Connection) -> List[dict]:
    """逐週 ATM 募資 —— 等同舊的 atm_weekly.json。"""
    rows = [r for r in all_events(conn)
            if r["kind"] in ("atm_issue", "atm_capacity")]
    out = []
    for period, evs in sorted(_latest_per_period(rows).items()):
        by_sec: Dict[str, dict] = {}
        has_issue, total_m = False, None
        for e in evs:
            by_sec.setdefault(e["instrument"], {})
            if e["kind"] == "atm_issue":
                by_sec[e["instrument"]].update({
                    "shares": e["qty"],
                    "notional_m": e["attrs"].get("notional_m"),
                    "net_proceeds_m": (e["usd"] / 1e6
                                       if e["usd"] is not None else None),
                })
                # total_m 可以是 null(文件沒有合計列),但那一週的紀錄
                # 仍然帶著這個鍵 —— 「沒有值」與「沒有這個欄位」不是同一件事
                has_issue, total_m = True, e["attrs"].get("total_m")
            else:
                by_sec[e["instrument"]]["available_m"] = e["qty"] / 1e6
        rec = {"week_start": _period_start(evs), "week_end": period,
               "by_security": by_sec}
        if has_issue:
            rec["total_m"] = total_m
        rec["filed"] = evs[0]["filed"]
        out.append(rec)
    return out


def weekly_repurchase(conn: sqlite3.Connection) -> List[dict]:
    """逐週優先股回購 —— 等同舊的 repurchase_weekly.json。"""
    rows = [r for r in all_events(conn)
            if r["kind"] in ("preferred_repurchase", "repurchase_authority")]
    out = []
    for period, evs in sorted(_latest_per_period(rows).items()):
        by_sec: Dict[str, dict] = {}
        authority: Dict[str, float] = {}
        totals: Dict[str, float] = {}
        for e in evs:
            if e["kind"] == "preferred_repurchase":
                by_sec[e["instrument"]] = {
                    "shares": e["qty"],
                    # + 0.0 把 -0.0 正規化掉,不然序列化出來會是 "-0.0"
                    "cost_m": (-e["usd"] / 1e6 + 0.0
                               if e["usd"] is not None else None)}
                totals = {k: e["attrs"].get(k)
                          for k in ("total_shares", "total_cost_m")}
            else:
                authority[e["instrument"]] = e["qty"] / 1e6
        rec = {"week_start": _period_start(evs), "week_end": period,
               "by_security": by_sec}
        rec.update({k: v for k, v in totals.items() if v is not None})
        rec["filed"] = evs[0]["filed"]
        rec["remaining_authority_m"] = authority
        out.append(rec)
    return out


def weekly_reserve(conn: sqlite3.Connection) -> List[dict]:
    """USD 儲備觀測 —— 等同舊的 reserve_weekly.json。"""
    seen: Dict[str, dict] = {}
    for r in all_events(conn, kind="reserve_observation"):
        prev = seen.get(r["effective_at"])
        if prev is None or r["filed"] >= prev["filed"]:
            seen[r["effective_at"]] = {
                "as_of": r["effective_at"], "usd_reserve": r["qty"],
                "usd_cash": r["attrs"].get("usd_cash"), "filed": r["filed"]}
    return [seen[k] for k in sorted(seen)]


# --------------------------------------------------------------- 資金流

def flows_between(conn: sqlite3.Connection, lo: str, hi: str) -> Dict[str, float]:
    """區間 [lo, hi] 內的資金流,單位美元。歸因層要的參數就是這些。

    **不能直接加總事件** —— 同一週被多份 8-K 提到時會重複計算。所以這裡
    走週聚合視圖,也就是「後蓋前」之後的那一份,與 `_latest_per_period()`
    同一個語意。
    """
    def in_range(week_end: str) -> bool:
        return lo <= week_end <= hi

    # 刻意以百萬為單位累加、最後才乘 1e6 —— 與既有管線的加總順序一致。
    # 先乘再加會在 1e-6 美元的量級上產生浮點差異,雖然毫無實質意義,
    # 但「重構不改變任何數字」這個驗收條件值得守到位。
    common_m = pref_m = 0.0
    for rec in weekly_atm(conn):
        if not in_range(rec["week_end"]):
            continue
        for sec, v in rec["by_security"].items():
            m = v.get("net_proceeds_m") or 0.0
            if sec == "MSTR":
                common_m += m
            else:
                pref_m += m
    common_raised, pref_proceeds = common_m * 1e6, pref_m * 1e6

    # 折價同樣是逐列算完再加總(而不是分別加總後相減),與既有管線一致
    repurchase_par = repurchase_cost = repurchase_discount = 0.0
    for rec in weekly_repurchase(conn):
        if not in_range(rec["week_end"]):
            continue
        for sec, v in rec["by_security"].items():
            if sec == "MSTR":                 # 普通股庫藏不是求償權回購
                continue
            par = (v.get("shares") or 0.0) * 100
            cost = (v.get("cost_m") or 0.0) * 1e6
            repurchase_par += par
            repurchase_cost += cost
            repurchase_discount += par - cost

    bought = sold = 0.0
    for rec in weekly_activity(conn):
        if not in_range(rec["week_end"]):
            continue
        delta, px = rec["btc_delta"], (rec["avg_price"] or 0.0)
        if delta > 0:
            bought += delta * px
        else:
            sold += -delta * px

    return {
        "common_raised": common_raised,     # 普通股 ATM 募得(抵減求償權)
        "pref_proceeds": pref_proceeds,     # 優先股 ATM 募得
        "repurchase_par": repurchase_par,   # 買回的面額
        "repurchase_cost": repurchase_cost,  # 買回付出的現金
        "repurchase_discount": repurchase_discount,
        "btc_bought_usd": bought,
        "btc_sold_usd": sold,
    }


# --------------------------------------------------------------- CLI

def main(argv: Optional[List[str]] = None) -> int:
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    conn = connect()
    if argv and argv[0] == "rebuild":
        n = rebuild(conn, verbose="-v" in argv)
        print(f"由 {len(A.find(conn, source='sec_8k'))} 份文件推出 {n} 個事件")
    rows = conn.execute(
        "SELECT family, kind, COUNT(*), MIN(effective_at), MAX(effective_at)"
        " FROM events GROUP BY family, kind ORDER BY family DESC, kind").fetchall()
    if not rows:
        print("還沒有事件 —— 先跑 python3 -m mstr_cebe.events rebuild")
        return 0
    print(f"{'家族':<12}{'種類':<24}{'筆數':>6}   期間")
    for fam, kind, n, lo, hi in rows:
        print(f"{fam:<12}{kind:<24}{n:>6}   {lo} → {hi}")
    print(f"{'合計':<36}{sum(r[2] for r in rows):>6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
