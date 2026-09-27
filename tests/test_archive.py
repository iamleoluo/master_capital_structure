"""L1 文件檔案庫的測試。

這一層的價值全在幾條性質上:內容定址、冪等、讀回來的東西沒變、
以及**解析器不必碰網路**。這支不連外網,用假文件驗。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import sqlite3

import pytest

from mstr_cebe import archive as A


@pytest.fixture()
def conn(tmp_path):
    c = A.connect(str(tmp_path / "archive.sqlite"))
    yield c
    c.close()


HTML = b"<html><body>As of September 12, 2024 ... 244,800 bitcoins</body></html>"


def _store(c, content=HTML, **kw):
    kw.setdefault("source", "sec_8k")
    kw.setdefault("url", "https://www.sec.gov/Archives/edgar/data/1050446/x/a.htm")
    kw.setdefault("media_type", "text/html")
    return A.store(c, content=content, **kw)


# --------------------------------------------------------------- 內容定址

def test_doc_id_is_derived_from_content(conn):
    assert _store(conn) == hashlib.sha256(HTML).hexdigest()[:16]


def test_storing_the_same_document_twice_is_one_row(conn):
    a = _store(conn, accession="0001-24-1")
    b = _store(conn, accession="0001-24-1")
    assert a == b
    assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1


def test_changed_content_becomes_a_new_document_and_keeps_the_old(conn):
    """SEC 有改檔的前例。改過的是新的一份,舊的必須留著 ——
    歷史不可以被悄悄改寫。"""
    old = _store(conn, content=HTML, accession="0001-24-1")
    new = _store(conn, content=HTML + b"<!-- revised -->", accession="0001-24-1")
    assert old != new
    assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 2
    assert A.read(conn, old) == HTML          # 舊的還在,而且沒被動過


def test_first_fetch_time_is_not_overwritten(conn):
    """fetched_at 記的是「第一次拿到」,重抓不該把它往後推。"""
    doc_id = _store(conn)
    first = conn.execute("SELECT fetched_at FROM documents").fetchone()[0]
    _store(conn)
    assert conn.execute("SELECT fetched_at FROM documents").fetchone()[0] == first


# --------------------------------------------------------------- 讀回來

def test_read_returns_the_exact_bytes(conn):
    assert A.read(conn, _store(conn)) == HTML


def test_read_detects_a_corrupted_archive(conn):
    """讀出來的東西必須還是當初存進去的那份,否則內容定址就沒有意義。"""
    doc_id = _store(conn)
    import zlib
    conn.execute("UPDATE documents SET content = ? WHERE doc_id = ?",
                 (zlib.compress(b"tampered"), doc_id))
    conn.commit()
    with pytest.raises(ValueError, match="毀損"):
        A.read(conn, doc_id)


def test_read_of_unknown_id_raises(conn):
    with pytest.raises(KeyError):
        A.read(conn, "0" * 16)


def test_binary_content_survives(conn):
    """XBRL 是 JSON,但別的來源不一定。壓縮與還原不能假設文字。"""
    blob = bytes(range(256)) * 40
    assert A.read(conn, _store(conn, content=blob,
                               media_type="application/octet-stream")) == blob


# --------------------------------------------------------------- 查詢

def test_find_filters_by_source_and_date(conn):
    _store(conn, content=b"a", accession="a", filed_at="2024-07-01")
    _store(conn, content=b"b", accession="b", filed_at="2025-03-31")
    _store(conn, content=b"c", source="sec_xbrl", accession="c",
           filed_at="2025-06-30", media_type="application/json")

    assert len(A.find(conn)) == 3
    assert len(A.find(conn, source="sec_8k")) == 2
    assert len(A.find(conn, source="sec_xbrl")) == 1
    assert [d.filed_at for d in A.find(conn, since=dt.date(2025, 1, 1))] == [
        "2025-03-31", "2025-06-30"]
    assert [d.filed_at for d in A.find(conn, until=dt.date(2024, 12, 31))] == [
        "2024-07-01"]


def test_find_is_ordered_by_filing_date(conn):
    for i, day in enumerate(["2025-06-30", "2024-07-01", "2025-03-31"]):
        _store(conn, content=f"doc{i}".encode(), accession=str(i), filed_at=day)
    assert [d.filed_at for d in A.find(conn)] == [
        "2024-07-01", "2025-03-31", "2025-06-30"]


def test_has_checks_by_accession(conn):
    _store(conn, accession="0001050446-26-000123")
    assert A.has(conn, accession="0001050446-26-000123")
    assert not A.has(conn, accession="0001050446-26-999999")


def test_metadata_records_provenance(conn):
    """這一層存在的理由:244,800 這個數字要能回溯。"""
    doc_id = _store(conn, accession="0001050446-24-000055", filed_at="2024-09-12")
    (meta,) = A.find(conn, source="sec_8k")
    assert meta.doc_id == doc_id
    assert meta.accession == "0001050446-24-000055"
    assert meta.filed_at == "2024-09-12"
    assert meta.url.startswith("https://www.sec.gov/Archives/edgar/")
    assert meta.byte_len == len(HTML)
    assert meta.fetched_at                       # 什麼時候拿的也要有


# --------------------------------------------------------------- 統計與建置

def test_stats_groups_by_source(conn):
    _store(conn, content=b"a" * 100, accession="a", filed_at="2024-07-01")
    _store(conn, content=b"b" * 200, accession="b", filed_at="2025-01-01")
    _store(conn, content=b"{}", source="sec_xbrl", accession="c",
           filed_at="2025-06-30", media_type="application/json")
    s = A.stats(conn)
    assert s["sec_8k"]["docs"] == 2
    assert s["sec_8k"]["bytes"] == 300
    assert s["sec_8k"]["first"] == "2024-07-01"
    assert s["sec_8k"]["last"] == "2025-01-01"
    assert s["sec_xbrl"]["docs"] == 1


def test_connect_is_idempotent(tmp_path):
    """重複開啟不該炸,也不該清掉既有資料。"""
    path = str(tmp_path / "a.sqlite")
    c1 = A.connect(path)
    _store(c1, accession="x")
    c1.close()
    c2 = A.connect(path)
    assert len(A.find(c2)) == 1
    c2.close()


def test_filing_url_is_built_from_accession():
    f = A.Filing(form="8-K", accession="0001050446-26-000123",
                 filed_at=dt.date(2026, 9, 8), primary_doc="d123.htm", items="7.01")
    assert f.url == ("https://www.sec.gov/Archives/edgar/data/1050446/"
                     "000105044626000123/d123.htm")


def test_schema_has_no_derived_columns(conn):
    """L1 只存事實。任何算出來的值(cebe_effect、mnav 之類)都不該在這裡 ——
    口徑一改就得改資料庫,那正是舊 schema 的毛病。

    items 是 SEC 對該份申報公布的中繼資料,與 accession / filed_at 同類,
    不是衍生值,所以它在這裡是合法的。"""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(documents)")}
    assert cols == {"doc_id", "source", "url", "accession", "filed_at",
                    "fetched_at", "media_type", "sha256", "byte_len",
                    "items", "content"}


def test_migration_adds_items_without_touching_content(tmp_path):
    """既有檔案庫要能就地升級 —— 不重抓、不改寫任何一份文件。"""
    import sqlite3 as _sq
    path = str(tmp_path / "old.sqlite")
    old_schema = A.SCHEMA.replace(
        "  items      TEXT,               "
        "-- SEC 申報的 item 代碼,如 '7.01,8.01'\n", "")
    c = _sq.connect(path)
    c.executescript(old_schema)
    import zlib
    digest = hashlib.sha256(HTML).hexdigest()
    c.execute("INSERT INTO documents (doc_id, source, url, accession, filed_at,"
              " fetched_at, media_type, sha256, byte_len, content)"
              " VALUES ('abc','sec_8k','u','0001-24-1','2024-09-13','t',"
              "'text/html',?,?,?)",
              (digest, len(HTML), zlib.compress(HTML)))
    c.commit()
    c.close()

    up = A.connect(path)                       # 遷移在這裡發生
    assert "items" in {r[1] for r in up.execute("PRAGMA table_info(documents)")}
    assert A.read(up, "abc") == HTML           # 內容原封不動
    up.close()


def test_iter_8k_filters_by_item_and_never_touches_network(conn, monkeypatch):
    """驗收條件:解析器走這條路,完全不碰網路。"""
    _store(conn, content=b"<html>btc update</html>", accession="a",
           filed_at="2026-01-05", items="7.01,8.01")
    _store(conn, content=b"<html>annual meeting</html>", accession="b",
           filed_at="2026-01-12", items="5.07")
    _store(conn, content=b"<html>results</html>", accession="c",
           filed_at="2026-01-19", items="2.02,7.01")

    def boom(*a, **k):
        raise AssertionError("不該連網")

    monkeypatch.setattr(A.requests, "get", boom)
    got = list(A.iter_8k(conn, since=dt.date(2026, 1, 1)))
    assert [f.accession for f in got] == ["a", "c"]        # 5.07 那份被篩掉
    assert got[0].html == "<html>btc update</html>"
    assert got[0].filed_at == dt.date(2026, 1, 5)


def test_iter_8k_respects_since(conn):
    _store(conn, content=b"<a/>", accession="a", filed_at="2024-07-01",
           items="7.01")
    _store(conn, content=b"<b/>", accession="b", filed_at="2026-01-05",
           items="7.01")
    assert [f.accession for f in A.iter_8k(conn, since=dt.date(2025, 1, 1))] == ["b"]


def test_sync_filing_metadata_fills_items_without_refetching(conn):
    doc_id = _store(conn, accession="0001-26-9", filed_at="2026-03-02")
    assert A.find(conn)[0].items is None
    n = A.sync_filing_metadata(conn, [A.Filing(
        form="8-K", accession="0001-26-9", filed_at=dt.date(2026, 3, 2),
        primary_doc="d.htm", items="7.01,8.01")])
    assert n == 1
    assert A.find(conn)[0].items == "7.01,8.01"
    assert A.read(conn, doc_id) == HTML        # 內容沒動
    assert A.sync_filing_metadata(conn, [A.Filing(
        form="8-K", accession="0001-26-9", filed_at=dt.date(2026, 3, 2),
        primary_doc="d.htm", items="7.01,8.01")]) == 0      # 冪等


def test_text_decodes_ascii_and_utf8(conn):
    assert A.text(conn, _store(conn, content=b"plain ascii")) == "plain ascii"
    utf8 = "彎撇號 \u2019".encode("utf-8")
    assert A.text(conn, _store(conn, content=utf8)) == utf8.decode("utf-8")


def test_archive_needs_no_network_to_read(conn, monkeypatch):
    """驗收條件的核心:歸檔之後,取用完全不碰網路。"""
    doc_id = _store(conn)

    def boom(*a, **k):
        raise AssertionError("不該連網")

    monkeypatch.setattr(A.requests, "get", boom)
    assert A.read(conn, doc_id) == HTML
    assert A.find(conn) and A.stats(conn)


# --------------------------------------------------------- 驗收:斷網跑管線

def _real_archive():
    """本機的真實檔案庫。沒補抓過就沒有,測試自動跳過。"""
    import os
    if not os.path.exists(A.DEFAULT_PATH):
        pytest.skip("檔案庫還沒建立,先跑 python3 -m mstr_cebe.archive backfill")
    conn = A.connect()
    if not A.find(conn, source="sec_8k"):
        conn.close()
        pytest.skip("檔案庫裡沒有 8-K")
    return conn


@pytest.fixture()
def no_network(monkeypatch):
    """把對外連線封死。模組要先載入完才能封 —— ssl 繼承 socket.socket。"""
    class Offline(Exception):
        pass

    def blocked(*a, **k):
        raise Offline("解析器嘗試連線 —— 它不該碰網路")

    monkeypatch.setattr("socket.socket.connect", blocked, raising=False)
    monkeypatch.setattr("socket.create_connection", blocked)
    monkeypatch.setattr("socket.getaddrinfo", blocked)
    return Offline


def test_parsers_run_with_the_network_cut(no_network):
    """第 2 步的驗收條件:四支解析器完全不碰網路。

    這條成立,就代表解析與抓取真的分開了 —— 解析器有 bug 時修起來
    不必再打 SEC,而且版型迴歸有固定樣本可重跑。
    """
    import datetime as _dt
    from mstr_cebe import (fetch_8k_atm, fetch_8k_btc,
                           fetch_8k_repurchase, fetch_8k_reserve)
    conn = _real_archive()
    try:
        holdings, activity = fetch_8k_btc.fetch_everything(
            _dt.date(2024, 7, 1), verbose=False, conn=conn)
        assert holdings and activity
        assert fetch_8k_atm.fetch_all(_dt.date(2024, 7, 1), verbose=False, conn=conn)
        assert fetch_8k_repurchase.fetch_all(_dt.date(2026, 1, 1), verbose=False, conn=conn)
        assert fetch_8k_reserve.fetch_all(_dt.date(2025, 12, 1), verbose=False, conn=conn)
    finally:
        conn.close()


def test_the_network_block_actually_blocks(no_network):
    """對照組:沒有這條,上面那個測試可能只是封鎖失效。"""
    conn = _real_archive()
    try:
        with pytest.raises(Exception):
            A.submissions(conn)
    finally:
        conn.close()


def test_parser_output_still_matches_the_committed_raw_files(no_network):
    """改讀檔案庫之後,解析結果必須與 web/raw/*.json 逐筆相同。

    這是「重構不改變行為」的實證 —— 不是靠信心,是靠比對。
    """
    import datetime as _dt
    import json as _json
    import os
    from mstr_cebe import (fetch_8k_atm, fetch_8k_btc,
                           fetch_8k_repurchase, fetch_8k_reserve)

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw = os.path.join(root, "web", "raw")
    conn = _real_archive()
    try:
        holdings, activity = fetch_8k_btc.fetch_everything(
            _dt.date(2024, 7, 1), verbose=False, conn=conn)
        cases = [
            (fetch_8k_atm.fetch_all(_dt.date(2024, 7, 1), verbose=False, conn=conn),
             "atm_weekly.json"),
            (fetch_8k_repurchase.fetch_all(_dt.date(2026, 1, 1), verbose=False, conn=conn),
             "repurchase_weekly.json"),
            (fetch_8k_reserve.fetch_all(_dt.date(2025, 12, 1), verbose=False, conn=conn),
             "reserve_weekly.json"),
        ]
    finally:
        conn.close()

    for got, name in cases:
        with open(os.path.join(raw, name), encoding="utf-8") as f:
            want = _json.load(f)
        # 經過 JSON round-trip 再比,避免 tuple/list 這類無關緊要的型別差異
        assert _json.loads(_json.dumps(got, ensure_ascii=False)) == want, name

    # 持幣的兩個檔案不再是爬蟲的直接輸出 —— 事件層在中間做了兩件事,
    # 兩件都是刻意的,所以這裡改成比對「爬蟲 + 那兩個轉換」:
    #
    #   1. 季末那份 8-K(Item 2.02)的季合計列,粒度是 quarter 不是 week,
    #      混進週加總會重複計算(2025 年因此多算 192,561 顆)
    #   2. 同一列尾欄帶的季末餘額是存量,要進持有量序列 ——
    #      舊檔只收專用表格,把它濾掉了
    #
    # 見 mstr_cebe/events.py 的 weekly_activity / weekly_holdings。
    from mstr_cebe import events as _E
    econn = _E.connect()
    try:
        ev_holdings = {r["effective_at"]: int(r["qty"])
                       for r in _E.all_events(econn, kind="holdings_observation")
                       if r["locator"].startswith("holdings/")}
        ev_weeks = {r["period_end"] for r in _E.all_events(econn)
                    if r["kind"] in ("btc_purchase", "btc_sale")}
        ev_quarters = {r["period_end"]
                       for r in _E.all_events(econn, granularity="quarter")
                       if r["kind"] in ("btc_purchase", "btc_sale")
                       and r["locator"].startswith("activity/")}
        raw_holdings = dict(_json.load(open(
            os.path.join(raw, "btc_holdings_weekly.json"), encoding="utf-8")))
        raw_weeks = {a["week_end"] for a in _json.load(open(
            os.path.join(raw, "btc_activity_weekly.json"), encoding="utf-8"))}
    finally:
        econn.close()

    # 爬蟲的持有量 = 事件層 `holdings/` 那一組,逐筆相同(解析本身沒變)
    assert {d.isoformat(): v for d, v in holdings.items()} == ev_holdings

    # web/raw 是事件層的視圖:持有量是爬蟲輸出的超集,多出來的只能是季末點
    assert set(raw_holdings) >= set(ev_holdings)
    for d, v in ev_holdings.items():
        assert raw_holdings[d] == v, d

    # 活動檔則相反 —— 恰好少掉季合計那幾列,而且每一列都還在事件層裡
    assert {a["week_end"] for a in activity} - raw_weeks == ev_quarters
    assert raw_weeks == ev_weeks          # 週粒度的那些一列不少
    assert not (ev_weeks & ev_quarters)   # 兩種粒度沒有落在同一個期末
