"""波動阻尼的量測 —— 口徑與邊界。"""
from __future__ import annotations

import math

import pytest

from mstr_cebe import volatility as V


def test_a_constant_price_has_zero_volatility() -> None:
    assert V.realized_vol([100.0] * 40) == pytest.approx(0.0)


def test_gaps_are_skipped_not_filled() -> None:
    """缺值直接跳過。補值(例如沿用前一天)會把波動**壓低**,

    而這支模組的用途正是證明某些工具波動低 —— 用一個會系統性
    低估波動的口徑去證明波動低,等於自己餵自己答案。
    """
    clean = [100.0, 102.0, 101.0, 103.0, 102.0, 104.0, 103.0, 105.0]
    holed = [100.0, 102.0, None, 101.0, 103.0, None, 102.0, 104.0, 103.0, 105.0]
    assert V.log_returns(holed) == pytest.approx(V.log_returns(clean))


def test_too_few_points_returns_none_rather_than_a_number() -> None:
    """樣本不足回 None。回一個用三個點算出來的標準差比回 None 更糟 ——
    下游會把它當成真的。"""
    assert V.realized_vol([100.0, 101.0, 102.0]) is None
    assert V.realized_vol([]) is None
    assert V.realized_vol([None] * 50) is None


def test_annualisation_uses_calendar_days() -> None:
    """√365 而不是 √252 —— BTC 七天都在交易,換成交易日會讓兩邊不可比。"""
    px = [100.0 * math.exp(0.01 * (-1) ** i) for i in range(40)]
    rets = V.log_returns(px)
    import statistics
    assert V.realized_vol(px) == pytest.approx(
        statistics.stdev(rets[-30:]) * math.sqrt(365), rel=1e-9)


def test_damping_is_measured_against_common_equity() -> None:
    """分母是普通股。拿 BTC 當分母會低估阻尼 —— 普通股本身已放大了 BTC。"""
    assert V.damping(0.10, 1.00) == pytest.approx(0.90)
    assert V.damping(1.00, 1.00) == pytest.approx(0.0)
    assert V.damping(None, 1.0) is None and V.damping(0.1, None) is None


def test_the_measured_ladder_backs_the_stated_engineering_claim() -> None:
    """對真實資料:優先股確實剝離了絕大部分的權益端波動。

    這是「可以被打臉的宣稱」那一類測試 —— 它斷言的是**真實資料**的性質,
    不是程式的性質。公司說剝離 50%–70%;若實測掉到 50% 以下,
    要嘛是結構變了,要嘛是我們的口徑錯了,兩種都該有人來看。
    """
    import json
    import pathlib
    d = json.loads((pathlib.Path(__file__).resolve().parent.parent
                    / "app" / "data" / "daily.json").read_text())
    eq = V.realized_vol(d["mstr"])
    assert eq and eq > 0
    for t in ("strc", "strf"):
        v = V.realized_vol(d[f"{t}_price"])
        assert v, f"{t} 沒有足夠樣本"
        assert V.damping(v, eq) > 0.5, f"{t} 的阻尼掉到 50% 以下"
    # 普通股承接放大的波動:必定高於 BTC
    assert eq > V.realized_vol(d["btc"])
