"""§3 資料 Schema —— SQLite 實作。

與規格書 §3 的差異(全部是刻意的):
  * market_daily 加了 OHLC 而非只有 close —— §8.9 的 split 檢查需要 high。
  * capital_structure 加了 shares_class_a / class_b 與 debt 的 tier 標記。
  * 新增 mnav_readings 表:§8.1 要求每個 mNAV 值都攜帶 variant + date,
    所以 (as_of, variant) 是複合主鍵,並存 comparable_key 讓查詢端能正確分段。
  * 新增 data_findings 表:記錄來源資料的內部矛盾(data.FINDING_*),
    讓下游查詢知道哪些數字有已知問題。
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from dataclasses import asdict
from typing import Dict, Iterable, List, Optional, Sequence

from . import core as C
from . import data as D
from .fetch import Bar

SCHEMA = """
PRAGMA foreign_keys = ON;

-- 日頻:市場資料
CREATE TABLE IF NOT EXISTS market_daily (
    date            TEXT PRIMARY KEY,
    btc_open_usd    REAL, btc_high_usd  REAL, btc_low_usd  REAL, btc_close_usd  REAL,
    mstr_open_usd   REAL, mstr_high_usd REAL, mstr_low_usd REAL, mstr_close_usd REAL,
    mstr_volume     INTEGER,
    btc_source      TEXT,
    mstr_source     TEXT
);

-- 事件頻:資本結構(查詢時 forward-fill)
CREATE TABLE IF NOT EXISTS capital_structure (
    as_of_date              TEXT PRIMARY KEY,
    source_tier             INTEGER,
    source_ref              TEXT,
    btc_held                REAL,
    debt_notional_usd       REAL,
    pref_strk_usd           REAL,
    pref_strf_usd           REAL,
    pref_strd_usd           REAL,
    pref_strc_usd           REAL,
    pref_stre_usd           REAL,
    pref_stre_eur           REAL,
    pref_stre_fx            REAL,
    pref_unallocated_usd    REAL,
    pref_total_usd          REAL,
    usd_reserve             REAL,
    cash_and_equiv          REAL,
    shares_basic            REAL,
    shares_fdso             REAL,
    shares_assumed_diluted  REAL,
    annual_obligations_usd  REAL,
    is_estimated            INTEGER,
    note                    TEXT
);

-- 每週買賣紀錄(融資來源歸因)
CREATE TABLE IF NOT EXISTS btc_transactions (
    week_end        TEXT,
    btc_delta       REAL,
    avg_price_usd   REAL,
    funding_source  TEXT,
    cebe_effect     TEXT,
    source_8k       TEXT,
    PRIMARY KEY (week_end, funding_source)
);

-- §8.1:mNAV 讀數必須攜帶 variant;comparable_key 處理 2026-07-23 斷點
CREATE TABLE IF NOT EXISTS mnav_readings (
    as_of           TEXT NOT NULL,
    variant         TEXT NOT NULL,
    comparable_key  TEXT NOT NULL,
    value           REAL NOT NULL,
    btc_price       REAL,
    mstr_price      REAL,
    claims_basis    TEXT,
    cash_source     TEXT,
    structure_as_of TEXT,
    is_forward_fill INTEGER,
    note            TEXT,
    PRIMARY KEY (as_of, variant, comparable_key)
);

-- 政策/定義斷點,畫圖時要標註
CREATE TABLE IF NOT EXISTS policy_breaks (
    as_of             TEXT PRIMARY KEY,
    title             TEXT,
    detail            TEXT,
    breaks_timeseries INTEGER
);

-- 來源資料的已知矛盾
CREATE TABLE IF NOT EXISTS data_findings (
    key      TEXT PRIMARY KEY,
    payload  TEXT
);

