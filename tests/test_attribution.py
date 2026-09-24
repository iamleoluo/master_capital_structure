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


# ---------------------------------------------------------------------------
# 操作層級拆解
# ---------------------------------------------------------------------------

def _ops_base():
    return {"held": 846_682.0, "claims": 20.02e9, "price": 60_260.0, "shares": 371.2e6}


def test_operations_sum_to_total_change():
    base = _ops_base()
    ops = A.build_operations(
        raised=5.161e9, discount=48.5e6, obligations=401e6,
        btc_bought_usd=445e6, btc_sold_usd=429e6,
        d_held=-682.0, d_shares=44.8e6, end_price=86_404.0, residual=-386e6)
    parts = A.shapley_operations(base, ops)

    end = dict(base)
    for k in ops:
        end = A._apply(end, ops[k])
    assert sum(parts.values()) == pytest.approx(
        A.cebe_of(end) - A.cebe_of(base), abs=1e-6)


def test_buying_bitcoin_with_cash_is_neutral():
    """最反直覺、也最重要的一條:用現金買幣對每股含幣量沒有影響。

    持幣 +X/p、現金 −X(求償權 +X),分子的兩項正好抵銷。
    所以「公司又買了多少幣」本身完全不能拿來論斷對股東好不好。
    """
    base = _ops_base()
    spend, p = 500e6, base["price"]
    only_btc = {"btc": {"dclaims": spend, "dheld": spend / p}}
    parts = A.shapley_operations(base, only_btc)
    assert parts["btc"] == pytest.approx(0.0, abs=1e-6)


def test_buyback_contributes_only_the_discount():
    """回購 $1.125B 面額 $1.173B —— 進得了分子的只有 $48.5M 的折價。"""
    base = _ops_base()
    par, cost = 1.1733e9, 1.1248e9
    parts = A.shapley_operations(base, {"buyback": {"dclaims": -(par - cost)}})
    expected = (par - cost) / base["price"] / base["shares"] * 1e8
    assert parts["buyback"] == pytest.approx(expected, rel=1e-9)
    # 若誤把整筆回購金額當成貢獻,會高估二十幾倍
    wrong = par / base["price"] / base["shares"] * 1e8
    assert wrong > parts["buyback"] * 20


def test_carry_is_the_only_structurally_negative_operation():
    """股息與債息是純現金流出,無論幣價高低都是負貢獻。"""
    base = _ops_base()
    for price in (30_000.0, 60_260.0, 200_000.0):
        st = dict(base, price=price)
        parts = A.shapley_operations(st, {"carry": {"dclaims": 401e6}})
        assert parts["carry"] < 0


def test_atm_above_nav_is_accretive_below_is_dilutive():
    """ATM 的正負完全取決於發行價與每股淨值的關係,不是「增發就是壞事」。"""
    base = _ops_base()
    nav_ps = A.cebe_of(base) / 1e8 * base["price"]
    shares = 40e6
    for mult, sign in ((1.4, 1), (0.6, -1)):
        raised = shares * nav_ps * mult
        parts = A.shapley_operations(
            base, {"atm": {"dclaims": -raised, "dshares": shares}})
        assert parts["atm"] * sign > 0, f"發行價 {mult}× 淨值時方向錯了"


# ---------------------------------------------------------------------------
# 逐日鏈結(決策 vs 行情)
# ---------------------------------------------------------------------------

def _path(*tuples):
    return [{"held": h, "claims": c, "price": p, "shares": s}
            for h, c, p, s in tuples]


def test_chain_linked_sums_exactly():
    path = _path((846_682, 20.0e9, 60_260, 371.2e6),
                 (846_682, 19.0e9, 70_000, 390.0e6),
                 (846_000, 14.8e9, 86_404, 415.9e6))
    r = A.chain_linked(path)
    assert r["market"] + r["decision"] == pytest.approx(r["total"], abs=1e-6)


def test_chain_linked_pure_price_path_is_all_market():
    """結構完全沒動,只有幣價在走 —— 決策貢獻必須是零。"""
    path = _path((846_000, 15.0e9, 60_000, 400e6),
                 (846_000, 15.0e9, 75_000, 400e6),
                 (846_000, 15.0e9, 90_000, 400e6))
    r = A.chain_linked(path)
    assert r["decision"] == pytest.approx(0.0, abs=1e-9)
    assert r["market"] == pytest.approx(r["total"], abs=1e-9)


def test_chain_linked_pure_structure_path_is_all_decision():
    """幣價完全沒動 —— 行情貢獻必須是零。"""
    path = _path((846_000, 20.0e9, 80_000, 400e6),
                 (846_000, 17.0e9, 80_000, 405e6),
                 (846_000, 15.0e9, 80_000, 410e6))
    r = A.chain_linked(path)
    assert r["market"] == pytest.approx(0.0, abs=1e-9)
    assert r["decision"] == pytest.approx(r["total"], abs=1e-9)


def test_chain_linked_removes_hindsight_that_fixed_price_embeds():
    """核心差異:增發之後幣價大漲時,固定期末幣價會把決策打成負的,鏈結不會。

    同一條路徑:先在低價增發(當下高於淨值,是加分),之後幣價翻倍。
    度量 C 用期末高價回頭看,會判定增發稀釋;鏈結用增發當下的價格評價,不會。
    """
    p0, p1 = 60_000.0, 120_000.0
    start = {"held": 800_000.0, "claims": 20e9, "price": p0, "shares": 400e6}
    nav0 = A.cebe_of(start) / 1e8 * p0
    new_shares = 40e6
    raised = new_shares * nav0 * 1.5           # 以 1.5 倍淨值發行,當下明顯加分
    mid = {"held": start["held"], "claims": start["claims"] - raised,
           "price": p0, "shares": start["shares"] + new_shares}
    end = dict(mid, price=p1)

    chained = A.chain_linked([start, mid, end])
    fixed = A.cebe_of(end) - A.cebe_sats(
        start["held"], start["claims"], p1, start["shares"])

    assert chained["decision"] > 0, "當下高於淨值的增發,鏈結口徑應判為加分"
    assert fixed < chained["decision"], "固定期末幣價應該比鏈結更不利於增發"
