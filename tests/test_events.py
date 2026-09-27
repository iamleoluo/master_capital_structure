"""L2 事件層的測試。

兩組:一組用假文件驗性質(冪等、家族、工具對應、可重放),
一組用真實檔案庫驗「週聚合由事件算出來之後與舊檔逐筆相同」——
那是第 3 步的驗收條件。
"""
from __future__ import annotations

import datetime as dt
import json
import os

import pytest

from mstr_cebe import archive as A
from mstr_cebe import events as E


@pytest.fixture()
def conn(tmp_path):
    c = E.connect(str(tmp_path / "a.sqlite"))
    yield c
    c.close()


def _doc(c, content=b"<html>x</html>", **kw):
    kw.setdefault("source", "sec_8k")
    kw.setdefault("url", "https://www.sec.gov/x")
    kw.setdefault("media_type", "text/html")
    kw.setdefault("filed_at", "2026-08-10")
    return A.store(c, content=content, **kw)


def _ev(doc, **kw):
    kw.setdefault("kind", "btc_purchase")
    kw.setdefault("instrument", "BTC")
    kw.setdefault("effective_at", "2026-08-09")
    kw.setdefault("locator", "activity/2026-08-09")
    return E.Event(doc_id=doc, **kw)


# --------------------------------------------------------- 名義與家族

def test_every_kind_declares_a_family():
    for kind, (family, _) in E.KINDS.items():
        assert family in ("action", "observation"), kind


def test_observations_map_to_no_tool():
    """觀測是狀態不是動作。把它對到工具,就會把「餘額變了」讀成
    「公司做了什麼」—— 四層歸因最想避免的錯誤。"""
    for kind, (family, _) in E.KINDS.items():
        if family == "observation":
            assert E.tool_for(kind, "BTC") is None, kind


def test_every_action_maps_to_a_real_toolbox_tool():
    """L2 與 toolbox 的接點。工具 id 打錯字,這裡會抓到。"""
    from mstr_cebe import toolbox as T
    for kind, (family, _) in E.KINDS.items():
        if family != "action":
            continue
        for instrument in ("BTC", "MSTR", "STRC"):
            tool = E.tool_for(kind, instrument)
            assert tool in T.BY_ID, f"{kind}/{instrument} → {tool}"


def test_atm_issue_picks_the_tool_by_instrument():
    """發普通股與發優先股對 E 的效果完全相反,不能共用一把工具。"""
    assert E.tool_for("atm_issue", "MSTR") == "common_atm"
    assert E.tool_for("atm_issue", "STRC") == "issue_preferred"
    assert E.tool_for("atm_issue", "STRF") == "issue_preferred"


# --------------------------------------------------------- 冪等與出處

def test_event_id_is_stable_for_the_same_row(conn):
    doc = _doc(conn)
    assert _ev(doc).event_id == _ev(doc).event_id


def test_event_id_separates_rows_within_one_document(conn):
    doc = _doc(conn)
    a = _ev(doc, instrument="STRC", kind="atm_issue",
            locator="atm/2026-08-09/STRC")
    b = _ev(doc, instrument="STRF", kind="atm_issue",
            locator="atm/2026-08-09/STRF")
    assert a.event_id != b.event_id


def test_reinserting_the_same_event_does_not_duplicate(conn):
    doc = _doc(conn)
    E.insert(conn, [_ev(doc)])
    E.insert(conn, [_ev(doc)])
    assert len(E.all_events(conn)) == 1


def test_every_event_carries_provenance(conn):
    doc = _doc(conn, accession="0001-26-1")
    E.insert(conn, [_ev(doc, qty=100.0, unit="BTC")])
    (row,) = E.all_events(conn)
    assert row["doc_id"] == doc
    assert row["locator"] == "activity/2026-08-09"
    assert row["filed"] == "2026-08-10"        # 從 documents join 來的
    assert row["extraction"] == "stated"


