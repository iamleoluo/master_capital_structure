"""L3 — 資本操作:把事件配對成有意圖的動作。

設計圖:reference/06-architecture.md §5

**這是第一個不可能被證明的層。** 現金是可替代的 —— 你永遠無法證明
「賣幣換到的那筆錢」就是「拿去回購的那筆錢」。所以這一層不宣稱事實,
它提出配對並附上證據與信心度。

實作時的關鍵決定:**配對的依據是文件自己寫的用途,不是金額相似度。**

理由是資料說的。把「同一週同時出現賣幣與回購」當成配對訊號去看,
只有 1 週的金額對得上(2026-08-09,差 0.0026%),其餘來源都遠大於用途 ——
因為一週裡多個來源同時供給多個用途。用金額相似度去配,等於在猜。

但 8-K 的敘述句其實直接寫了用途,而且有時連金額都逐筆寫出來:

    "$52.4 million in proceeds from the bitcoin sales were used to fund
     dividends ... and $52.3 million ... to fund repurchases of STRC Stock"

那是 `stated`,不是推論。所以配對規則以它為準,金額只拿來**佐證**。

三條不可妥協的性質(設計圖 §5):
  1. 單一事件也是一個操作 —— 配不到對不是失敗
  2. 未配對的必須顯性,不准攤進任何一個操作
  3. 配對不得無中生有 —— 只能把既有事件綁在一起
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from . import events as E

SCHEMA = """
CREATE TABLE IF NOT EXISTS operations (
  op_id       TEXT PRIMARY KEY,
  combo_id    TEXT NOT NULL,      -- toolbox 的組合 id,或單一工具 id
  window_lo   TEXT NOT NULL,
  window_hi   TEXT NOT NULL,
  params      TEXT NOT NULL,      -- JSON:餵給 Tool 的參數
  confidence  REAL NOT NULL,
  rule        TEXT NOT NULL,      -- 哪一條規則認定的
  evidence    TEXT NOT NULL       -- JSON:為什麼認定它們是一組
);
CREATE TABLE IF NOT EXISTS operation_events (
  op_id    TEXT NOT NULL REFERENCES operations(op_id),
  event_id TEXT NOT NULL REFERENCES events(event_id),
  role     TEXT NOT NULL,         -- 'source' | 'use' | 'single'
  usd      REAL,                  -- 這個事件有多少金額算進這個操作
  PRIMARY KEY (op_id, event_id, role)
);
CREATE INDEX IF NOT EXISTS idx_op_window ON operations(window_lo, window_hi);
"""

# 信心度。刻意只有三檔 —— 再細分是假精確。
HIGH, MEDIUM, LOW = 0.9, 0.6, 0.3


@dataclass(frozen=True)
class Operation:
    combo_id: str
    window_lo: str
    window_hi: str
    rule: str
    confidence: float
    params: Dict = field(default_factory=dict)
    evidence: Dict = field(default_factory=dict)
    members: Sequence[tuple] = ()      # (event_id, role, usd)

    @property
    def op_id(self) -> str:
        key = f"{self.rule}|{self.window_lo}|{self.window_hi}|" + \
              "|".join(sorted(f"{e}:{r}" for e, r, _ in self.members))
        return hashlib.sha256(key.encode()).hexdigest()[:16]


def connect(path: str = None) -> sqlite3.Connection:
    conn = E.connect(path) if path else E.connect()
    conn.executescript(SCHEMA)
    return conn


# --------------------------------------------------------------- 配對

def _stated_uses(sale: dict) -> List[dict]:
    """這筆賣幣的所得,文件說了流向哪裡。沒說就回空清單 —— 不猜。

    逐筆分配優先;沒有逐筆就看整筆用途的敘述句。
    """
    alloc = sale["attrs"].get("sale_allocation") or []
    if alloc:
        return [dict(a, basis="itemised") for a in alloc if a.get("kind")]
    use = (sale["attrs"].get("sale_use") or "").strip()
    kind = E.classify_purpose(use)
    if not kind:
        return []
    return [{"usd": sale["usd"], "purpose": use, "kind": kind,
             "basis": "narrative"}]


def match_sell_to_buyback(conn: sqlite3.Connection) -> tuple:
    """賣幣 → 折價回購優先股。回傳 (完全配對的組合操作, 只支應一部分的證據)。

    依據是文件寫的用途;金額用來判斷這筆錢**支應了全部**還是**只支應一部分**。
    這個區分決定記帳方式,不只是信心度:

      全額支應(金額差 < 5%)  兩邊合併成一個組合操作,各自不再單獨成操作
      只支應一部分            兩邊維持獨立操作,文件的說法掛在賣幣那一筆上

    為什麼不能一律合併:2026-08-02 的文件寫明賣幣所得 $52.3M 用於回購,
    但那一週的回購總額是 $81.2M —— 其餘來自 ATM。硬把兩邊合併會把
    另外那 $28.9M 吃掉;硬讓兩邊都算一次又會重複計算現金流。
    """
    sales = [r for r in E.all_events(conn, kind="btc_sale") if (r["qty"] or 0)]
    repurchases = [r for r in E.all_events(conn, kind="preferred_repurchase")
                   if (r["qty"] or 0)]
    by_week: Dict[str, List[dict]] = {}
    for r in repurchases:
        by_week.setdefault(r["period_end"] or r["effective_at"], []).append(r)

    merged: List[Operation] = []
    partial: Dict[str, dict] = {}        # event_id → 證據
    for sale in sales:
        week = sale["period_end"] or sale["effective_at"]
        for use in _stated_uses(sale):
            if use["kind"] != "preferred_repurchase":
                continue
            targets = by_week.get(week, [])
            if not targets:
                # 文件說錢拿去回購,但同一週沒有回購事件 —— 不自己生一個出來
                continue
            cost = sum(-(t["usd"] or 0) for t in targets)
            stated = use["usd"] or 0.0
            gap = abs(stated - cost) / max(cost, 1.0)
            evidence = {
                "basis": use["basis"],          # itemised | narrative
                "quoted": use["purpose"][:200],
                "stated_usd": stated,
                "repurchase_cost_usd": cost,
                "amount_gap_pct": round(gap * 100, 2),
                "same_document": all(t["doc_id"] == sale["doc_id"]
                                     for t in targets),
            }
            if gap >= 0.05:
                # 只支應了一部分:記錄關係,但不合併 ——
                # 硬合併會把其他資金來源吃掉
                evidence["partial"] = True
                evidence["covered_share_pct"] = round(
                    min(stated / max(cost, 1.0), 1.0) * 100, 1)
                partial[sale["event_id"]] = evidence
                continue
            merged.append(Operation(
                combo_id="sell_to_buyback", rule="stated_sale_use",
                window_lo=sale["period_start"] or sale["effective_at"],
                window_hi=week, confidence=HIGH,
                params={"x": sale["qty"], "c": stated,
                        "F": sum((t["qty"] or 0) * 100 for t in targets)},
                evidence=evidence,
                members=[(sale["event_id"], "source", sale["usd"])]
                        + [(t["event_id"], "use", t["usd"]) for t in targets]))
    return merged, partial


def single_operations(conn: sqlite3.Connection, consumed: Sequence[str],
                      evidence_for: Dict[str, dict] = None) -> List[Operation]:
    """配不到對的動作,自己就是一個操作。

    這不是失敗處理 —— 下游因此永遠只需要處理一種型別(設計圖 §5)。
    「只支應一部分」的證據掛在這裡,資訊不會因為沒合併而消失。
    """
    done, evidence_for = set(consumed), evidence_for or {}
    out = []
    for r in E.all_events(conn, family="action"):
        if r["event_id"] in done or not (r["qty"] or 0):
            continue
        ev = dict(evidence_for.get(r["event_id"]) or
                  {"note": "沒有配對證據,單一動作即一個操作"})
        out.append(Operation(
            combo_id=E.tool_for(r["kind"], r["instrument"]),
            rule="partly_funded" if r["event_id"] in evidence_for else "unpaired",
            confidence=MEDIUM if r["event_id"] in evidence_for else 1.0,
            window_lo=r["period_start"] or r["effective_at"],
            window_hi=r["period_end"] or r["effective_at"],
            params={"qty": r["qty"], "usd": r["usd"]},
            evidence=ev,
            members=[(r["event_id"], "single", r["usd"])]))
    return out


def build(conn: sqlite3.Connection) -> List[Operation]:
    """目前只實作 sell_to_buyback,其餘維持單工具操作(設計圖第 5 步)。

    記帳規則:**每一個動作事件恰好屬於一個操作**。合併過的兩邊不再單獨出現,
    沒合併的維持獨立 —— 所以現金流既不會被吃掉,也不會被重複計算。
    """
    merged, partial = match_sell_to_buyback(conn)
    consumed = [e for op in merged for e, _, _ in op.members]
    return merged + single_operations(conn, consumed, partial)


def rebuild(conn: sqlite3.Connection) -> int:
    conn.execute("DELETE FROM operation_events")
    conn.execute("DELETE FROM operations")
    ops = build(conn)
    for op in ops:
        conn.execute(
            "INSERT OR REPLACE INTO operations (op_id, combo_id, window_lo,"
            " window_hi, params, confidence, rule, evidence)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (op.op_id, op.combo_id, op.window_lo, op.window_hi,
             json.dumps(op.params, ensure_ascii=False, sort_keys=True),
             op.confidence, op.rule,
             json.dumps(op.evidence, ensure_ascii=False, sort_keys=True)))
        for event_id, role, usd in op.members:
            conn.execute(
                "INSERT OR REPLACE INTO operation_events"
                " (op_id, event_id, role, usd) VALUES (?,?,?,?)",
                (op.op_id, event_id, role, usd))
    conn.commit()
    return len(ops)


# --------------------------------------------------------------- 對帳

def reconcile(conn: sqlite3.Connection) -> Dict:
    """現金流對帳:每一個動作事件都要**恰好**落在一個操作裡。

    驗收條件(設計圖 §5):配對不得無中生有,也不得吃掉或重複計算任何流量。
    """
    actions = {r["event_id"]: (r["usd"] or 0.0)
               for r in E.all_events(conn, family="action") if (r["qty"] or 0)}
    counts: Dict[str, int] = {}
    for (event_id,) in conn.execute("SELECT event_id FROM operation_events"):
        counts[event_id] = counts.get(event_id, 0) + 1

    missing = sorted(set(actions) - set(counts))
    invented = sorted(set(counts) - set(actions))
    doubled = sorted(e for e, n in counts.items() if n > 1 and e in actions)
    op_usd = sum(r[0] or 0.0 for r in conn.execute(
        "SELECT usd FROM operation_events"))
    return {
        "actions": len(actions),
        "covered": len(set(counts) & set(actions)),
        "missing": missing, "invented": invented, "doubled": doubled,
        "action_usd": sum(actions.values()),
        "operation_usd": op_usd,
        "usd_gap": op_usd - sum(actions.values()),
        "ok": not missing and not invented and not doubled
             and abs(op_usd - sum(actions.values())) < 1.0,
    }


def summary(conn: sqlite3.Connection) -> List[dict]:
    rows = conn.execute(
        "SELECT combo_id, rule, COUNT(*) n, MIN(window_lo), MAX(window_hi),"
        " AVG(confidence) FROM operations GROUP BY combo_id, rule"
        " ORDER BY rule DESC, combo_id").fetchall()
    return [{"combo_id": r[0], "rule": r[1], "n": r[2],
             "from": r[3], "to": r[4], "confidence": round(r[5], 2)}
            for r in rows]


def main(argv: Optional[List[str]] = None) -> int:
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    conn = connect()
    if argv and argv[0] == "rebuild":
        print(f"建出 {rebuild(conn)} 個操作")
    rows = summary(conn)
    if not rows:
        print("還沒有操作 —— 先跑 python3 -m mstr_cebe.operations rebuild")
        return 0
    print(f"{'規則':<20}{'組合':<22}{'個數':>5}{'平均信心':>9}   期間")
    for r in rows:
        print(f"{r['rule']:<20}{r['combo_id']:<22}{r['n']:>5}"
              f"{r['confidence']:>9.2f}   {r['from']} → {r['to']}")
    rec = reconcile(conn)
    print(f"\n對帳:{rec['covered']}/{rec['actions']} 個動作被涵蓋"
          f"{'' if rec['ok'] else '  ⚠️ 有遺漏或憑空出現'}")
    print(f"現金流:動作 ${rec['action_usd']/1e6:,.1f}M  "
          f"操作 ${rec['operation_usd']/1e6:,.1f}M  差 ${rec['usd_gap']:,.2f}")
    for op in (o for o in build(conn) if o.rule != "unpaired"):
        ev = op.evidence
        print(f"\n配對 {op.combo_id}  {op.window_lo} → {op.window_hi}"
              f"  信心 {op.confidence}")
        kind = "只支應一部分" if ev.get("partial") else "全額支應"
        print(f"  {kind}  依據:{ev['basis']}  金額差 {ev['amount_gap_pct']}%"
              f"  同一份文件:{ev['same_document']}")
        print(f"  文件原話:「{ev['quoted'][:110]}」")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ---------------------------------------------------------------------------
# 操作 → toolbox 工具:把 L3 的 (qty, usd) 翻成代數的參數
# ---------------------------------------------------------------------------

# 優先股的清算優先權。STRC/STRF/STRK/STRD 都是每股 $100。
# ⚠️ 普通股沒有面額 —— 真的出現普通股庫藏時這個對應不成立,所以要擋掉。
PAR_PER_SHARE = 100.0


def tool_params(op: Operation, conn=None) -> Optional[tuple]:
    """這個操作對應到哪一把 toolbox 工具、參數是多少。

    L3 記的是 `(qty, usd)` —— 文件直接揭露的兩個量;toolbox 的參數是
    `(c, F, n, P, x)` —— 代數需要的量。兩者之間的翻譯只能寫在一個地方,
    否則「網站顯示的效果」與「測試驗的效果」會各自漂開。

    回傳 `(tool, kwargs)`;翻不過去就回 None(不要硬湊一個看起來合理的)。
    """
    from . import toolbox as T

    p = op.params
    qty, usd = p.get("qty") or 0.0, p.get("usd") or 0.0

    if op.combo_id == "sell_to_buyback":
        return T.SELL_TO_BUYBACK, {"x": p["x"], "F": p["F"]}
    if op.combo_id == "buy_btc":
        return T.BUY_BTC, {"c": abs(usd)}          # usd 為負(現金流出)
    if op.combo_id == "sell_btc":
        return T.SELL_BTC, {"x": qty}
    if op.combo_id == "issue_preferred":
        return T.ISSUE_PREFERRED, {"c": usd, "F": qty * PAR_PER_SHARE}
    if op.combo_id == "buyback_preferred":
        if conn is not None and _touches_common(op, conn):
            return None                            # 普通股沒有面額,見上
        return T.BUYBACK_PREFERRED, {"c": abs(usd), "F": qty * PAR_PER_SHARE}
    if op.combo_id == "common_atm":
        if not qty:
            return None                            # 沒有股數就算不出每股價
        return T.COMMON_ATM, {"n": qty, "P": abs(usd) / qty}
    return None


def _touches_common(op: Operation, conn) -> bool:
    ids = [m[0] for m in op.members]
    if not ids:
        return False
    q = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT DISTINCT instrument FROM events WHERE event_id IN ({q})", ids)
    return any(r[0] == "MSTR" for r in rows)


def effect_of(op: Operation, state, conn=None) -> Optional[dict]:
    """這個操作對兩把尺的效果。**用 toolbox 算,不自己寫一份。**

    `state` 是操作發生當下的資本結構 —— 效果取決於當時的規模,
    同一筆 $1 億在求償權 $5B 與 $20B 的時候意義完全不同。
    """
    from . import toolbox as T

    tp = tool_params(op, conn)
    if tp is None:
        return None
    tool, kw = tp
    eff = T.effect(tool, state, **kw)
    verdict = None
    if tool.accretive is not None:
        verdict = bool(tool.accretive(state, kw))
    return {"dB": eff["dB"], "dE": eff["dE"], "accretive": verdict,
            "tool": tool.id, "params": kw}