CREATE INDEX IF NOT EXISTS idx_mnav_variant ON mnav_readings(variant, as_of);
CREATE INDEX IF NOT EXISTS idx_mnav_key ON mnav_readings(comparable_key, as_of);
"""

DEFAULT_DB = "mstr_cebe.sqlite"


def connect(path: str = DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


# ---------------------------------------------------------------------------
# 寫入
# ---------------------------------------------------------------------------

def upsert_market_daily(conn: sqlite3.Connection,
                        btc: Sequence[Bar] = (),
                        mstr: Sequence[Bar] = ()) -> int:
    """BTC 與 MSTR 分別 upsert,互不覆蓋對方的欄位(交易日不一致是正常的)。"""
    n = 0
    for bars, prefix in ((btc, "btc"), (mstr, "mstr")):
        for b in bars:
            cols = {f"{prefix}_open_usd": b.open, f"{prefix}_high_usd": b.high,
                    f"{prefix}_low_usd": b.low, f"{prefix}_close_usd": b.close,
                    f"{prefix}_source": b.source}
            if prefix == "mstr":
                cols["mstr_volume"] = int(b.volume) if b.volume else None
            names = ", ".join(cols)
            setters = ", ".join(f"{k}=excluded.{k}" for k in cols)
            placeholders = ", ".join("?" for _ in cols)
            conn.execute(
                f"INSERT INTO market_daily (date, {names}) VALUES (?, {placeholders}) "
                f"ON CONFLICT(date) DO UPDATE SET {setters}",
                [b.date.isoformat(), *cols.values()])
            n += 1
    conn.commit()
    return n


def seed_capital_structure(conn: sqlite3.Connection) -> int:
    """把 §5 的人工整理資料寫進 DB(§9 步驟 3),is_estimated 標好。"""
    rows = 0
    for cs in D.capital_structure_timeline():
        pref = cs.preferred_by_ticker
        stre = next((p for p in cs.preferreds if p.ticker == "STRE"), None)
        conn.execute("""
            INSERT INTO capital_structure VALUES (
              :as_of, :tier, :ref, :btc, :debt,
              :strk, :strf, :strd, :strc, :stre, :stre_eur, :stre_fx, :unalloc, :pref_total,
              :reserve, :cash, :basic, :fdso, :assumed, :oblig, :est, :note)
            ON CONFLICT(as_of_date) DO UPDATE SET
              source_tier=excluded.source_tier, source_ref=excluded.source_ref,
              btc_held=excluded.btc_held, debt_notional_usd=excluded.debt_notional_usd,
              pref_strk_usd=excluded.pref_strk_usd, pref_strf_usd=excluded.pref_strf_usd,
              pref_strd_usd=excluded.pref_strd_usd, pref_strc_usd=excluded.pref_strc_usd,
              pref_stre_usd=excluded.pref_stre_usd, pref_total_usd=excluded.pref_total_usd,
              shares_basic=excluded.shares_basic, note=excluded.note
        """, {
            "as_of": cs.as_of.isoformat(), "tier": cs.source_tier,
            "ref": cs.source_ref, "btc": cs.btc_held,
            "debt": cs.debt_notional_usd,
            "strk": pref.get("STRK", 0.0), "strf": pref.get("STRF", 0.0),
            "strd": pref.get("STRD", 0.0), "strc": pref.get("STRC", 0.0),
            "stre": pref.get("STRE", 0.0),
            "stre_eur": stre.liquidation_preference_native if stre else None,
            "stre_fx": stre.fx_rate_as_of if stre else None,
            "unalloc": pref.get("UNALLOCATED", 0.0),
            "pref_total": cs.preferred_total_usd,
            "reserve": cs.usd_reserve_usd, "cash": cs.cash_and_equiv_usd,
            "basic": cs.shares_basic, "fdso": cs.shares_fdso,
            "assumed": cs.shares_assumed_diluted,
            "oblig": cs.annual_obligations_usd,
            "est": int(cs.is_estimated), "note": cs.note,
        })
        rows += 1

    for pb in D.POLICY_BREAKS:
        conn.execute("INSERT OR REPLACE INTO policy_breaks VALUES (?,?,?,?)",
                     (pb.as_of.isoformat(), pb.title, pb.detail,
                      int(pb.breaks_timeseries)))

    findings = {
        "2026_07_05_claims": D.FINDING_2026_07_05_CLAIMS,
        "cebe_denominator": D.FINDING_CEBE_DENOMINATOR,
        "spec_arithmetic": list(D.FINDING_SPEC_ARITHMETIC),
        "third_denominator": D.FINDING_THIRD_DENOMINATOR,
        "tier3_not_reproducible": D.FINDING_TIER3_NOT_REPRODUCIBLE,
        "ath_is_intraday": D.FINDING_ATH_IS_INTRADAY,
        "btc_date_pairing": D.FINDING_BTC_DATE_PAIRING,
        "fdso_coverage": D.FINDING_FDSO_COVERAGE,
        "itm_converts_2024": D.FINDING_ITM_CONVERTS_DOMINATE_2024,
    }
    for k, v in findings.items():
        conn.execute("INSERT OR REPLACE INTO data_findings VALUES (?,?)",
                     (k, json.dumps(v, ensure_ascii=False, default=str)))

    conn.commit()
    return rows


def store_mnav_readings(conn: sqlite3.Connection,
                        readings: Iterable[C.MNavReading],
                        structure_as_of: Optional[dt.date] = None,
                        claims_basis: str = "", cash_source: str = "",
                        is_forward_fill: bool = False) -> int:
    n = 0
    for r in readings:
        conn.execute("""
            INSERT OR REPLACE INTO mnav_readings VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (r.as_of.isoformat(), r.variant.value, r.comparable_key, r.value,
              r.btc_price, r.mstr_price, claims_basis, cash_source,
              structure_as_of.isoformat() if structure_as_of else None,
              int(is_forward_fill), r.note))
        n += 1
    conn.commit()
    return n