def test_events_can_be_filtered_by_family(conn):
    doc = _doc(conn)
    E.insert(conn, [
        _ev(doc, qty=1.0),
        _ev(doc, kind="holdings_observation", locator="holdings/2026-08-09",
            qty=846000.0),
    ])
    assert len(E.all_events(conn, family="action")) == 1
    assert len(E.all_events(conn, family="observation")) == 1


# --------------------------------------------------------- 後蓋前

def test_a_later_filing_wins_for_the_same_period(conn):
    """同一週被兩份 8-K 提到時取最新那份。這個規則原本藏在 dict 覆寫的
    順序裡,現在是顯性的 —— 所以它可以被測試。"""
    old = _doc(conn, content=b"<old/>", accession="a", filed_at="2026-08-10")
    new = _doc(conn, content=b"<new/>", accession="b", filed_at="2026-08-17")
    for doc, shares in ((old, 100.0), (new, 250.0)):
        E.insert(conn, [E.Event(
            kind="preferred_repurchase", instrument="STRC",
            effective_at="2026-08-09", period_start="2026-08-03",
            period_end="2026-08-09", qty=shares, unit="shares", usd=-1e6,
            doc_id=doc, locator="repurchase/2026-08-09/STRC")])
    (rec,) = E.weekly_repurchase(conn)
    assert rec["by_security"]["STRC"]["shares"] == 250.0
    assert rec["filed"] == "2026-08-17"


# --------------------------------------------------------- 可重放

def test_rebuild_clears_before_deriving(conn):
    doc = _doc(conn)
    E.insert(conn, [_ev(doc, qty=1.0)])
    assert len(E.all_events(conn)) == 1
    # 這份假文件解不出任何東西,所以重建之後應該是空的
    assert E.rebuild(conn, since=dt.date(2020, 1, 1)) == 0
    assert E.all_events(conn) == []


# --------------------------------------------------- 驗收:與舊檔逐筆相同

def _real():
    if not os.path.exists(A.DEFAULT_PATH):
        pytest.skip("檔案庫還沒建立,先跑 python3 -m mstr_cebe.archive backfill")
    conn = E.connect()
    if not conn.execute("SELECT 1 FROM events LIMIT 1").fetchone():
        conn.close()
        pytest.skip("還沒有事件,先跑 python3 -m mstr_cebe.events rebuild")
    return conn


RAW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "web", "raw")


@pytest.mark.parametrize("view,filename", [
    ("weekly_holdings", "btc_holdings_weekly.json"),
    ("weekly_activity", "btc_activity_weekly.json"),
    ("weekly_atm", "atm_weekly.json"),
    ("weekly_repurchase", "repurchase_weekly.json"),
    ("weekly_reserve", "reserve_weekly.json"),
])
def test_weekly_view_matches_the_committed_raw_file(view, filename):
    """第 3 步的驗收條件:週聚合改由事件算出來,結果必須與舊檔逐筆相同。

    這證明的是「換了資料結構但沒有改變任何數字」—— 週聚合從此是視圖,
    不是真相,而視圖與原本的真相對得起來。
    """
    conn = _real()
    try:
        got = getattr(E, view)(conn)
    finally:
        conn.close()
    with open(os.path.join(RAW, filename), encoding="utf-8") as f:
        want = json.load(f)
    assert json.loads(json.dumps(got, ensure_ascii=False)) == want


def test_the_real_archive_yields_both_families():
    conn = _real()
    try:
        actions = E.all_events(conn, family="action")
        obs = E.all_events(conn, family="observation")
    finally:
        conn.close()
    assert actions and obs
    # 每一個動作都要對得到一把工具
    for r in actions:
        assert E.tool_for(r["kind"], r["instrument"]) is not None


def test_named_actions_can_be_queried_by_month():
    """這一層存在的理由:現在問得出「某個月有哪些動作」,
    而不是只能問「回購檔案裡那幾週是什麼」。"""
    conn = _real()
    try:
        rows = [r for r in E.all_events(conn, family="action")
                if r["effective_at"].startswith("2026-08")]
    finally:
        conn.close()
    assert rows
    kinds = {r["kind"] for r in rows}
    assert "preferred_repurchase" in kinds     # 2026-08 確實有回購


