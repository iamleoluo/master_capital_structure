"""定價頁情境模擬的測試。

這一組的重點是**那條冪次封閉解到底對不對** —— 它原本只存在於
`leverage.ts` 的一行註解裡(「已用 20 萬步離散模擬驗證誤差 <0.0001%」),
而那個驗證不在倉庫裡。這裡把它變成會跑的東西。
"""
from __future__ import annotations

import math

import pytest

from mstr_cebe import scenario as SC
from mstr_cebe import toolbox as T


@pytest.fixture()
def s():
    return T.State(held=847_666.0, claims=14.7559e9,
                   shares=415.933e6, price=84_880.0)


# ------------------------------------------------------------------ 觸發價

def test_trigger_price_is_exactly_where_leverage_hits_the_floor(s):
    """定義檢查:在觸發價上,A(p*) 必須恰好等於下限。"""
    for floor in (1.05, 1.3, 2.0):
        star = SC.trigger_price(s, floor)
        assert SC.amplification(s, star) == pytest.approx(floor, rel=1e-12)


def test_a_floor_at_or_below_one_is_not_a_mechanism(s):
    """A 永遠 > 1,所以下限設在 1 以下等於沒有設 —— 不能製造出一個觸發價。"""
    for floor in (0.5, 1.0):
        assert SC.trigger_price(s, floor) == math.inf
        for px in (30_000, 120_000):
            assert SC.levered_residual_usd(s, px, floor) == SC.residual_usd(s, px)


def test_below_the_trigger_nothing_happens(s):
    """機制只在觸發價之上生效,之下必須與原本的殘值逐分錢相同。"""
    star = SC.trigger_price(s, 1.3)
    for px in (star * 0.5, star * 0.99, star):
        assert SC.levered_residual_usd(s, px, 1.3) == pytest.approx(
            SC.residual_usd(s, px), rel=1e-12)


def test_amplification_agrees_with_the_toolbox(s):
    """同一條式子不能有兩個答案 —— toolbox.leverage 是定義處。"""
    for px in (40_000, 86_000, 200_000):
        assert SC.amplification(T.State(s.held, s.claims, s.shares, px), px) \
            == pytest.approx(T.leverage(T.State(s.held, s.claims, s.shares, px)))


# -------------------------------------------------- 冪次封閉解 vs 離散模擬

def _simulate(s, target_px: float, floor: float, steps: int) -> float:
    """機制本身:逐步升價,每一步增發求償權買幣,把 A 釘回下限。

    不用任何封閉解 —— 這是拿「公司實際會做的動作」去逼近,
    所以它能獨立檢驗 `levered_residual_usd` 的那條冪次式。
    """
    star = SC.trigger_price(s, floor)
    H, C, p = s.held, s.claims, star
    r = (target_px / star) ** (1 / steps)
    for _ in range(steps):
        p *= r
        residual = H * p - C
        c_new = (floor - 1) * residual     # 釘住 A = floor 所需的求償權
        H += (c_new - C) / p               # 募到的錢全部買幣
        C = c_new
    return H * p - C


@pytest.mark.parametrize("target", [100_000, 150_000, 300_000])
def test_the_power_law_matches_the_mechanism_it_claims_to_describe(s, target):
    """R(p) = R(p*)·(p/p*)^L 必須與「逐步補倉釘住 A」算出來的一樣。"""
    closed = SC.levered_residual_usd(s, target, 1.30)
    sim = _simulate(s, target, 1.30, 20_000)
    assert abs(sim - closed) / closed < 2e-5


def test_the_gap_is_discretisation_error_and_shrinks(s):
    """誤差要隨步數收斂 —— 否則「接近」只是碰巧,不是同一條式子。"""
    closed = SC.levered_residual_usd(s, 300_000, 1.30)
    errs = [abs(_simulate(s, 300_000, 1.30, n) - closed) / closed
            for n in (200, 2_000, 20_000)]
    assert errs[0] > errs[1] > errs[2]
    assert errs[0] / errs[1] > 5 and errs[1] / errs[2] > 5   # 大致線性收斂


def test_a_higher_floor_means_more_leverage_above_the_trigger(s):
    """下限訂得越高,觸發得越早,而且之後長得越快。"""
    assert SC.trigger_price(s, 1.6) < SC.trigger_price(s, 1.2)
    a = SC.levered_residual_usd(s, 250_000, 1.2)
    b = SC.levered_residual_usd(s, 250_000, 1.6)
    assert b > a


# ------------------------------------------------------- 溢價增發的複利

def test_issuing_at_fair_value_changes_nothing(s):
    """m = 1 時增發既不加分也不稀釋 —— 這是 02-operations 判準的邊界。"""
    r, sh = SC.apply_atm_accretion(1e9, 100e6, mnav=1.0, dilution=0.3)
    assert r / sh == pytest.approx(1e9 / 100e6, rel=1e-12)


