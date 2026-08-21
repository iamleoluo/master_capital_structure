"""資料層與 CLI 的整合測試(不打 API,只驗證 schema/往返/降級行為)。"""
from __future__ import annotations

import datetime as dt
import sqlite3

import pytest

from mstr_cebe import cli as CLI
from mstr_cebe import core as C
from mstr_cebe import data as D
from mstr_cebe import db as DB
from mstr_cebe import fetch as F


@pytest.fixture()
def conn(tmp_path):
    c = DB.connect(str(tmp_path / "t.sqlite"))
    DB.seed_capital_structure(c)
    yield c
    c.close()


def _bar(day, close, high=None):
    return F.Bar(dt.date.fromisoformat(day), close, high or close, close, close,
                 1000, "test")


# ---------------------------------------------------------------------------
# schema / 往返
# ---------------------------------------------------------------------------

def test_capital_structure_round_trips_through_sqlite(conn):
    """DB 讀回的物件必須算出與記憶體版本完全相同的數字。"""
    from_db = {c.as_of: c for c in DB.load_capital_structures(conn)}
    for original in D.capital_structure_timeline():
        restored = from_db[original.as_of]
        assert restored.btc_held == pytest.approx(original.btc_held)
        assert restored.preferred_total_usd == pytest.approx(
            original.preferred_total_usd, rel=1e-9)
        assert restored.debt_notional_usd == pytest.approx(original.debt_notional_usd)
        assert restored.shares_basic == original.shares_basic
        assert restored.shares_fdso == original.shares_fdso


def test_fwp_snapshot_survives_the_round_trip(conn):
    """§6 的黃金測試在 DB 往返之後必須仍然通過。"""
    cs = next(c for c in DB.load_capital_structures(conn)
              if c.as_of == dt.date(2026, 8, 13))
    for btc, official in D.FWP_SENSITIVITY_TABLE:
        got = C.net_reserve_per_share_from(cs, btc, D.FWP_MSTR_PRICE)
        assert abs(got - official) <= 0.02, f"BTC {btc}: {got} vs {official}"


def test_market_daily_upsert_keeps_btc_and_mstr_independent(conn):
    """BTC 與 MSTR 交易日不同(週末),互相 upsert 不能覆蓋對方欄位。"""
    DB.upsert_market_daily(conn, btc=[_bar("2026-08-15", 63086.0)])
    DB.upsert_market_daily(conn, mstr=[_bar("2026-08-14", 93.04)])
    DB.upsert_market_daily(conn, btc=[_bar("2026-08-14", 63043.56)])

    rows = {r["date"]: r for r in DB.load_market_daily(conn)}
    assert rows["2026-08-15"]["btc_close_usd"] == pytest.approx(63086.0)
    assert rows["2026-08-15"]["mstr_close_usd"] is None      # 週末沒有股價
    assert rows["2026-08-14"]["btc_close_usd"] == pytest.approx(63043.56)
    assert rows["2026-08-14"]["mstr_close_usd"] == pytest.approx(93.04)


def test_mnav_readings_keep_variant_and_break_key(conn):
    """§8.1 / §8.5:同一天的不同 variant 必須各自成列,公司 mNAV 分兩段。"""
    cs = next(c for c in DB.load_capital_structures(conn)
              if c.as_of == dt.date(2026, 8, 13))
    readings = C.all_mnavs(cs, D.FWP_BTC_PRICE, D.FWP_MSTR_PRICE)
    DB.store_mnav_readings(conn, readings.values())

    rows = conn.execute("SELECT variant, comparable_key FROM mnav_readings "
                        "WHERE as_of = '2026-08-13'").fetchall()
    assert len(rows) == len(C.MNavVariant)
    keys = {r["variant"]: r["comparable_key"] for r in rows}
    assert keys["company"] == "company::post"      # 2026-08-13 在斷點之後
    assert keys["basic"] == "basic"

    # 同一天同 variant 重複寫入不應產生第二列
    DB.store_mnav_readings(conn, readings.values())
    again = conn.execute("SELECT COUNT(*) n FROM mnav_readings "
                         "WHERE as_of = '2026-08-13'").fetchone()
    assert again["n"] == len(C.MNavVariant)