# --------------------------------------------- 驗收:歸因參數改由事件來源

def test_flows_between_matches_the_legacy_aggregation():
    """第 4 步的驗收條件:歸因的資金流參數改由事件算出來,數字不能變。

    位元級比對,不是近似 —— 加總順序不同就會在 1e-6 美元的量級上分岔,
    而「重構不改變任何數字」值得守到位。
    """
    import os
    conn = _real()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def raw(name):
        with open(os.path.join(root, "web", "raw", name), encoding="utf-8") as f:
            return json.load(f)

    def app(name):
        with open(os.path.join(root, "app", "data", name), encoding="utf-8") as f:
            return json.load(f)

    try:
        atm, rep = raw("atm_weekly.json"), raw("repurchase_weekly.json")
        weekly, daily = app("weekly.json"), app("daily.json")
        end = daily["date"][-1]
        for a in daily["date"][::13]:            # 取樣即可,全量在 CLI 驗過
            legacy = {
                "common_raised": sum(
                    (x["by_security"].get("MSTR", {}).get("net_proceeds_m") or 0.0)
                    for x in atm if a <= x["week_end"] <= end) * 1e6,
                "pref_proceeds": sum(
                    (v.get("net_proceeds_m") or 0.0) for x in atm
                    if a <= x["week_end"] <= end
                    for sec, v in x["by_security"].items() if sec != "MSTR") * 1e6,
                "repurchase_discount": sum(
                    v.get("shares", 0.0) * 100 - v.get("cost_m", 0.0) * 1e6
                    for x in rep if a <= x["week_end"] <= end
                    for sec, v in x["by_security"].items() if sec != "MSTR"),
                "repurchase_par": sum(
                    v.get("shares", 0.0) * 100 for x in rep
                    if a <= x["week_end"] <= end
                    for sec, v in x["by_security"].items() if sec != "MSTR"),
                "btc_bought_usd": sum(
                    (w["delta"] or 0) * (w["avg_price"] or 0) for w in weekly
                    if a <= w["week_end"] <= end and (w["delta"] or 0) > 0),
                "btc_sold_usd": sum(
                    -(w["delta"] or 0) * (w["avg_price"] or 0) for w in weekly
                    if a <= w["week_end"] <= end and (w["delta"] or 0) < 0),
            }
            got = E.flows_between(conn, a, end)
            for k, want in legacy.items():
                assert got[k] == want, f"{a} {k}: {got[k]!r} != {want!r}"
    finally:
        conn.close()


def test_security_order_inside_a_week_follows_the_document():
    """券種順序會影響浮點加總,所以 locator 帶著表格列序。

    這同時讓 locator 更接近「文件裡的實體位置」,而不只是邏輯位置。
    """
    conn = _real()
    try:
        rec = next(r for r in E.weekly_atm(conn) if r["week_end"] == "2025-06-01")
    finally:
        conn.close()
    assert list(rec["by_security"]) == ["STRK", "STRF"]   # 文件裡就是這個順序


# ------------------------------------------- 季頻(XBRL):年初累計的陷阱

def test_ytd_cumulative_facts_are_differenced_into_quarters():
    """XBRL 的期間從會計年度起算,是**累計值**。直接加總會把同一筆錢算好幾次。

    這條測試用真實的數字:優先股募資 2025 年的四個累計值,
    還原之後各季應該是 1337 / 1611 / 2940 / 1148。
    """
    facts = [
        {"start": "2025-01-01", "end": "2025-03-31", "val": 1336.9, "accn": "a"},
        {"start": "2025-01-01", "end": "2025-06-30", "val": 2947.6, "accn": "a"},
        {"start": "2025-01-01", "end": "2025-09-30", "val": 5888.4, "accn": "a"},
        {"start": "2025-01-01", "end": "2025-12-31", "val": 7036.1, "accn": "a"},
    ]
    got = [(f["period_start"], f["period_end"], round(f["val"], 1))
           for f in E._discrete_periods(facts)]
    assert got == [
        ("2025-01-01", "2025-03-31", 1336.9),
        ("2025-03-31", "2025-06-30", 1610.7),
        ("2025-06-30", "2025-09-30", 2940.8),
        ("2025-09-30", "2025-12-31", 1147.7),
    ]
    # 各季相加要等於全年累計 —— 這才是「沒有重複也沒有遺漏」
    assert sum(x[2] for x in got) == pytest.approx(7036.1, abs=0.1)


