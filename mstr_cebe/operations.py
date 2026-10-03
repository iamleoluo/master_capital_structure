"""L3 — 資本操作:把事件配對成有意圖的動作。

設計圖:reference/06-architecture.md §5

**這是第一個不可能被證明的層。** 現金是可替代的 —— 你永遠無法證明
「賣幣換到的那筆錢」就是「拿去回購的那筆錢」。所以這一層不宣稱事實,
它提出配對並附上證據與信心度。

配對的依據分兩級,強弱不同:

  1. **文件明寫用途**(信心 0.9)。8-K 的敘述句有時連金額都逐筆寫出來:
       "$52.4 million in proceeds from the bitcoin sales were used to fund
        dividends ... and $52.3 million ... to fund repurchases of STRC Stock"
     那是 `stated`,不是推論。

  2. **金額**(信心 0.8)。一來源對一用途而且金額吻合,或多個來源的
     **加總**等於用途 —— 後者不是「不知道是哪一個」,是**兩個都是**,
     加總對得上就證明了分配。

> ⚠️ **這裡曾經有一條錯的規則。** 原本寫「配對的依據是文件寫的用途,
>    **不是**金額相似度」,理由是「把同一週同時出現賣幣與回購當訊號,
>    只有 1 週的金額對得上」。
>
>    那個推論的錯在**樣本只有一種配對**。賣幣→回購 確實配不起來,
>    但從沒測過 ATM→買幣 —— 而那才是主要的流向。2026-10-03 量過:
>
>      一來源 → 一用途   38 週,14 週金額差 ≤ 5%
>      兩來源 → 一用途   19 週,13 週來源加總 ≈ 用途(中位差 0.5%)
>
>    而且差距的分布是**雙峰的**:一群貼在 0 附近、一群在 50% 以上,
>    中間幾乎是空的。「配得上」與「配不上」自己分開,門檻怎麼取都差不多。
>
>    更根本的理由:**文件寫不寫是揭露的編輯決定,錢怎麼流不會因為沒寫
>    就不一樣。** 買賣才是真實的。

金額在什麼時候**不**算證據:加總也對不上的時候。那個落差本身是資訊
(錢進了儲備、或某個來源那時還沒逐週揭露),不該被硬湊掉。

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
HIGH, MEDIUM_HIGH, MEDIUM, LOW = 0.9, 0.8, 0.6, 0.3


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


# ---------------------------------------------------------------------------
# 依金額配對
# ---------------------------------------------------------------------------
#
# 原本的規則是「看文件寫的用途,不看金額相似度」。那條規則寫的時候站得住 ——
# 現金是可替代的,一週裡多個來源同時供給多個用途,金額對得上可能只是巧合。
#
# 但量過之後它不成立。實測 2026-10-03:
#
#   一來源 → 一用途   38 週,其中 14 週金額差 ≤ 5%
#   兩來源 → 一用途   19 週,其中 13 週**來源加總** ≈ 用途(中位差 0.5%)
#
# 而且差距的分布是**雙峰的**:一群貼在 0 附近,一群在 50% 以上,中間幾乎空的。
# 「配得上」與「配不上」自己分開,門檻怎麼取都差不多。
#
# 更要緊的是第二列:兩個來源不是「不知道是哪一個」,是**兩個都是** ——
# 加總等於用途就證明了分配。那不是模糊,是答案。
#
# 所以改成:**金額是證據,只是比文件明寫弱一級。** 文件寫不寫是揭露的
# 編輯決定,錢怎麼流不會因為沒寫就不一樣。

PREFERRED = ("STRK", "STRF", "STRD", "STRC", "STRE")
AMOUNT_TOL = 0.05        # 雙峰之間的空檔很寬,5% 與 20% 的結果幾乎一樣

# (來源工具, 用途工具) → 組合 id
PAIR_COMBO = {
    ("common_atm", "buy_btc"): "atm_to_btc",
    ("issue_preferred", "buy_btc"): "preferred_to_btc",
    ("common_atm", "buyback_preferred"): "atm_to_buyback",
    ("sell_btc", "buyback_preferred"): "sell_to_buyback",
}


def _week_flows(conn: sqlite3.Connection, skip: set) -> Dict[str, tuple]:
    """每一週的來源與用途,按工具分組。`skip` 是已經被文件配對吃掉的事件。"""
    src: Dict[str, Dict[str, list]] = {}
    use: Dict[str, Dict[str, list]] = {}
    for r in E.all_events(conn, family="action"):
        if r["event_id"] in skip or not (r["usd"] or 0):
            continue
        wk = r["period_end"] or r["effective_at"]
        k = r["kind"]
        if k == "atm_issue":
            tool = "common_atm" if r["instrument"] == "MSTR" else "issue_preferred"
            src.setdefault(wk, {}).setdefault(tool, []).append(r)
        elif k == "btc_sale":
            src.setdefault(wk, {}).setdefault("sell_btc", []).append(r)
        elif k == "btc_purchase":
            use.setdefault(wk, {}).setdefault("buy_btc", []).append(r)
        elif k == "preferred_repurchase":
            use.setdefault(wk, {}).setdefault("buyback_preferred", []).append(r)
    return {wk: (src.get(wk, {}), use.get(wk, {}))
            for wk in set(src) | set(use)}


def _amount(rows: list) -> float:
    return sum(abs(r["usd"] or 0) for r in rows)


def _combo_params(combo: str, srcs: list, uses: list, share: float) -> Dict:
    """這一組配對餵給 toolbox 的參數。`share` 是這個來源佔用途的比例。"""
    c = _amount(srcs) * 1.0
    n = sum(r["qty"] or 0 for r in srcs)
    if combo == "atm_to_btc":
        return {"n": n, "P": c / n} if n else {}
    if combo == "preferred_to_btc":
        return {"c": c, "F": n * PAR_PER_SHARE}
    if combo == "atm_to_buyback":
        f = sum((u["qty"] or 0) for u in uses) * PAR_PER_SHARE * share
        d = 1 - c / f if f else 0.0
        return {"n": n, "P": c / n, "d": d} if n and f else {}
    if combo == "sell_to_buyback":
        return {"x": sum(r["qty"] or 0 for r in srcs),
                "F": sum((u["qty"] or 0) for u in uses) * PAR_PER_SHARE * share}
    return {}


def match_by_amount(conn: sqlite3.Connection, skip: set = frozenset(),
                    tol: float = AMOUNT_TOL) -> tuple:
    """來源加總 ≈ 用途加總的那幾週。回傳 (合併的組合操作, 多來源的證據)。

    **只在加總對得上時才看。** 對不上就什麼都不做 —— 那個落差本身是資訊
    (錢進了儲備、或某個來源那時還沒逐週揭露),不該被硬湊掉。

    兩種記法,理由與 `match_sell_to_buyback` 相同:

      一來源 → 一用途   合併成組合操作,兩邊不再單獨出現
      多來源 → 一用途   **不合併**,證據掛在各來源上

    為什麼多來源不能合併成多個組合:那筆用途會被算進每一個組合裡,
    同一筆買幣就被計了兩次。而硬塞進單一個組合又會讓另一個來源消失。
    所以記下關係、保持獨立 —— 加總對得上這件事本身就是證據,
    不需要為它捏造一個不存在的工具。
    """
    merged: List[Operation] = []
    evidence: Dict[str, dict] = {}
    for wk, (src, use) in sorted(_week_flows(conn, set(skip)).items()):
        if not src or not use or len(use) != 1:
            continue
        s_tot = sum(map(_amount, src.values()))
        use_tool, use_rows = next(iter(use.items()))
        u_tot = _amount(use_rows)
        if not (s_tot and u_tot):
            continue
        gap = abs(s_tot - u_tot) / max(s_tot, u_tot)
        if gap > tol:
            continue

        base = {"basis": "amount", "use_tool": use_tool, "use_usd": u_tot,
                "sources_total_usd": s_tot,
                "amount_gap_pct": round(gap * 100, 2)}

        if len(src) > 1:
            # 多個來源都供給同一個用途 —— 加總證明了這件事,但不合併
            for tool, rows in src.items():
                for r in rows:
                    evidence[r["event_id"]] = {
                        **base, "multi_source": True,
                        "source_tool": tool,
                        "share_of_use_pct": round(_amount(rows) / s_tot * 100, 1),
                        "co_sources": sorted(k for k in src if k != tool)}
            continue

        src_tool, src_rows = next(iter(src.items()))
        combo = PAIR_COMBO.get((src_tool, use_tool))
        params = _combo_params(combo, src_rows, use_rows, 1.0) if combo else {}
        if not params:
            continue
        merged.append(Operation(
            combo_id=combo, rule="amount_match", confidence=MEDIUM_HIGH,
            window_lo=min(r["period_start"] or r["effective_at"] for r in src_rows),
            window_hi=wk, params=params,
            evidence={**base, "source_tool": src_tool,
                      "same_document": len({r["doc_id"] for r in src_rows
                                            + use_rows}) == 1},
            members=[(r["event_id"], "source", r["usd"]) for r in src_rows]
                    + [(r["event_id"], "use", r["usd"]) for r in use_rows]))
    return merged, evidence


def single_operations(conn: sqlite3.Connection, consumed: Sequence[str],
                      evidence_for: Dict[str, dict] = None) -> List[Operation]:
    """配不到對的動作,自己就是一個操作。

    這不是失敗處理 —— 下游因此永遠只需要處理一種型別(設計圖 §5)。
    沒合併但有證據的,證據掛在這裡,資訊不會因為沒合併而消失。
    兩種證據的意思不同,所以 rule 要分開:

      partly_funded  文件明寫用途,但那筆錢只支應了用途的一部分
      multi_source   多個來源的**加總**等於同一個用途 —— 它們都參與了,
                     但分不出誰付了哪一塊,所以不合併
    """
    done, evidence_for = set(consumed), evidence_for or {}
    out = []
    for r in E.all_events(conn, family="action"):
        if r["event_id"] in done or not (r["qty"] or 0):
            continue
        ev = dict(evidence_for.get(r["event_id"]) or
                  {"note": "沒有配對證據,單一動作即一個操作"})
        rule = ("multi_source" if ev.get("multi_source")
                else "partly_funded" if r["event_id"] in evidence_for
                else "unpaired")
        out.append(Operation(
            combo_id=E.tool_for(r["kind"], r["instrument"]),
            rule=rule,
            confidence=(MEDIUM_HIGH if rule == "multi_source"
                        else MEDIUM if rule == "partly_funded" else 1.0),
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
    consumed = {e for op in merged for e, _, _ in op.members}
    # 文件明寫的先配(證據較強),剩下的才看金額
    by_amt, amt_ev = match_by_amount(conn, skip=consumed)
    merged += by_amt
    consumed |= {e for op in by_amt for e, _, _ in op.members}
    return merged + single_operations(conn, list(consumed),
                                      {**amt_ev, **partial})


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

    # 配對出來的組合,參數已經是 toolbox 的形狀(由 _combo_params 產生),
    # 直接過去就好 —— 再翻一次只會多一個會漂的地方。
    tool = T.BY_ID.get(op.combo_id)
    if tool is not None and set(tool.params) <= set(p):
        return tool, {k: p[k] for k in tool.params}

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
