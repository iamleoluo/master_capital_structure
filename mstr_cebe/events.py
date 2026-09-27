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
import os
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
  granularity  TEXT NOT NULL DEFAULT 'week',   -- 'week' | 'quarter' | 'instant'
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
    "convert_issue":          ("action", "issue_preferred"),
    "convert_repurchase":     ("action", "buyback_preferred"),
    "dividend_payment":       ("action", "carry"),
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
    # 週揭露(8-K)與季揭露(XBRL)描述的是同一批動作,粒度不同。
    # 視圖要能分辨,才不會把兩種粒度疊在一起重複計算。
    #
    # ⚠️ 這個欄位描述的是**流量涵蓋的期間**。觀測是瞬時的存量,沒有期間,
    #    一律是 'instant'(見 __post_init__)—— 讓觀測繼承流量列的粒度是
    #    歸類錯誤,而且有實害:季末那份 8-K(Item 2.02)附的季合計列帶著
    #    正確的季末餘額,卻因為被標成 'quarter' 而被存量視圖過濾掉,
    #    結果 2025-03-31 的持幣量長期由 data.py 一筆手工估值頂替。
    granularity: str = "week"
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if KINDS[self.kind][0] == "observation":
            object.__setattr__(self, "granularity", "instant")

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

def _migrate(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(events)")}
    if cols and "granularity" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN granularity TEXT"
                     " NOT NULL DEFAULT 'week'")
        conn.commit()


def connect(path: str = A.DEFAULT_PATH) -> sqlite3.Connection:
    """事件與文件放同一個檔案 —— 出處的外鍵才是真的。

    層次的分界不在檔案,而在「documents 永遠不得有衍生欄位」這條規則上。
    事件隨時可以整批刪掉再由文件重算(見 rebuild()),這就是可重放。
    """
    conn = A.connect(path)
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def insert(conn: sqlite3.Connection, events: Iterable[Event]) -> int:
    n = 0
    for e in events:
        conn.execute(
            "INSERT OR REPLACE INTO events (event_id, kind, family, instrument,"
            " effective_at, period_start, period_end, qty, unit, usd,"
            " unit_price, attrs, doc_id, locator, extraction, granularity,"
            " confidence) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (e.event_id, e.kind, e.family, e.instrument, e.effective_at,
             e.period_start, e.period_end, e.qty, e.unit, e.usd, e.unit_price,
             json.dumps(e.attrs, ensure_ascii=False, sort_keys=True),
             e.doc_id, e.locator, e.extraction, e.granularity, e.confidence))
        n += 1
    conn.commit()
    return n


def all_events(conn: sqlite3.Connection, *, kind: Optional[str] = None,
               family: Optional[str] = None,
               granularity: Optional[str] = "week") -> List[dict]:
    """取事件,附上該文件的申報日 —— 「後蓋前」的排序要靠它。

    granularity 預設只取週粒度。季粒度描述的是同一批動作,兩種混在一起
    會重複計算 —— 要取季的就明講,或傳 None 取全部。

    **觀測不受這個過濾器管。** granularity 描述的是流量涵蓋的期間,
    而觀測是瞬時的存量(granularity='instant'),既不會被重複計算,
    也不屬於任何一種粒度。把它們一起濾掉會讓存量視圖看不到季末那些點。
    """
    where, args = [], []
    if granularity:
        where.append("(e.family = 'observation' OR e.granularity = ?)")
        args.append(granularity)
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


# --------------------------------------------------------------- 買幣的資金來源

# 10-Q/10-K 的註腳直接寫出買幣的錢從哪來,例如:
#   "(a) In the first quarter of 2025, we purchased bitcoin using $4.37 billion
#    of the net proceeds from ATM sales of class A common stock, $1.99 billion
#    ... from our issuance of the 2030B Convertible Notes, ..."
# 這與賣幣的 sale_allocation 完全對稱 —— 一邊是錢去哪,一邊是錢從哪來,
# 而且兩邊都是 stated。L3 的配對靠它,所以在 L2 解析成結構。
_FUND_QUARTER = re.compile(
    r"In the (first|second|third|fourth) quarter of (\d{4}),\s*"
    r"we purchased bitcoin using (.+?)\.(?!\d)", re.I)
_FUND_YEAR = re.compile(
    r"During (\d{4}),\s*we purchased bitcoin using (.+?)\.(?!\d)", re.I)
