"""L1 — 文件檔案庫。

設計圖:reference/06-architecture.md §3

職責只有一件事:**把外部世界的東西原封不動存下來**,並記錄它是什麼、
什麼時候拿的、從哪裡拿的。不解析、不計算、不詮釋。

為什麼需要它:

  1. 現在四支 fetcher 各自去 SEC 重抓同一批 8-K —— 四倍流量,
     而且四個地方可能對同一份文件有不同看法。
  2. 解析器一有 bug 就得重打 SEC 才能修,因為原文沒有留下來。
  3. `web/raw/` 裡的 ["2024-09-12", 244800] 無法回答「這個數字是從哪一份
     文件解出來的」。

**內容定址**是這一層的核心:doc_id 由內容的 sha256 決定,所以

  - 同一份文件重抓不會產生第二筆
  - SEC 改檔(有前例)會變成新的 doc_id,舊的留著 —— 歷史不可被悄悄改寫
  - 解析結果永遠可以指回一個確定的位元組序列

用法:

    python3 -m mstr_cebe.archive backfill     # 補抓歷史文件
    python3 -m mstr_cebe.archive stats        # 看檔案庫現況
"""
from __future__ import annotations

import datetime as dt
import hashlib
import os
import re
import sqlite3
import sys
import time
import zlib
from dataclasses import dataclass
from typing import Iterable, Iterator, List, Optional, Sequence

import requests