def test_findings_are_persisted(conn):
    findings = DB.load_findings(conn)
    for key in ("2026_07_05_claims", "itm_converts_2024", "ath_is_intraday",
                "third_denominator", "fdso_coverage"):
        assert key in findings, key


# ---------------------------------------------------------------------------
# 驗證器
# ---------------------------------------------------------------------------

def test_fixture_validator_catches_a_bad_feed():
    """故意餵錯的價格必須被抓到 —— 驗證器不能永遠回 PASS。"""
    good = [_bar(d, v) for d, v in D.MSTR_DAILY_FIXTURE.items()]
    assert F.verify_mstr_against_fixture(good).ok

    bad = [_bar(d, v * 1.1) for d, v in D.MSTR_DAILY_FIXTURE.items()]
    rep = F.verify_mstr_against_fixture(bad)
    assert not rep.ok and len(rep.mismatched) == len(D.MSTR_DAILY_FIXTURE)


def test_split_validator_catches_unadjusted_prices():
    """§8.9:未做 split 調整的資料源會是 $5,430,必須被擋下。"""
    when, expected, _, _ = D.SPLIT_CHECK
    ok = [F.Bar(when, 500, expected, 390, 397.28, 0, "t")]
    assert F.verify_split(ok).ok

    unadjusted = [F.Bar(when, 5000, expected * 10, 3900, 3972.8, 0, "t")]
    assert not F.verify_split(unadjusted).ok


def test_split_validator_uses_high_not_close():
    """收盤價是 $397.28,拿 close 去比會誤判正確的資料源為失敗。"""
    when, expected, _, _ = D.SPLIT_CHECK
    bars = [F.Bar(when, 500, expected, 390, D.ATH_CLOSE_2024_11_21, 0, "t")]
    assert F.verify_split(bars).ok


def test_btc_validator_is_tier_aware():
    """Tier 3 的『~』約值只列 advisory,不能把整份驗證判成失敗。"""
    bars = []
    for obs in D.MNAV_OBSERVATIONS:
        if obs.btc_price is None:
            continue
        # Tier 3 全部給 8% 偏差,Tier 1/2 給準確值
        factor = 1.08 if obs.tier == "3" else 1.0
        bars.append(F.Bar(obs.as_of, 0, 0, 0, obs.btc_price * factor, 0, "t"))
    rep = F.verify_btc_anchors(bars)
    assert rep.ok, rep.mismatched
    assert len(rep.advisory) == 3

    # 但 Tier 1 偏差就必須失敗
    bad = [F.Bar(o.as_of, 0, 0, 0, o.btc_price * 1.05, 0, "t")
           for o in D.MNAV_OBSERVATIONS if o.btc_price]
    assert not F.verify_btc_anchors(bad).ok


# ---------------------------------------------------------------------------
# forward / backward fill 的降級行為
# ---------------------------------------------------------------------------

def test_cli_structure_backfills_before_first_observation(conn, capsys):
    cs = CLI._structure(conn, dt.date(2024, 11, 21))
    assert cs.as_of == dt.date(2024, 11, 21)
    assert cs.is_estimated
    assert "backward-filled" in cs.note
    assert "早於最早的資本結構觀測" in capsys.readouterr().out