# ---------------------------------------------------------------------------
# 讀取
# ---------------------------------------------------------------------------

def load_market_daily(conn: sqlite3.Connection,
                      start: Optional[dt.date] = None,
                      end: Optional[dt.date] = None) -> List[sqlite3.Row]:
    sql = "SELECT * FROM market_daily WHERE 1=1"
    args: List[str] = []
    if start:
        sql += " AND date >= ?"
        args.append(start.isoformat())
    if end:
        sql += " AND date <= ?"
        args.append(end.isoformat())
    return conn.execute(sql + " ORDER BY date", args).fetchall()


def load_capital_structures(conn: sqlite3.Connection) -> List[C.CapitalStructure]:
    """從 DB 讀回 CapitalStructure 物件(繞回 core 的型別,保持單一計算路徑)。"""
    out: List[C.CapitalStructure] = []
    for row in conn.execute("SELECT * FROM capital_structure ORDER BY as_of_date"):
        prefs = []
        for ticker, col in (("STRK", "pref_strk_usd"), ("STRF", "pref_strf_usd"),
                            ("STRD", "pref_strd_usd"), ("STRC", "pref_strc_usd"),
                            ("STRE", "pref_stre_usd"),
                            ("UNALLOCATED", "pref_unallocated_usd")):
            amount = row[col] or 0.0
            if amount <= 0:
                continue
            prefs.append(C.PreferredSeries(
                ticker=ticker, liquidation_preference_usd=amount,
                rank=D.SENIORITY_RANK.get(ticker, 99),
                convertible=(ticker == "STRK"),
                currency="EUR" if ticker == "STRE" else "USD",
                liquidation_preference_native=(row["pref_stre_eur"]
                                               if ticker == "STRE" else None),
                fx_rate_as_of=(row["pref_stre_fx"] if ticker == "STRE" else None),
                is_estimated=bool(row["is_estimated"]),
            ))
        out.append(C.CapitalStructure(
            as_of=dt.date.fromisoformat(row["as_of_date"]),
            btc_held=row["btc_held"],
            debt_notional_usd=row["debt_notional_usd"] or 0.0,
            preferreds=tuple(prefs),
            usd_reserve_usd=row["usd_reserve"] or 0.0,
            cash_and_equiv_usd=row["cash_and_equiv"] or 0.0,
            shares_basic=row["shares_basic"],
            shares_fdso=row["shares_fdso"],
            shares_assumed_diluted=row["shares_assumed_diluted"],
            annual_obligations_usd=row["annual_obligations_usd"],
            source_tier=row["source_tier"], source_ref=row["source_ref"] or "",
            is_estimated=bool(row["is_estimated"]), note=row["note"] or "",
        ))
    return out


def load_findings(conn: sqlite3.Connection) -> Dict[str, object]:
    return {r["key"]: json.loads(r["payload"])
            for r in conn.execute("SELECT * FROM data_findings")}
