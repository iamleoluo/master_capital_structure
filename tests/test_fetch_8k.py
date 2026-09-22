"""8-K 解析器測試 —— 全部用本地 fixture,不打網路。

fixture 是五份真實的 8-K,涵蓋所有已知版型:
  atm_2025_btc_table.htm             2025-09-08  ATM 舊版型(STRF ATM)+ BTC 買入表
  atm_2026_btc_table.htm             2026-05-04  ATM 新版型(STRF Stock)
  btc_prose_2024.htm                 2024-12-23  prose 版持有量與買入 + 融資來源敘述
  btc_sale_2026.htm                  2026-08-03  BTC 賣出表 + 賣幣用途敘述
  btc_purchased_sold_merged_2026.htm 2026-08-17  買賣合併欄位「BTC Purchased / (Sold)」

這組測試存在的理由:已經三次栽在「用攤平文字猜欄位順序」「正則跨段落誤配對」
「表頭字樣判斷方向」—— 版型一換就靜默給出錯的數字,而且往往是符號錯誤這種
不會讓程式崩潰、只會默默算錯的那種 bug。這裡把每種版型的期望值釘死。
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from mstr_cebe.fetch_8k_atm import parse_atm_table
from mstr_cebe.fetch_8k_repurchase import parse_repurchase_table
from mstr_cebe.fetch_8k_btc import (
    _cell_num,
    _parse_prose_format,
    _parse_table_format,
    normalize_funding,
    parse_activity,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# ATM Program Summary
# ---------------------------------------------------------------------------

def test_atm_2025_layout():
    """舊版型:第一欄是「STRF ATM」,無 Security 表頭。"""
    recs = parse_atm_table(load("atm_2025_btc_table.htm"))
    assert len(recs) == 1
    r = recs[0]
    assert r["week_start"] == "2025-09-02"
    assert r["week_end"] == "2025-09-07"
    assert r["total_m"] == pytest.approx(217.3)

    s = r["by_security"]
    assert s["STRF"]["net_proceeds_m"] == pytest.approx(11.6)
    assert s["STRF"]["shares"] == pytest.approx(104_381)
    assert s["STRK"]["net_proceeds_m"] == pytest.approx(5.2)
    assert s["MSTR"]["net_proceeds_m"] == pytest.approx(200.5)
    assert s["MSTR"]["shares"] == pytest.approx(591_606)
    # 該週沒動用的券種要是 0,不是 None
    assert s["STRC"]["net_proceeds_m"] == 0.0
    assert s["STRD"]["net_proceeds_m"] == 0.0


def test_atm_2026_layout():
    """新版型:多了 Security 表頭,第一欄改成「STRF Stock」。"""
    recs = parse_atm_table(load("atm_2026_btc_table.htm"))
    assert len(recs) == 1
    r = recs[0]
    assert r["week_start"] == "2026-04-27"
    assert r["week_end"] == "2026-05-03"
    assert r["total_m"] == pytest.approx(82.0)
    assert r["by_security"]["MSTR"]["net_proceeds_m"] == pytest.approx(82.0)
    assert r["by_security"]["MSTR"]["shares"] == pytest.approx(492_210)
    for t in ("STRF", "STRC", "STRK", "STRD"):
        assert r["by_security"][t]["net_proceeds_m"] == 0.0


def test_atm_available_capacity_is_captured():
    """Available for Issuance 欄是判斷 ATM 額度耗盡的依據,不能漏。"""
    r = parse_atm_table(load("atm_2025_btc_table.htm"))[0]
    assert r["by_security"]["STRK"]["available_m"] == pytest.approx(20_386.1)
    assert r["by_security"]["STRC"]["available_m"] == pytest.approx(4_200.0)


def test_atm_absent_returns_empty():
    """2024 年的 8-K 沒有 ATM 表,要安靜回空清單而不是炸掉。"""
    assert parse_atm_table(load("btc_prose_2024.htm")) == []


# ---------------------------------------------------------------------------
# 逐週買賣量
# ---------------------------------------------------------------------------

def test_activity_buy_week_table_format():
    recs = parse_activity(load("atm_2025_btc_table.htm"))
    assert len(recs) == 1
    r = recs[0]
    assert r["week_start"] == "2025-09-02"
    assert r["week_end"] == "2025-09-07"
    assert r["btc_delta"] == pytest.approx(1955)
    assert r["avg_price"] == pytest.approx(111_196)
    assert r["holdings"] == pytest.approx(638_460)


def test_activity_sell_week_is_negative():
    """賣出週的 delta 必須是負數 —— 舊版單一方向表頭(BTC Sold)靠表頭判定正負號。"""
    recs = parse_activity(load("btc_sale_2026.htm"))
    assert len(recs) == 1
    r = recs[0]
    assert r["btc_delta"] == pytest.approx(-1638)
    assert r["holdings"] == pytest.approx(842_138)
    assert "dividends" in r["sale_use"]


def test_activity_merged_header_zero_week():
    """2026-08-17 起出現的第三種版型:買賣合併成一欄「BTC Purchased / (Sold)」。

    這份 fixture 剛好是無交易週(cell 是 "-"),用來確認新版型至少解析得出來 ——
    先前的 regex 只認 "BTC (Acquired|Sold)",完全沒對到 "Purchased",
    整週會被靜默漏解析(activity 少一筆,不會報錯)。
    """
    recs = parse_activity(load("btc_purchased_sold_merged_2026.htm"))
    assert len(recs) == 1
    r = recs[0]
    assert r["week_start"] == "2026-08-10"
    assert r["week_end"] == "2026-08-16"
    assert r["btc_delta"] == pytest.approx(0.0)
    assert r["holdings"] == pytest.approx(840_447)


def test_merged_header_does_not_flip_sign_on_purchase():
    """回歸測試:合併表頭「BTC Purchased / (Sold)」本身含有 "Sold" 這個字,

    若沿用舊邏輯「表頭有 Sold 字樣就取負號」,連買入週都會被誤判成賣出。
    正負號現在完全交給 _cell_num 判斷括號,不看表頭字樣。這裡用真實表格結構
    (取自實際 fixture,只把資料列換成一個買入案例)驗證買入不會被誤翻負。
    """
    html = """
    <table>
      <tr><td>During Period August 10, 2026 to August 16, 2026</td><td>As of August 16, 2026</td></tr>
      <tr><td>BTC Purchased / (Sold) (1)</td><td>Aggregate Purchase / (Sale) Price (in millions) (2)</td>
          <td>Average Purchase / (Sale) Price (2)</td><td>Aggregate BTC Holdings</td>
          <td>Aggregate Purchase Price (in billions) (2)</td><td>Average Purchase Price (2)</td></tr>
      <tr><td>1,955</td><td>$</td><td>217.4</td><td>$</td><td>111,196</td>
          <td>840,447</td><td>$</td><td>63.36</td><td>$</td><td>75,385</td></tr>
    </table>"""
    recs = parse_activity(html)
    assert len(recs) == 1
    assert recs[0]["btc_delta"] == pytest.approx(1955), (
        "買入週被合併表頭的 'Sold' 字樣誤判成負數")


def test_merged_header_negative_cell_is_sell():
    """合併表頭遇到括號負數(真正的賣出週)時,方向要正確。"""
    html = """
    <table>
      <tr><td>During Period August 10, 2026 to August 16, 2026</td><td>As of August 16, 2026</td></tr>
      <tr><td>BTC Purchased / (Sold) (1)</td><td>Aggregate Purchase / (Sale) Price (in millions) (2)</td>
          <td>Average Purchase / (Sale) Price (2)</td><td>Aggregate BTC Holdings</td>
          <td>Aggregate Purchase Price (in billions) (2)</td><td>Average Purchase Price (2)</td></tr>
      <tr><td>(1,690)</td><td>$</td><td>104.7</td><td>$</td><td>61,952</td>
          <td>840,447</td><td>$</td><td>63.36</td><td>$</td><td>75,385</td></tr>
    </table>"""
    recs = parse_activity(html)
    assert len(recs) == 1
    assert recs[0]["btc_delta"] == pytest.approx(-1690)


@pytest.mark.parametrize("cell,expected", [
    ("1,955", 1955.0),
    ("(1,690)", -1690.0),
    ("-", 0.0),
    ("–", 0.0),
    ("$63.36", 63.36),
    ("", 0.0),
])
def test_cell_num_parses_parenthesized_negatives(cell, expected):
    """財務報表慣例:整個 cell 是「(數字)」代表負數。"""
    assert _cell_num(cell) == pytest.approx(expected)


def test_activity_prose_format():
    """2025-03-24 之前沒有表格,只有敘述句,一樣要抓到。"""
    recs = parse_activity(load("btc_prose_2024.htm"))
    assert len(recs) == 1
    r = recs[0]
    assert r["week_start"] == "2024-12-16"
    assert r["week_end"] == "2024-12-22"
    assert r["btc_delta"] == pytest.approx(5262)
    assert r["avg_price"] == pytest.approx(106_662)
    assert r["holdings"] == pytest.approx(444_262)


# ---------------------------------------------------------------------------
# 融資來源
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phrase,expected", [
    ("proceeds from the STRF ATM, STRK ATM and MSTR ATM", ["STRF", "STRK", "MSTR"]),
    ("proceeds from the Common ATM, STRK ATM and STRF Offering", ["STRF", "STRK", "MSTR"]),
    ("proceeds from the issuance and sale of Shares under the Sales Agreement", ["MSTR"]),
    ("proceeds from the sale of shares of STRD Stock and MSTR Stock", ["STRD", "MSTR"]),
])
def test_normalize_funding(phrase, expected):
    assert sorted(normalize_funding(phrase)) == sorted(expected)


def test_unspecified_funding_is_not_guessed():
    """只寫「under the ATM」沒指名券種時,回空清單 —— 絕不猜。"""
    assert normalize_funding("proceeds from the sale of shares under the ATM") == []


def test_activity_carries_funding_from_prose():
    r = parse_activity(load("atm_2025_btc_table.htm"))[0]
    assert sorted(r["funding"]) == ["MSTR", "STRF", "STRK"]
    assert "STRF ATM" in r["funding_raw"]


# ---------------------------------------------------------------------------
# 累計持有量(既有解析器,確認 fixture 上仍正確)
# ---------------------------------------------------------------------------

def test_cumulative_holdings_table_format():
    pts = _parse_table_format(load("atm_2025_btc_table.htm"))
    assert (dt.date(2025, 9, 7), 638_460) in pts


def test_cumulative_holdings_prose_format():
    pts = _parse_prose_format(load("btc_prose_2024.htm"))
    assert pts == [(dt.date(2024, 12, 22), 444_262)]


def test_prose_pattern_does_not_cross_paragraphs():
    """回歸測試:曾經因為非貪婪匹配跨段落,把債務段落的日期配到持有量數字上。

    2024-09-20 那份的「As of June 30, 2024」屬於債務揭露段落,
    與持有量無關,不該被配對進來。
    """
    text = ('As of June 30, 2024, MicroStrategy had $3.909 billion aggregate '
            'indebtedness. As of September 19, 2024, MicroStrategy, together with '
            'its subsidiaries, held an aggregate of approximately 252,220 bitcoins.')
    from mstr_cebe.fetch_8k_btc import _PROSE_PAT
    matches = _PROSE_PAT.findall(text)
    assert len(matches) == 1
    assert matches[0][0] == "September 19, 2024"
    assert matches[0][1] == "252,220"


# ---------------------------------------------------------------------------
# 股票回購表(2026-07-27 起出現;2026-09-08 起 ATM 表消失只剩這張)
# ---------------------------------------------------------------------------

def test_repurchase_table_parsed():
    """fixture 是 2026-09-08 申報的 8-K,當週回購 STRC 1,810,885 股 / $176.3M。"""
    recs = parse_repurchase_table(load("repurchase_2026.htm"))
    assert len(recs) == 1
    r = recs[0]
    assert r["week_start"] == "2026-08-31"
    assert r["week_end"] == "2026-09-07"
    assert r["by_security"]["STRC"]["shares"] == pytest.approx(1_810_885)
    assert r["by_security"]["STRC"]["cost_m"] == pytest.approx(176.3)
    # 該週沒買的券種要是 0,不是 None,也不是漏掉
    for t in ("STRF", "STRK", "STRD", "MSTR"):
        assert r["by_security"][t]["shares"] == 0.0


def test_repurchase_total_row_is_split_across_two_rows():
    """版型細節:Total 的標籤與數值分屬兩個 <tr>,只看同一列會抓不到總計。"""
    r = parse_repurchase_table(load("repurchase_2026.htm"))[0]
    assert r["total_shares"] == pytest.approx(1_810_885)
    assert r["total_cost_m"] == pytest.approx(176.3)


def test_repurchase_parser_ignores_atm_issuance_table():
    """回購表與 ATM 發行表方向相反,絕不能互相誤判 —— 誤判會讓求償權往反方向跑。

    2025-09-08 那份只有 ATM 表(Shares Sold),回購解析器必須回空。
    """
    assert parse_repurchase_table(load("atm_2025_btc_table.htm")) == []


def test_atm_parser_ignores_repurchase_table():
    """反向:只有回購表的那份,ATM 解析器也必須回空。"""
    assert parse_atm_table(load("repurchase_2026.htm")) == []