def test_a_natively_quarterly_fact_wins_over_the_differenced_one():
    """有些事實本身就是單季(起日不是年度起日)。公司自己報的優先,
    否則兩者期間重疊會重複計算。"""
    facts = [
        {"start": "2025-01-01", "end": "2025-03-31", "val": 9.2, "accn": "a"},
        {"start": "2025-01-01", "end": "2025-06-30", "val": 58.1, "accn": "a"},
        {"start": "2025-04-01", "end": "2025-06-30", "val": 49.0, "accn": "b"},
    ]
    got = {f["period_end"]: f for f in E._discrete_periods(facts)}
    q2 = got["2025-06-30"]
    assert q2["extraction"] == "stated"          # 不是相減出來的
    assert q2["period_start"] == "2025-04-01"
    assert q2["val"] == pytest.approx(49.0)
    assert got["2025-03-31"]["extraction"] == "derived"


def test_restated_periods_take_the_latest_filing():
    facts = [
        {"start": "2025-01-01", "end": "2025-03-31", "val": 100.0,
         "accn": "0001-25-1", "filed": "2025-05-05"},
        {"start": "2025-01-01", "end": "2025-03-31", "val": 111.0,
         "accn": "0001-26-1", "filed": "2026-05-06"},
    ]
    (f,) = E._discrete_periods(facts)
    assert f["val"] == pytest.approx(111.0)


def test_quarterly_periods_never_overlap():
    """重疊就是重複計算。用真實資料掃一遍。"""
    conn = _real()
    try:
        rows = E.all_events(conn, granularity="quarter")
    finally:
        conn.close()
    seen = {}
    for r in rows:
        seen.setdefault((r["kind"], r["instrument"]), []).append(
            (r["period_start"], r["period_end"]))
    for key, spans in seen.items():
        spans.sort()
        for a, b in zip(spans, spans[1:]):
            assert b[0] >= a[1], f"{key} 期間重疊:{a} vs {b}"


def test_weekly_views_ignore_quarterly_events():
    """季頻與週頻描述同一批動作。混在一起就會重複計算,
    所以週聚合視圖只能看得到週顆粒。"""
    conn = _real()
    try:
        assert E.all_events(conn, granularity="quarter")      # 確實有季頻資料
        for r in E.all_events(conn, kind="atm_issue"):        # 預設只取週
            assert r["granularity"] == "week"
    finally:
        conn.close()


def test_xbrl_fills_the_tool_that_had_no_events():
    """可轉債的事件數原本是 0 —— 那是階段偵測器失敗的主因之一。"""
    conn = _real()
    try:
        issues = [r for r in E.all_events(conn, kind="convert_issue",
                                          granularity="quarter")]
        repays = [r for r in E.all_events(conn, kind="convert_repurchase",
                                          granularity="quarter")]
    finally:
        conn.close()
    assert issues and repays
    assert all(r["usd"] > 0 for r in issues)      # 發行是現金流入
    assert all(r["usd"] < 0 for r in repays)      # 償還是流出


def test_every_quarterly_event_points_at_its_source_filing():
    """出處往上流:季頻事件要能指回原始的 10-Q/10-K accession。"""
    conn = _real()
    try:
        rows = E.all_events(conn, granularity="quarter")
    finally:
        conn.close()
    for r in rows:
        assert r["attrs"]["xbrl_tag"]
        assert r["attrs"]["source_accession"]
        assert r["attrs"]["form"] in ("10-Q", "10-K")