CIK = "0001050446"
# SEC 要求宣告身分並自律在 10 req/s 以內。這裡取遠比上限保守的節奏 ——
# 文件是不可變的,補抓只會做一次,沒有理由跑快。
USER_AGENT = "mstr-cebe-research (contact: iamleo789@gmail.com)"
_HEADERS = {"User-Agent": USER_AGENT}
_MIN_INTERVAL = 0.15
_TIMEOUT = 30

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(ROOT, "web", "archive.sqlite")

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  doc_id     TEXT PRIMARY KEY,   -- sha256(content) 前 16 碼
  source     TEXT NOT NULL,      -- 'sec_8k' | 'sec_submissions' | 'sec_xbrl' | ...
  url        TEXT NOT NULL,
  accession  TEXT,               -- SEC 專用
  filed_at   TEXT,               -- 文件自己宣稱的日期,不是抓取日
  fetched_at TEXT NOT NULL,
  media_type TEXT NOT NULL,
  sha256     TEXT NOT NULL,
  byte_len   INTEGER NOT NULL,   -- 原文長度(未壓縮)
  items      TEXT,               -- SEC 申報的 item 代碼,如 '7.01,8.01'
  content    BLOB NOT NULL       -- zlib 壓縮的原文
);
CREATE INDEX IF NOT EXISTS idx_doc_source_filed ON documents(source, filed_at);
CREATE INDEX IF NOT EXISTS idx_doc_accession ON documents(accession);
"""


@dataclass(frozen=True)
class DocMeta:
    """一份文件的中繼資料,不含內容。"""
    doc_id: str
    source: str
    url: str
    accession: Optional[str]
    filed_at: Optional[str]
    fetched_at: str
    media_type: str
    byte_len: int
    items: Optional[str] = None


# --------------------------------------------------------------- 檔案庫

def connect(path: str = DEFAULT_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    # 既有檔案庫的欄位遷移。內容是不可變的,只有中繼資料會後補 ——
    # 所以遷移一律是加欄位,不會重抓也不會改寫任何一份文件。
    cols = {r[1] for r in conn.execute("PRAGMA table_info(documents)")}
    if "items" not in cols:
        conn.execute("ALTER TABLE documents ADD COLUMN items TEXT")
        conn.commit()
    return conn


def doc_id_of(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()[:16]


def store(conn: sqlite3.Connection, *, source: str, url: str, content: bytes,
          media_type: str, accession: Optional[str] = None,
          filed_at: Optional[str] = None, items: Optional[str] = None) -> str:
    """歸檔一份文件,回傳 doc_id。

    內容相同就是同一份 —— 重複呼叫不會新增資料列,也不會更新 fetched_at
    (第一次拿到的時間才有意義)。
    """
    digest = hashlib.sha256(content).hexdigest()
    doc_id = digest[:16]
    conn.execute(
        "INSERT OR IGNORE INTO documents"
        " (doc_id, source, url, accession, filed_at, fetched_at,"
        "  media_type, sha256, byte_len, items, content)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (doc_id, source, url, accession, filed_at,
         dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
         media_type, digest, len(content), items, zlib.compress(content, 9)))
    conn.commit()
    return doc_id


def read(conn: sqlite3.Connection, doc_id: str) -> bytes:
    """取原文。解析器只透過這個拿資料,永遠不碰網路。"""
    row = conn.execute(
        "SELECT content, sha256 FROM documents WHERE doc_id = ?", (doc_id,)
    ).fetchone()
    if row is None:
        raise KeyError(f"檔案庫裡沒有 {doc_id}")
    content = zlib.decompress(row[0])
    # 內容定址的意義就在這裡:讀出來的東西必須還是當初存進去的那份
    if hashlib.sha256(content).hexdigest() != row[1]:
        raise ValueError(f"{doc_id} 內容與雜湊不符 —— 檔案庫毀損")
    return content


def text(conn: sqlite3.Connection, doc_id: str) -> str:
    """取原文並解碼成字串。解析器用這個。

    SEC 的 8-K 送出時不帶 charset,而 requests 會依 RFC 2616 退回 ISO-8859-1。
    實測目前 160 份全是純 ASCII(彎撇號等字元用 HTML entity 表示),
    所以 UTF-8 與 ISO-8859-1 解出來完全一樣 —— 換掉解碼方式不會改變任何輸出。
    這裡選 UTF-8 優先、失敗才退 latin-1,是為了將來真的出現 UTF-8 文件時
    不會靜默地解成亂碼。
    """
    raw = read(conn, doc_id)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def iter_8k(conn: sqlite3.Connection, *, since: dt.date,
            items: Sequence[str] = ("7.01", "8.01")) -> Iterator["Filed"]:
    """走訪已歸檔的 8-K,依申報日排序。**完全不碰網路。**

    四支解析器原本各自維護一份一樣的候選清單邏輯(抓 submissions、
    篩 7.01/8.01、組 URL、下載),現在共用這一個。
    """
    for m in find(conn, source="sec_8k", since=since):
        if items and not any(i in (m.items or "") for i in items):
            continue
        yield Filed(meta=m, html=text(conn, m.doc_id))


@dataclass(frozen=True)
class Filed:
    """一份已歸檔的申報:中繼資料 + 原文。"""
    meta: DocMeta
    html: str

    @property
    def filed_at(self) -> dt.date:
        return dt.date.fromisoformat(self.meta.filed_at)

    @property
    def accession(self) -> str:
        return self.meta.accession or ""


def find(conn: sqlite3.Connection, *, source: Optional[str] = None,
         since: Optional[dt.date] = None,
         until: Optional[dt.date] = None) -> List[DocMeta]:
    """依來源與申報日期查中繼資料,按申報日排序。"""
    where, args = [], []
    if source:
        where.append("source = ?")
        args.append(source)
    if since:
        where.append("filed_at >= ?")
        args.append(since.isoformat())
    if until:
        where.append("filed_at <= ?")
        args.append(until.isoformat())
    sql = ("SELECT doc_id, source, url, accession, filed_at, fetched_at,"
           " media_type, byte_len, items FROM documents")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY filed_at, accession"
    return [DocMeta(*row) for row in conn.execute(sql, args)]


def has(conn: sqlite3.Connection, *, accession: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM documents WHERE accession = ? LIMIT 1", (accession,)
    ).fetchone() is not None


def stats(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT source, COUNT(*), SUM(byte_len), MIN(filed_at), MAX(filed_at)"
        " FROM documents GROUP BY source ORDER BY source").fetchall()
    return {r[0]: {"docs": r[1], "bytes": r[2] or 0,
                   "first": r[3], "last": r[4]} for r in rows}


MANIFEST_PATH = os.path.join(ROOT, "web", "archive", "manifest.json")


def export_manifest(conn: sqlite3.Connection, path: str = MANIFEST_PATH) -> int:
    """把中繼資料(不含內容)匯出成可進版控的稽核軌跡。

    取捨:sqlite 每加一份文件就整檔重寫,git 存不了差異 —— 一年的每週更新
    會累積近百 MB 的歷史。所以**內容不進版控,軌跡進**。

    這樣仍然可稽核:每一列都有 url 與 sha256,任何人都能自己去抓那份文件、
    算雜湊、跟這裡比對。SEC 的文件是不可變的,所以檔案庫本身隨時可以用
    `backfill` 重建。
    """
    import json
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rows = conn.execute(
        "SELECT doc_id, source, url, accession, filed_at, fetched_at,"
        " media_type, sha256, byte_len, items FROM documents"
        " ORDER BY filed_at, accession, doc_id").fetchall()
    cols = ["doc_id", "source", "url", "accession", "filed_at", "fetched_at",
            "media_type", "sha256", "byte_len", "items"]
    with open(path, "w", encoding="utf-8") as f:
        json.dump([dict(zip(cols, r)) for r in rows], f,
                  ensure_ascii=False, indent=1)
        f.write("\n")
    return len(rows)


# --------------------------------------------------------------- 抓取

_last_call = 0.0


def _get(url: str) -> requests.Response:
    """對 SEC 禮貌一點:限速 + 宣告身分。"""
    global _last_call
    wait = _MIN_INTERVAL - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    _last_call = time.monotonic()
    r.raise_for_status()
    return r


@dataclass(frozen=True)
class Filing:
    form: str
    accession: str
    filed_at: dt.date
    primary_doc: str
    items: str

    @property
    def url(self) -> str:
        return ("https://www.sec.gov/Archives/edgar/data/1050446/"
                f"{self.accession.replace('-', '')}/{self.primary_doc}")


def submissions(conn: sqlite3.Connection) -> List[Filing]:
    """列出申報清單,順便把清單本身也歸檔。

    清單會隨時間變動(新的申報會被加進去),所以每次抓都可能是新的 doc_id ——
    這正是內容定址想要的效果:每一次的清單長什麼樣都留著。
    """
    url = f"https://data.sec.gov/submissions/CIK{CIK}.json"
    r = _get(url)
    store(conn, source="sec_submissions", url=url, content=r.content,
          media_type="application/json",
          filed_at=dt.date.today().isoformat())
    recent = r.json()["filings"]["recent"]
    return [
        Filing(form=recent["form"][i],
               accession=recent["accessionNumber"][i],
               filed_at=dt.date.fromisoformat(recent["filingDate"][i]),
               primary_doc=recent["primaryDocument"][i],
               items=recent.get("items", [""] * len(recent["form"]))[i])
        for i in range(len(recent["form"]))
    ]


def sync_filing_metadata(conn: sqlite3.Connection,
                         listing: Sequence["Filing"]) -> int:
    """用申報清單補齊已歸檔文件的中繼資料(目前是 items)。

    只動中繼資料,不碰內容 —— 所以 doc_id 不會變,也不需要重抓任何文件。
    """
    n = 0
    for f in listing:
        cur = conn.execute(
            "UPDATE documents SET items = ?"
            " WHERE accession = ? AND (items IS NULL OR items != ?)",
            (f.items, f.accession, f.items))
        n += cur.rowcount
    conn.commit()
    return n


def fetch_company_facts(conn: sqlite3.Connection) -> str:
    """歸檔 SEC 的 XBRL companyfacts。

    為什麼不解析 10-Q 的 HTML 表格:同樣的數字 SEC 已經以 XBRL 結構化發布,
    連期間起訖與來源 accession 都標好了。硬解 HTML 表格是自找的麻煩 ——
    「三個月」與「九個月」兩欄長得一模一樣,弄錯就是嚴重錯誤。

    這份檔案會隨每次申報而變,內容定址會自然留下每一版。
    """
    url = (f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json")
    r = _get(url)
    return store(conn, source="sec_xbrl", url=url, content=r.content,
                 media_type="application/json",
                 filed_at=dt.date.today().isoformat())


def backfill(conn: sqlite3.Connection, *, since: dt.date,
             forms: Iterable[str] = ("8-K",),
             progress: bool = True) -> Iterator[DocMeta]:
    """把 since 之後的申報文件補進檔案庫。已經有的跳過,不重抓。

    只歸檔,不解析 —— 這一步刻意不動任何現有的解析器。
    """
    wanted = set(forms)
    listing = submissions(conn)
    sync_filing_metadata(conn, listing)
    todo = [f for f in listing if f.form in wanted and f.filed_at >= since]
    todo.sort(key=lambda f: f.filed_at)

    for i, f in enumerate(todo, 1):
        if has(conn, accession=f.accession):
            continue
        try:
            r = _get(f.url)
        except requests.HTTPError as exc:            # 少數申報沒有 primary doc
            if progress:
                print(f"  ! {f.filed_at} {f.accession} 取不到:{exc}",
                      file=sys.stderr)
            continue
        doc_id = store(conn, source=f"sec_{f.form.lower().replace('-', '')}",
                       url=f.url, content=r.content,
                       media_type=r.headers.get("Content-Type", "text/html")
                       .split(";")[0].strip(),
                       accession=f.accession, filed_at=f.filed_at.isoformat(),
                       items=f.items)
        if progress:
            print(f"  + [{i:>3}/{len(todo)}] {f.filed_at} {f.form:<5} "
                  f"{doc_id}  {len(r.content)//1024:>4} KB  {f.items}")
        yield DocMeta(doc_id, f"sec_{f.form.lower().replace('-', '')}", f.url,
                      f.accession, f.filed_at.isoformat(), "", "", len(r.content))


# --------------------------------------------------------------- CLI

def _cmd_backfill(argv: List[str]) -> int:
    since = dt.date.fromisoformat(argv[0]) if argv else dt.date(2024, 7, 1)
    conn = connect()
    print(f"補抓 {since} 之後的 8-K 到 {DEFAULT_PATH}")
    added = sum(1 for _ in backfill(conn, since=since))
    print(f"\n新增 {added} 份")
    n = export_manifest(conn)
    print(f"稽核軌跡 web/archive/manifest.json({n} 列)")
    _cmd_stats([])
    return 0


def _cmd_facts(_argv: List[str]) -> int:
    conn = connect()
    doc_id = fetch_company_facts(conn)
    export_manifest(conn)
    print(f"XBRL companyfacts 已歸檔:{doc_id}")
    return 0


def _cmd_manifest(_argv: List[str]) -> int:
    n = export_manifest(connect())
    print(f"web/archive/manifest.json  {n} 列")
    return 0


def _cmd_stats(_argv: List[str]) -> int:
    conn = connect()
    s = stats(conn)
    if not s:
        print("檔案庫是空的 —— 先跑 python3 -m mstr_cebe.archive backfill")
        return 0
    print(f"{'來源':<18}{'份數':>6}{'原文大小':>12}   期間")
    total_docs = total_bytes = 0
    for source, v in s.items():
        print(f"{source:<18}{v['docs']:>6}{v['bytes']/1e6:>10.1f} MB"
              f"   {v['first']} → {v['last']}")
        total_docs += v["docs"]
        total_bytes += v["bytes"]
    size = os.path.getsize(DEFAULT_PATH)
    print(f"{'合計':<18}{total_docs:>6}{total_bytes/1e6:>10.1f} MB")
    print(f"檔案庫 {size/1e6:.1f} MB(壓縮後,"
          f"{size/max(total_bytes,1)*100:.0f}%)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmds = {"backfill": _cmd_backfill, "stats": _cmd_stats,
            "manifest": _cmd_manifest, "facts": _cmd_facts}
    if not argv or argv[0] not in cmds:
        print(f"用法:python3 -m mstr_cebe.archive {{{'|'.join(cmds)}}}")
        return 1
    return cmds[argv[0]](argv[1:])



# ---------------------------------------------------------------------------
# 讀申報表格:逐格抽文字
# ---------------------------------------------------------------------------

def row_cells(tr, drop=("$", "(", ")")) -> List[str]:
    """一列 <tr> → 乾淨的文字格。空格一律正規化成一般空格。

    ⚠️ **`\\xa0` 會讓正則靜默失配。** EDGAR 的表頭大量使用不斷行空格,
    `get_text()` 原樣保留它,於是 `"Aggregate BTC Holdings"` 這種字面比對
    與 `r'Average (Purchase|Sale) Price'` 這種正則都對不上 —— 不會報錯,
    只是欄位變成 None。

    實害:2025-12-01 的 8-K 表格裡明寫 `Aggregate BTC Holdings = 650,000`,
    卻整整漏掉,持幣序列因此在 2025-11-16 → 12-07 之間空了 21 天。
    同一張表的 `avg_price` 也一起消失。

    這與 03-data.md §3 記的排版用撇號(U+2019)是同一類陷阱:
    **看起來一樣的字元,比對起來不一樣。** 所以正規化要做在最底層,
    而不是讓每一支解析器各自記得。
    """
    out = []
    for c in tr.find_all(["td", "th"]):
        t = re.sub(r"\s+", " ", c.get_text(" ")).strip()
        if t and t not in drop:
            out.append(t)
    return out


if __name__ == "__main__":
    raise SystemExit(main())
