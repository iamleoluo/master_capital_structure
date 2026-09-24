"""策略歸因的測試 —— 守的是「拆解必須加得回去」這件事。

歸因最容易出的錯是殘差被默默吞掉:四個因子加起來不等於實際變化,
或三層乘法拆解漏掉一層。那種錯不會讓程式崩潰,只會讓頁面上的百分比
看起來合理但全部是錯的。這裡把加總恆等釘死。
"""
from __future__ import annotations

import math

import pytest

from mstr_cebe import attribution as A


def _st(held, claims, price, shares):
    return {"held": held, "claims": claims, "price": price, "shares": shares}


# ---------------------------------------------------------------------------
# 四因子 Shapley
# ---------------------------------------------------------------------------

def test_shapley_sums_exactly_to_delta():
    a = _st(846_682, 20.0e9, 60_260, 371.2e6)
    b = _st(846_000, 14.8e9, 86_404, 415.9e6)
    parts = A.shapley_cebe(a, b)
    delta = A._cebe(b) - A._cebe(a)
    assert sum(parts.values()) == pytest.approx(delta, abs=1e-6)


def test_shapley_is_order_independent_by_construction():
    """換掉因子在 dict 裡的順序不應該改變結果(Shapley 的重點就是這個)。"""
    a = _st(500_000, 8.0e9, 50_000, 250e6)
    b = _st(700_000, 15.0e9, 90_000, 350e6)
    p1 = A.shapley_cebe(a, b)
    p2 = A.shapley_cebe({k: a[k] for k in reversed(list(a))},
                        {k: b[k] for k in reversed(list(b))})
    for f in A.FACTORS:
        assert p1[f] == pytest.approx(p2[f], abs=1e-9)


def test_only_price_moves_means_only_price_gets_credit():
    """結構完全不動、只有幣價變 —— 其他三項的貢獻必須是零。"""
    a = _st(846_000, 15.0e9, 60_000, 400e6)
    b = dict(a, price=90_000)
    parts = A.shapley_cebe(a, b)
    assert parts["price"] == pytest.approx(A._cebe(b) - A._cebe(a), abs=1e-9)
    for f in ("held", "claims", "shares"):
        assert parts[f] == pytest.approx(0.0, abs=1e-9)


def test_claims_reduction_helps_dilution_hurts():
    """方向性:求償權減少要是正貢獻,股數增加要是負貢獻。"""
    a = _st(846_000, 20.0e9, 80_000, 400e6)
    b = _st(846_000, 15.0e9, 80_000, 450e6)
    parts = A.shapley_cebe(a, b)
    assert parts["claims"] > 0
    assert parts["shares"] < 0


# ---------------------------------------------------------------------------
# 反事實
# ---------------------------------------------------------------------------

def test_counterfactual_only_advances_price():
    a = _st(846_682, 20.0e9, 60_260, 371.2e6)
    cf = A.counterfactual_cebe(a, 86_404)
    assert cf == pytest.approx(A.cebe_sats(a["held"], a["claims"], 86_404, a["shares"]))


def test_counterfactual_rises_with_price_when_claims_positive():
    """求償權是固定美元,所以幣價漲、什麼都不做,每股含幣量也會自己上升。"""
    a = _st(800_000, 18.0e9, 50_000, 400e6)
    assert A.counterfactual_cebe(a, 100_000) > A._cebe(a)


def test_counterfactual_is_flat_without_claims():
    """沒有任何求償權的話,幣價完全不影響每股含幣量 —— 槓桿效果來自求償權。"""
    a = _st(800_000, 0.0, 50_000, 400e6)
    assert A.counterfactual_cebe(a, 100_000) == pytest.approx(A._cebe(a))


# ---------------------------------------------------------------------------
# 三層乘法拆解
# ---------------------------------------------------------------------------

def test_price_layers_sum_to_total_log_change():
    layers = A.price_layers(1.12, 138_613, 60_260, 1.30, 162_107, 86_404)
    p0 = 1.12 * 138_613 * 60_260 / 1e8
    p1 = 1.30 * 162_107 * 86_404 / 1e8
    assert sum(layers.values()) == pytest.approx(math.log(p1 / p0), abs=1e-12)


def test_price_identity_reconstructs_the_stock_price():
    """恆等式本身:三個因子相乘要等於股價(這是整個拆解的前提)。"""
    mnav, cebe, btc = 1.3046, 149_925.0, 86_404.0
    assert mnav * cebe * btc / 1e8 == pytest.approx(169.00, rel=2e-4)


def test_share_of_handles_zero_total():
    assert A.share_of({"a": 1e-12, "b": -1e-12}) == {}


@pytest.mark.parametrize("bad", [0, -1])
def test_price_layers_rejects_nonpositive(bad):
    with pytest.raises(ValueError):
        A.price_layers(1.0, 1.0, 1.0, bad, 1.0, 1.0)
