"""CSV 是觀測與 FWP 參數的正本。這些數字是從 data.py 常數倒出來之後釘住的。"""
from __future__ import annotations

from datetime import date

from mstr_cebe import data as D


def test_xbrl_debt_matches_the_old_constants():
    assert D.XBRL_DEBT == (
        (date(2024, 3, 31), 3.559e9), (date(2024, 6, 30), 3.703e9),
        (date(2024, 9, 30), 4.212e9), (date(2024, 12, 31), 7.191e9),
        (date(2025, 3, 31), 8.140e9), (date(2025, 6, 30), 8.162e9),
        (date(2025, 9, 30), 8.174e9), (date(2025, 12, 31), 8.159e9),
        (date(2026, 3, 31), 8.165e9), (date(2026, 6, 30), 6.670e9),
        (date(2026, 9, 30), 6_715_414_000),
    )


def test_xbrl_cash_and_holdings_anchors():
    assert D.XBRL_CASH[-1] == (date(2026, 6, 30), 1.712e9)
    assert D.XBRL_BTC_HELD[-1] == (date(2026, 6, 30), 846_000)
    assert D.WEEKLY_BTC_HELD[0] == (date(2024, 9, 12), 244800)
    assert D.WEEKLY_BTC_HELD[-1][0] == date(2026, 8, 16)
    assert len(D.WEEKLY_BTC_HELD) == 90


def test_share_counts_and_preferred_q2():
    basic = {sc.as_of: sc.basic for sc in D.SHARE_COUNTS}
    assert basic[date(2026, 8, 21)] == 415_932_914
    assert basic[date(2026, 10, 25)] == 422_354_607
    q2 = next(p for p in D.PREFERRED_BALANCES if p.as_of == date(2026, 6, 30))
    q3 = next(p for p in D.PREFERRED_BALANCES if p.as_of == date(2026, 9, 30))
    assert q3.total == 14_109_839_000
    assert q3.shares_by_ticker["STRC"] == 90_964_532
    assert q2.total == 15_462_056_000
    assert q2.shares_by_ticker["STRC"] == 104_894_705
    assert [i.ticker for i in D.PREFERRED_IPOS] == ["STRK", "STRF", "STRD", "STRC", "STRE"]


def test_fwp_params_unchanged():
    assert D.PARAMS_2026_08_13["usd_reserve"] == 4.650e9
    assert D.PARAMS_2026_08_13["fdso"] == 398_220_309
    assert D.PARAMS_2026_08_24["usd_reserve"] == 6.69e9
    assert D.PARAMS_2026_08_24["pref_otm_notional"] == 14.966e9
    assert D.FWP_2026_08_24_USD_RESERVE == 5.10e9
    assert D.FWP_2026_08_24_USD_CASH == 1.59e9
    assert D.FWP_2026_08_24_ANNUAL_OBLIGATIONS == 1.703e9
    assert D.FWP_MSTR_PRICE == 97.33
    assert D.FWP_2026_08_24_MSTR_PRICE == 119.25