@pytest.mark.parametrize("m,better", [(1.5, True), (0.7, False)])
def test_the_atm_verdict_is_the_same_as_the_toolbox(s, m, better):
    """m > 1 加分、m < 1 稀釋 —— 與 03-operations.md 的 ATM 判準一致。"""
    base = 1e9 / 100e6
    r, sh = SC.apply_atm_accretion(1e9, 100e6, mnav=m, dilution=0.2)
    assert ((r / sh) > base) is better


def test_no_dilution_is_a_no_op(s):
    assert SC.apply_atm_accretion(1e9, 100e6, 2.0, 0.0) == (1e9, 100e6)


# ----------------------------------------------------------- 完整情境

def test_market_price_is_mnav_times_per_share(s):
    """定價頁的恆等式:股價 = m × 每股殘值。"""
    r = SC.run(s, 150_000, SC.Params(1.3, 1.21, 0.1))
    assert r.market_price == pytest.approx(1.21 * r.per_share_usd)
    assert r.per_share_sats == pytest.approx(r.per_share_usd / 150_000 * 1e8)


def test_amplification_is_pinned_at_the_floor_once_triggered(s):
    r = SC.run(s, 250_000, SC.Params(1.3, 1.0, 0.0))
    assert r.triggered and r.amplification == pytest.approx(1.3)
    lo = SC.run(s, 40_000, SC.Params(1.3, 1.0, 0.0))
    assert not lo.triggered and lo.amplification > 1.3


def test_golden_grid_covers_both_sides_of_the_trigger(s):
    """黃金樣本要有鑑別力 —— 全部落在同一側就釘不住冪次那一段。"""
    g = SC.golden_grid(s)
    assert len(g) == len(SC.GRID_PX) * len(SC.GRID_FLOOR) \
        * len(SC.GRID_MNAV) * len(SC.GRID_DILUTION)
    triggered = [x for x in g if x["trigger_px"] and x["px"] > x["trigger_px"]]
    assert len(triggered) > 50
    assert all(x["per_share_usd"] >= 0 for x in g)


# ---------------------------------------------------------------------------
# 增厚飛輪的上限
# ---------------------------------------------------------------------------

def test_the_yield_formula_agrees_with_apply_atm_accretion() -> None:
    """`accretion_yield` 必須與 `apply_atm_accretion` 是同一條式子。

    兩個實作算同一件事就會各自漂移(CLAUDE.md 第一條規則的理由)。
    這裡的處理是:公式單獨寫一份,但用 apply 的結果逐點釘住它。
    """
    for mnav in (0.8, 1.0, 1.05, 1.2, 1.5, 2.0):
        for x in (0.01, 0.1, 0.5, 1.0, 5.0):
            resid, shares = SC.apply_atm_accretion(1_000.0, 100.0, mnav, x)
            by_apply = (resid / shares) / (1_000.0 / 100.0) - 1
            assert by_apply == pytest.approx(SC.accretion_yield(mnav, x), abs=1e-12)


def test_dilution_for_yield_round_trips() -> None:
    """反解出來的增發比例,代回去必須得到原來的目標。"""
    for mnav in (1.05, 1.2, 1.5, 2.0):
        for target in (0.01, 0.03, 0.049):
            x = SC.dilution_for_yield(mnav, target)
            assert x is not None
            assert SC.accretion_yield(mnav, x) == pytest.approx(target, rel=1e-12)


def test_the_yield_ceiling_is_mnav_minus_one() -> None:
    """y < m − 1 是硬上限:超過它的目標回 None,而不是一個很大的數字。

    這是 01-architecture.md §7.1 的規模陷阱。寫成測試的理由是
    **「不可達」與「需要很大的增發」在程式裡長得一樣**,很容易被
    下游當成後者顯示出去。
    """
    for mnav in (1.1, 1.2, 1.5):
        ceiling = SC.max_accretion_yield(mnav)
        assert ceiling == pytest.approx(mnav - 1.0)
        # 逼近上限:需要的稀釋單調爆增,但永遠有解
        prev = 0.0
        for frac in (0.5, 0.9, 0.99, 0.999):
            x = SC.dilution_for_yield(mnav, ceiling * frac)
            assert x is not None and x > prev
            prev = x
        # 等於或超過上限:不可達
        assert SC.dilution_for_yield(mnav, ceiling) is None
        assert SC.dilution_for_yield(mnav, ceiling * 1.01) is None


def test_a_discount_makes_every_positive_yield_unreachable() -> None:
    """m ≤ 1 時增發只會稀釋,任何正的目標都不可達。"""
    for mnav in (0.8, 0.95, 1.0):
        assert SC.max_accretion_yield(mnav) == 0.0
        assert SC.dilution_for_yield(mnav, 0.01) is None
        assert SC.accretion_yield(mnav, 0.5) <= 0.0
