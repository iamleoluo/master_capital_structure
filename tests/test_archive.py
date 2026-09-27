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
    口徑一改就得改資料庫,那正是舊 schema 的毛病。"""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(documents)")}
    assert cols == {"doc_id", "source", "url", "accession", "filed_at",
                    "fetched_at", "media_type", "sha256", "byte_len", "content"}


def test_archive_needs_no_network_to_read(conn, monkeypatch):
    """驗收條件的核心:歸檔之後,取用完全不碰網路。"""
    doc_id = _store(conn)

    def boom(*a, **k):
        raise AssertionError("不該連網")

    monkeypatch.setattr(A.requests, "get", boom)
    assert A.read(conn, doc_id) == HTML
    assert A.find(conn) and A.stats(conn)