# 句號後面接數字的是小數點,不是句尾 —— 少了 (?!\d) 會在 "$179." 斷掉
_FUND_PART = re.compile(
    r"\$([\d,.]+)\s*(million|billion)\s+of\s+(?:the\s+)?"
    r"([^$]+?)(?=,\s*\$|,?\s+and\s+\$|$)", re.I)

_QUARTER_NO = {"first": 1, "second": 2, "third": 3, "fourth": 4}
_QUARTER_END = {1: ("01-01", "03-31"), 2: ("04-01", "06-30"),
                3: ("07-01", "09-30"), 4: ("10-01", "12-31")}


def _funding_instrument(text: str) -> Optional[str]:
    """把來源敘述歸到一個標的。認不出來回 None —— 不猜。"""
    t = text.lower()
    for sym in ("strk", "strf", "strc", "strd", "stre"):
        if sym in t:
            return sym.upper()
    if "convertible" in t:
        return "CONVERTIBLE"
    if "common stock" in t or "class a" in t:
        return "MSTR"
    if "excess cash" in t or "cash flow from operations" in t:
        return "CASH"          # 自有現金,不是融資來源
    return None


def parse_funding_attribution(text: str) -> List[Dict]:
    """解析買幣資金來源的註腳。10-Q 給到季,10-K 只給到年。"""
    out = []

    def parts_of(body: str) -> List[Dict]:
        got = []
        for amount, unit, src in _FUND_PART.findall(body):
            usd = float(amount.replace(",", "")) * (1e9 if unit.lower() == "billion"
                                                    else 1e6)
            got.append({"usd": usd, "source": src.strip()[:120],
                        "instrument": _funding_instrument(src)})
        return got

    for q, year, body in _FUND_QUARTER.findall(text):
        lo, hi = _QUARTER_END[_QUARTER_NO[q.lower()]]
        got = parts_of(body)
        if got:
            out.append({"period_start": f"{year}-{lo}", "period_end": f"{year}-{hi}",
                        "granularity": "quarter", "sources": got})
    for year, body in _FUND_YEAR.findall(text):
        got = parts_of(body)
        if got:
            out.append({"period_start": f"{year}-01-01",
                        "period_end": f"{year}-12-31",
                        "granularity": "year", "sources": got})
    return out


def derive_funding(conn: sqlite3.Connection, *, verbose: bool = False) -> int:
    """從 10-Q/10-K 的註腳取出買幣的資金來源,存成帶 funding_allocation 的
    買幣事件。

    **粒度比週資料粗,所以不會進週聚合視圖** —— 它補的是 L3 的配對證據,
    不是拿來重算週報表的。
    """
    docs = [m for m in A.find(conn) if m.source in ("sec_10q", "sec_10k")]
    # 同一個期間被多份申報寫到時取最新那份(與週資料同規則)
    best: Dict[tuple, tuple] = {}
    for m in sorted(docs, key=lambda x: x.filed_at):
        text = _plain_text(A.text(conn, m.doc_id))
        for rec in parse_funding_attribution(text):
            best[(rec["period_end"], rec["granularity"])] = (m, rec)

    out: List[Event] = []
    for (period_end, gran), (m, rec) in sorted(best.items()):
        total = sum(p["usd"] for p in rec["sources"])
        out.append(Event(
            kind="btc_purchase", instrument="BTC",
            effective_at=period_end,
            period_start=rec["period_start"], period_end=period_end,
            qty=None, unit="USD", usd=-total,
            attrs={"funding_allocation": rec["sources"],
                   "source_form": m.source, "accession": m.accession},
            doc_id=m.doc_id,
            locator=f"funding/{rec['period_start']}..{period_end}",
            granularity=gran))
        if verbose:
            print(f"  {rec['period_start']} → {period_end} ({gran})"
                  f"  ${total/1e9:>6.2f}B  "
                  + " ".join(f"{p['instrument'] or '?'}={p['usd']/1e9:.2f}"
                             for p in rec["sources"]))
    return insert(conn, out)


# --------------------------------------------------------------- 由文件推導