def test_preferred_series_carry_forward_instead_of_vanishing():
    """2026-07-24 的 8-K 只揭露 STRC,其他系列必須沿用而不是變成 0。"""
    tl = {c.as_of: c for c in D.capital_structure_timeline()}
    jun = tl[dt.date(2026, 6, 30)]
    jul = tl[dt.date(2026, 7, 24)]
    for ticker in ("STRK", "STRF", "STRD", "STRE"):
        assert jul.preferred_by_ticker[ticker] == pytest.approx(
            jun.preferred_by_ticker[ticker]), ticker
    # STRC 是回購後的新值,必須下降
    assert jul.preferred_by_ticker["STRC"] < jun.preferred_by_ticker["STRC"]
    # 總額因此不該出現斷崖
    assert jul.preferred_total_usd / jun.preferred_total_usd > 0.99


def test_preferred_totals_never_collapse_between_observations():
    """優先股餘額只在回購時小幅下降,不該有 >10% 的單期崩塌。"""
    tl = sorted(D.capital_structure_timeline(), key=lambda c: c.as_of)
    for prev, cur in zip(tl, tl[1:]):
        if prev.preferred_total_usd == 0:
            continue
        ratio = cur.preferred_total_usd / prev.preferred_total_usd
        assert ratio > 0.9, f"{prev.as_of} → {cur.as_of}: ×{ratio:.3f}"


def test_march_2026_matches_the_filed_total():
    """2026-03-31 只揭露 STRC,沿用上期後仍以 UNALLOCATED 補到申報總額。"""
    cs = next(c for c in D.capital_structure_timeline()
              if c.as_of == dt.date(2026, 3, 31))
    pb = next(p for p in D.PREFERRED_BALANCES if p.as_of == dt.date(2026, 3, 31))
    assert cs.preferred_total_usd == pytest.approx(pb.total, rel=1e-9)
    assert cs.preferred_by_ticker["STRC"] == pytest.approx(pb.strc)


def test_convertible_backfill_is_flagged_as_estimated():
    """§5.3 沒有 2025 年底之前的餘額,回填值必須標記推估。"""
    tl = {c.as_of: c for c in D.capital_structure_timeline()}
    early = tl[dt.date(2024, 12, 31)]
    assert early.is_estimated
    assert "backward-filled" in early.note
    assert early.debt_notional_usd == pytest.approx(8.21e9)

    late = tl[dt.date(2026, 6, 30)]
    assert "backward-filled" not in late.note
    assert late.debt_notional_usd == pytest.approx(6.71e9)


# ---------------------------------------------------------------------------
# CLI 端到端
# ---------------------------------------------------------------------------

def test_cli_table_reproduces_the_spec_answers(conn, capsys, tmp_path, monkeypatch):
    DB.upsert_market_daily(conn, btc=[_bar("2026-08-13", D.FWP_BTC_PRICE)])
    conn.commit()
    rc = CLI.main(["--db", conn.execute("PRAGMA database_list").fetchone()[2],
                   "table", "--date", "2026-08-13", "--btc", str(D.FWP_BTC_PRICE)])
    assert rc == 0
    out = capsys.readouterr().out
    for expected in ("92.11", "115.14", "138.17", "184.22", "276.33", "137.04"):
        assert expected in out, expected


def test_cli_snapshot_always_labels_the_variant(conn, capsys):
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    rc = CLI.main(["--db", path, "snapshot", "--date", "2026-08-13",
                   "--btc", str(D.FWP_BTC_PRICE), "--mstr", str(D.FWP_MSTR_PRICE)])
    assert rc == 0
    out = capsys.readouterr().out
    # §8.1:不能出現裸的 mNAV 數字,每個都要帶 variant 與日期
    for variant in ("basic", "diluted", "enterprise", "company", "cebe"):
        assert f"({variant}, 2026-08-13)" in out, variant
    assert "橫跨 1.0x 兩側" in out


def test_cli_breakeven_shows_all_definitions(conn, capsys):
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    assert CLI.main(["--db", path, "breakeven", "--date", "2026-08-13",
                     "--btc", str(D.FWP_BTC_PRICE)]) == 0
    out = capsys.readouterr().out
    assert "20,635" in out
    assert out.count("求償權 $") == len(C.ClaimsBasis)
