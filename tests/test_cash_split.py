"""Reserve 與 Cash 拆成兩條觀測。拼好的 cash_anchors 維持原值。"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from mstr_cebe.interpolate import cash_anchors

OBS = Path(__file__).resolve().parents[1] / "data" / "obs"


def _rows(name: str) -> list[dict[str, str]]:
    with (OBS / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_reserve_and_cash_are_separate_files():
    reserve = _rows("usd_reserve.csv")
    cash = _rows("usd_cash.csv")
    assert len(reserve) == 26
    assert len(cash) == 11
    sep = next(r for r in reserve if r["as_of"] == "2026-09-27")
    assert float(sep["usd"]) == 5.02e9
    assert reserve[-1]["as_of"] == "2026-11-08"
    assert float(reserve[-1]["usd"]) == 4.77e9
    assert cash[0]["as_of"] == "2026-08-30"
    assert float(cash[0]["usd"]) == 1.61e9
    sep_cash = next(r for r in cash if r["as_of"] == "2026-09-27")
    assert float(sep_cash["usd"]) == 1.00e9
    assert float(cash[-1]["usd"]) == 146.2e6
    assert all(r["as_of"] >= "2026-08-30" for r in cash)


def test_spliced_anchors_keep_their_values():
    got = {d: v for d, v in cash_anchors()}
    assert got[date(2025, 12, 21)] == 2.19e9
    assert got[date(2026, 6, 30)] == 1.712e9
    assert got[date(2026, 8, 16)] == 4.8e9
    assert got[date(2026, 8, 30)] == 6.71e9
    assert got[date(2026, 9, 27)] == 6.02e9
    assert got[date(2026, 11, 8)] == 4.77e9 + 146.2e6


def test_where_both_exist_the_splice_is_their_sum():
    cash = {r["as_of"]: float(r["usd"]) for r in _rows("usd_cash.csv")}
    reserve = {r["as_of"]: float(r["usd"]) for r in _rows("usd_reserve.csv")}
    anchors = {d.isoformat(): v for d, v in cash_anchors()}
    for day, c in cash.items():
        assert anchors[day] == reserve[day] + c