def _span_days(start: Optional[str], end: str) -> Optional[int]:
    """這筆紀錄涵蓋幾天。用來分辨週列與季末的合計列。"""
    if not start:
        return None
    return (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days


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
            # 季末的 8-K 會附一列「該季合計」,格式與週列一模一樣。
            # 把它當週紀錄會與那一季的各週重複計算 —— 實測 2025 年因此
            # 多算了 $19.4B(10-K 宣稱全年 $22.47B,現行管線算出 $35.88B)。
            # 它不是壞資料,只是粒度不同,所以用 granularity 分開而不是丟掉。
            # 跨度分布很乾淨:正常週列 1–7 天(另有一筆 13 天的兩週期),
            # 季度彙總 89–91 天,中間完全沒有東西。門檻取 45 天。
            span = _span_days(rec.get("week_start"), rec["week_end"])
            gran = "week" if span is None or span <= 45 else "quarter"
            out.append(Event(
                granularity=gran,
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


# --------------------------------------------------------------- 季頻(XBRL)

# XBRL 標籤 → (事件種類, 標的)。設計圖 §4 的事件種類表早就列了這幾項,
# 所以這不是為了 10-Q 開的特例 —— 是同一套模型換一個來源填。
XBRL_FLOWS = {
    "ProceedsFromIssuanceOfCommonStock":
        ("atm_issue", "MSTR"),
    "ProceedsFromIssuanceOfPreferredStockAndPreferenceStock":
        ("atm_issue", "PREFERRED"),      # XBRL 是各系列合計,沒有拆開
    "ProceedsFromConvertibleDebt":
        ("convert_issue", "CONVERTIBLE"),
    "RepaymentsOfConvertibleDebt":
        ("convert_repurchase", "CONVERTIBLE"),
    "PaymentsOfDividendsPreferredStockAndPreferenceStock":
        ("dividend_payment", "PREFERRED"),
    "PaymentsOfDividendsCommonStock":
        ("dividend_payment", "MSTR"),
}

# 現金流的方向:募資流入為正,付款流出為負。
_XBRL_SIGN = {"atm_issue": +1, "convert_issue": +1,
              "convert_repurchase": -1, "dividend_payment": -1}


def _discrete_periods(facts: List[dict]) -> List[dict]:
    """把 XBRL 的期間整理成互不重疊的單季金額。

    **這是這一層最容易出錯的地方**,而且錯法有兩種。

    第一種:大部分事實是**年初至今的累計**,不是單季 ——

        2025-01-01 → 03-31  $1,337M   (Q1)
        2025-01-01 → 06-30  $2,948M   (上半年,不是 Q2!)
        2025-01-01 → 09-30  $5,888M

    直接加總會把同一筆錢算好幾次,所以同年度內要逐筆相減:
    Q2 = 2,948 − 1,337 = 1,611。

    第二種:**有些事實本身就是單季**(起日不是年度起日)。它們與上面
    相減出來的結果期間重疊,一起收下就會重複。公司自己報的單季值優先 ——
    那是 stated,相減出來的是 derived。

    同一個期間被多份申報重述時取最新的(與週資料的「後蓋前」同規則)。
    """
    # 去重:同一個 (start, end) 取申報最新的那一筆
    best: Dict[tuple, dict] = {}
    for f in facts:
        if not f.get("start"):
            continue
        key = (f["start"], f["end"])
        prev = best.get(key)
        if prev is None or (f.get("filed", ""), f.get("accn", "")) > \
                (prev.get("filed", ""), prev.get("accn", "")):
            best[key] = f

    # 會計年度起日 = 每年最早出現的起日
    fy_start = {}
    for f in best.values():
        y = f["start"][:4]
        fy_start[y] = min(fy_start.get(y, f["start"]), f["start"])

    cumulative, discrete = [], []
    for f in best.values():
        (cumulative if f["start"] == fy_start[f["start"][:4]]
         else discrete).append(f)

    out = []
    by_year: Dict[str, List[dict]] = {}
    for f in cumulative:
        by_year.setdefault(f["start"], []).append(f)
    for start, rows in by_year.items():
        rows.sort(key=lambda x: x["end"])
        prev_end, prev_val = start, 0.0
        for f in rows:
            out.append({**f, "period_start": prev_end, "period_end": f["end"],
                        "val": f["val"] - prev_val, "ytd_val": f["val"],
                        "extraction": "derived"})   # 相減出來的
            prev_end, prev_val = f["end"], f["val"]

    # 公司自己報的單季值蓋掉相減出來的(以結束日為準)
    by_end = {f["period_end"]: f for f in out}
    for f in discrete:
        by_end[f["end"]] = {**f, "period_start": f["start"],
                            "period_end": f["end"], "ytd_val": None,
                            "extraction": "stated"}
    return sorted(by_end.values(), key=lambda x: x["period_end"])


def derive_xbrl(conn: sqlite3.Connection, *, verbose: bool = False) -> int:
    """把 XBRL companyfacts 的資金流拆成季頻事件。

    補的是週 8-K 看不到的那些:可轉債發行與償還(事件數原本是 0)、
    早於逐週揭露的募資、以及實際付出的股息(原本只有用年率估的常數)。
    """
    docs = [m for m in A.find(conn, source="sec_xbrl")]
    if not docs:
        raise RuntimeError("檔案庫裡沒有 XBRL —— 先跑 "
                           "python3 -m mstr_cebe.archive facts")
    doc = max(docs, key=lambda m: m.fetched_at)
    facts = json.loads(A.text(conn, doc.doc_id))["facts"]["us-gaap"]

    out: List[Event] = []
    for tag, (kind, instrument) in XBRL_FLOWS.items():
        if tag not in facts:
            continue
        rows = facts[tag]["units"].get("USD", [])
        for f in _discrete_periods(rows):
            if not f["val"]:
                continue
            usd = abs(f["val"]) * _XBRL_SIGN[kind]
            out.append(Event(
                kind=kind, instrument=instrument,
                effective_at=f["period_end"],
                period_start=f["period_start"], period_end=f["period_end"],
                qty=abs(f["val"]), unit="USD", usd=usd,
                attrs={"xbrl_tag": tag, "ytd_usd": f["ytd_val"],
                       "source_accession": f.get("accn"),
                       "form": f.get("form"), "fp": f.get("fp")},
                doc_id=doc.doc_id,
                locator=f"xbrl/{tag}/{f['period_start']}..{f['period_end']}",
                extraction=f["extraction"], granularity="quarter"))
            if verbose:
                print(f"  {f['period_start']} → {f['period_end']}  {kind:<20}"
                      f"{instrument:<12}${usd/1e6:>10,.1f}M")
    return insert(conn, out)


def rebuild(conn: sqlite3.Connection, *, with_xbrl: bool = True, **kw) -> int:
    """整批刪掉再由文件重算 —— 這就是「每層可獨立重放」的實證。"""
    conn.execute("DELETE FROM events")
    conn.commit()
    n = derive(conn, **kw)
    if with_xbrl and A.find(conn, source="sec_xbrl"):
        n += derive_xbrl(conn, verbose=kw.get("verbose", False))
    if any(m.source in ("sec_10q", "sec_10k") for m in A.find(conn)):
        n += derive_funding(conn, verbose=kw.get("verbose", False))
    return n


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


# 存量觀測的兩種出處。專用的持有量表格優先於活動表尾欄 ——
# 同一天兩者都有時前者是主要揭露,後者是附帶欄位。
_HOLDINGS_LOCATORS = ("holdings/", "activity-holdings/")


def weekly_holdings(conn: sqlite3.Connection) -> List[list]:
    """[[日期, 顆數], ...] —— 舊 btc_holdings_weekly.json 的超集。

    比舊檔多了每季第一份 8-K(Item 2.02 財報預告)活動表尾欄帶的季末餘額。
    舊檔只收 `holdings/`,把 `activity-holdings/` 濾掉了,而 2025 三個季末
    (03-31 / 06-30 / 09-30)**只**出現在後者 —— 沒有任何逐週觀測落在那些
    日期上,缺口長期由 data.py 的手工錨點頂替,其中 2025-03-31 那筆把申報
    當日的餘額(555,450→四捨五入 550,000)誤標成季末(實際 528,185)。
    """
    seen: Dict[str, tuple] = {}
    for r in all_events(conn, kind="holdings_observation"):
        if not r["locator"].startswith(_HOLDINGS_LOCATORS):
            continue
        # 排序鍵:申報日越新越優先,同日則專用表格優先於活動表尾欄
        rank = (r["filed"], r["locator"].startswith("holdings/"))
        prev = seen.get(r["effective_at"])
        if prev is None or rank >= prev[0]:
            seen[r["effective_at"]] = (rank, int(r["qty"]))
    return [[d, v] for d, (_, v) in sorted(seen.items())]


def weekly_activity(conn: sqlite3.Connection) -> List[dict]:
    """逐週買賣 —— 等同舊的 btc_activity_weekly.json。"""
    rows = [r for r in all_events(conn)
            if r["kind"] in ("btc_purchase", "btc_sale")]
    out = []
    for period, evs in sorted(_latest_per_period(rows).items()):
        e = evs[0]
        # 「本週無買賣」的 8-K 也會出一列(qty=0),目前被歸成 btc_sale ——
        # 乘上 -1 會產生 -0.0,序列化出去就與舊檔不同。判斷要帶上 qty。
        sign = -1 if (e["kind"] == "btc_sale" and e["qty"]) else 1
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

# ---------------------------------------------------- 粒度解析(粗只能補洞)

# 由細到粗。同一批動作可以被三種粒度描述:8-K 的週表、10-Q 的季表、
# 10-K 的年表。三者**不得相加**。
GRAIN_ORDER: Dict[str, int] = {"week": 0, "quarter": 1, "year": 2}

# XBRL 只給「優先股」的合計,8-K 則逐系列列出。要比較涵蓋範圍就得先對齊 ——
# 這個對照只用於粒度解析,事件本身的 instrument 不變。
PREFERRED_SERIES = ("STRK", "STRF", "STRD", "STRC", "STRE")


def flow_group(kind: str, instrument: str) -> tuple:
    """粒度解析時的比較單位。"""
    if kind == "atm_issue" and instrument in PREFERRED_SERIES:
        return (kind, "PREFERRED")
    return (kind, instrument)


@dataclass(frozen=True)
class Resolved:
    """一個事件在「不得重複計算」的前提下,實際貢獻多少資金流。"""
    kind: str
    group: str
    granularity: str
    period_start: str
    period_end: str
    stated_usd: float       # 文件對這段期間講的數字
    covered_usd: float      # 已經被更細的粒度算過的部分
    usd: float              # 淨貢獻 = stated − covered(補洞的部分)
    doc_id: str
    locator: str
    conflict: bool = False  # 細粒度反而超出粗粒度 —— 見下方說明


def _covers(inner: dict, outer: dict) -> bool:
    """inner 的期間真包含於 outer(相同期間不算,那是同一件事的兩份文件)。"""
    same = inner["ps"] == outer["ps"] and inner["pe"] == outer["pe"]
    return (not same) and outer["ps"] <= inner["ps"] and inner["pe"] <= outer["pe"]


def resolve_flows(conn: sqlite3.Connection, *, tol: float = 0.02) -> List[Resolved]:
    """把三種粒度解析成一組互不重疊的資金流。

    規則只有一條:**粗粒度只能補洞,不能與細粒度相加。**

      1. 同一 (種類, 標的, 粒度, 期間) 有多份文件 → 取申報日最新的那份。
         2025 三季的買幣就是這樣:季末的 8-K(Item 2.02)給顆數,
         三個月後的 10-Q 給資金來源,兩邊差 0.027%,但只能算一次。
      2. 由細到粗:每個事件的淨貢獻 = 自身 − 內部所有更細事件的**淨貢獻**
         (要用淨貢獻遞迴,不是原始金額,否則季與週會被重複扣掉)。
      3. 淨貢獻若與自身反號超過 `tol` → 細粒度超出粗粒度。粗粒度是用來
         補洞的,補不出負的洞,所以貢獻取 0 並標記 conflict,交由上層看見。

    驗證:2024 與 2025 的**年**頻買幣,經過這個規則之後淨貢獻趨近於零 ——
    也就是年報的數字被季報與週報完整解釋掉了,三種粒度互相對得起來。
    """
    raw: List[dict] = []
    for r in all_events(conn, family="action", granularity=None):
        raw.append({
            "kind": r["kind"], "inst": r["instrument"], "gran": r["granularity"],
            "ps": r["period_start"] or r["effective_at"],
            "pe": r["period_end"] or r["effective_at"],
            "usd": r["usd"] or 0.0, "filed": r["filed"],
            "doc_id": r["doc_id"], "locator": r["locator"],
        })

    # (1) 後蓋前。鍵用**原始**標的 —— 用分組後的標的會讓同一週的
    #     STRK 與 STRC 互相蓋掉。
    best: Dict[tuple, dict] = {}
    for r in raw:
        k = (r["kind"], r["inst"], r["gran"], r["ps"], r["pe"])
        if k not in best or r["filed"] > best[k]["filed"]:
            best[k] = r
    rows = list(best.values())

    # (2) 由細到粗遞迴
    done: List[dict] = []
    out: List[Resolved] = []
    for r in sorted(rows, key=lambda x: (GRAIN_ORDER[x["gran"]], x["ps"], x["pe"])):
        g = flow_group(r["kind"], r["inst"])
        covered = sum(x["contrib"] for x in done
                      if flow_group(x["kind"], x["inst"]) == g and _covers(x, r))
        contrib = r["usd"] - covered
        # (3) 補不出負的洞
        conflict = bool(r["usd"]) and (contrib / r["usd"]) < -tol
        if conflict:
            contrib = 0.0
        r["contrib"] = contrib
        done.append(r)
        out.append(Resolved(
            kind=r["kind"], group=g[1], granularity=r["gran"],
            period_start=r["ps"], period_end=r["pe"],
            stated_usd=r["usd"], covered_usd=covered, usd=contrib,
            doc_id=r["doc_id"], locator=r["locator"], conflict=conflict))
    return out


def resolved_between(conn: sqlite3.Connection, lo: str, hi: str,
                     *, kind: Optional[str] = None) -> Dict[str, float]:
    """區間內、已解析過粒度的資金流,按 (種類, 分組標的) 加總。

    與 `flows_between()` 的差別:那一支只看週粒度(歸因層的既有口徑),
    這一支把季與年的補洞部分也算進來,所以涵蓋 8-K 還沒開始揭露的早期。
    """
    total: Dict[str, float] = {}
    for r in resolve_flows(conn):
        if not (lo <= r.period_end <= hi) or not r.usd:
            continue
        if kind and r.kind != kind:
            continue
        total[f"{r.kind}:{r.group}"] = total.get(f"{r.kind}:{r.group}", 0.0) + r.usd
    return total


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

# 週視圖 → 它序列化成的 web/raw 檔名。模型讀的是這些檔,所以視圖改了
# 就要 export 一次,否則事件層修好了、下游卻還吃著舊檔。
RAW_VIEWS = {
    "weekly_holdings":  "btc_holdings_weekly.json",
    "weekly_activity":  "btc_activity_weekly.json",
    "weekly_atm":       "atm_weekly.json",
    "weekly_repurchase": "repurchase_weekly.json",
    "weekly_reserve":   "reserve_weekly.json",
}


def export_raw(conn: sqlite3.Connection, root: Optional[str] = None) -> Dict[str, int]:
    """把週視圖寫回 web/raw。

    這些檔案原本是爬蟲的直接輸出,現在改由事件層產生 —— 真相是檔案庫裡的
    文件,web/raw 只是視圖的序列化。這樣「重解文件」的修正才會流到下游。
    """
    root = root or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "raw")
    out: Dict[str, int] = {}
    for view, name in RAW_VIEWS.items():
        rows = globals()[view](conn)
        with open(os.path.join(root, name), "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False)
        out[name] = len(rows)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    conn = connect()
    if argv and argv[0] == "rebuild":
        n = rebuild(conn, verbose="-v" in argv)
        print(f"由 {len(A.find(conn, source='sec_8k'))} 份文件推出 {n} 個事件")
    if argv and argv[0] in ("export", "rebuild"):
        for name, n in export_raw(conn).items():
            print(f"  寫出 web/raw/{name}  {n} 列")
    rows = conn.execute(
        "SELECT granularity, family, kind, COUNT(*), MIN(effective_at),"
        " MAX(effective_at) FROM events GROUP BY granularity, family, kind"
        " ORDER BY granularity, family DESC, kind").fetchall()
    if not rows:
        print("還沒有事件 —— 先跑 python3 -m mstr_cebe.events rebuild")
        return 0
    print(f"{'粒度':<10}{'家族':<12}{'種類':<22}{'筆數':>6}   期間")
    for gran, fam, kind, n, lo, hi in rows:
        print(f"{gran:<10}{fam:<12}{kind:<22}{n:>6}   {lo} → {hi}")
    print(f"{'合計':<50}{sum(r[3] for r in rows):>6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
