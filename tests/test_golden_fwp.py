"""§6 驗證錨點 —— 這組測試不過,後面全部白做(§9 步驟 1)。

關於容差的說明(重要):
    規格書 §6.1 寫「必須精確吻合」,附錄也把 FWP 參數的信心標為「高 —— 已完全反解驗證」。
    實測結果是**做不到逐分吻合**,而且原因不在我們的公式,在 FWP 自己的輸入:
    usd_reserve / debt_otm / pref_otm 三個數字都只揭露到 $1M 精度,fdso 只寫 "~398.2M"。

    證據見 test_no_single_fdso_reproduces_table_exactly:不存在任何單一 FDSO
    能在單一 rounding 規則下重現全部六列。因此本檔案用
        絕對容差 $0.02 / 相對容差 1 bp
    這是「公式正確」能達到的最緊上限,不是隨手放寬。
"""
from __future__ import annotations

from datetime import date

import pytest

from mstr_cebe import core as C
from mstr_cebe import data as D

# 容差:FWP 輸入本身的四捨五入誤差上限
ABS_TOL_USD = 0.02
REL_TOL_BP = 1.0        # 1 basis point = 0.01%


def _within(got: float, official: float,
            abs_tol: float = ABS_TOL_USD, rel_bp: float = REL_TOL_BP) -> bool:
    return (abs(got - official) <= abs_tol
            or abs(got - official) / abs(official) * 1e4 <= rel_bp)


# ---------------------------------------------------------------------------
# §6.1 黃金測試:重現 Strategy 官方敏感度表
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("btc_price,official", D.FWP_SENSITIVITY_TABLE)
def test_fwp_sensitivity_table(btc_price, official):
    got = C.net_reserve_per_share(btc_price, **D.PARAMS_2026_08_13)
    assert _within(got, official), (
        f"BTC ${btc_price:,}: official ${official}, got ${got:.4f} "
        f"({(got - official) / official * 1e4:+.2f}bp)"
    )


def test_fwp_worked_example_64279():
    """§6.1 的逐步驗算示範,逐項比對中間值。"""
    p = D.PARAMS_2026_08_13
    nav = p["btc_held"] * 64_279
    assert nav == pytest.approx(54_023_092_713, abs=1)
    step = nav + p["usd_reserve"]
    assert step == pytest.approx(58_673_092_713, abs=1)
    step -= p["debt_otm_notional"]
    assert step == pytest.approx(51_919_092_713, abs=1)
    step -= p["pref_otm_notional"]
    assert step == pytest.approx(36_680_092_713, abs=1)
    # ⚠️ 規格書 §6.1 的驗算示範最後一行寫 "= $92.115",那是筆誤:
    #    36,680,092,713 ÷ 398,220,309 = 92.11005。官方揭露值 $92.11 才是對的。
    assert step / p["fdso"] == pytest.approx(92.11005, abs=1e-4)


def test_no_single_fdso_reproduces_table_exactly():
    """證明「精確吻合」在數學上不可能 —— 這是容差存在的理由,不是失敗。

    對每一列反解出「能產生該官方值」的 FDSO 區間(假設官方值為截斷到分),
    六個區間的交集為空 ⇒ FWP 的輸入本身已被四捨五入。
    """
    p = D.PARAMS_2026_08_13

    def numerator(btc):
        return (p["btc_held"] * btc + p["usd_reserve"]
                - p["debt_otm_notional"] - p["pref_otm_notional"])

    lo = max(numerator(b) / (o + 0.01) for b, o in D.FWP_SENSITIVITY_TABLE)
    hi = min(numerator(b) / o for b, o in D.FWP_SENSITIVITY_TABLE)
    assert lo >= hi, (
        "交集非空,代表存在單一 FDSO 可精確重現全表 —— "
        f"若如此請把容差收緊到 0:區間 ({lo:,.0f}, {hi:,.0f}]"
    )


def test_spec_fdso_is_within_one_basis_point_everywhere():
    """規格書給的 FDSO 雖非精確,但六列全部落在 1bp 內。"""
    worst = max(
        abs(C.net_reserve_per_share(b, **D.PARAMS_2026_08_13) - o) / o * 1e4
        for b, o in D.FWP_SENSITIVITY_TABLE
    )
    assert worst <= REL_TOL_BP, f"最差 {worst:.2f}bp"


# ---------------------------------------------------------------------------
# §6.2 其他必過檢查(同一份 FWP)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def fwp():
    return D.fwp_snapshot(), D.FWP_BTC_PRICE, D.FWP_MSTR_PRICE


def test_gross_bps_sats(fwp):
    cs, btc, _ = fwp
    got = C.gross_bps_sats(cs.btc_held, cs.shares_assumed_diluted)
    assert _within(got, D.FWP_DERIVED_METRICS["gross_bps_sats"], abs_tol=10)


def test_gross_bps_usd(fwp):
    cs, btc, _ = fwp
    got = C.gross_bps_usd(cs.btc_held, cs.shares_assumed_diluted, btc)
    assert _within(got, D.FWP_DERIVED_METRICS["gross_bps_usd"])


def test_net_bps_sats(fwp):
    cs, btc, px = fwp
    nrps = C.net_reserve_per_share_from(cs, btc, px)
    got = C.net_bps_sats(nrps, btc)
    assert _within(got, D.FWP_DERIVED_METRICS["net_bps_sats"], abs_tol=10)


def test_net_bps_usd(fwp):
    cs, btc, px = fwp
    got = C.net_reserve_per_share_from(cs, btc, px)
    assert _within(got, D.FWP_DERIVED_METRICS["net_bps_usd"])


def test_company_mnav(fwp):
    """官方 1.06x 只揭露到小數兩位,所以比到 0.005。"""
    cs, btc, px = fwp
    reading = C.mnav(cs, btc, px, C.MNavVariant.COMPANY)
    assert reading.value == pytest.approx(D.FWP_DERIVED_METRICS["mnav_company"], abs=0.005)
    assert reading.variant is C.MNavVariant.COMPANY
    assert reading.as_of == date(2026, 8, 13)


def test_amplification(fwp):
    cs, btc, px = fwp
    got = C.amplification(cs, btc, px)
    assert got == pytest.approx(D.FWP_DERIVED_METRICS["amplification"], abs=0.005)


def test_market_cap(fwp):
    cs, _, px = fwp
    got = C.market_cap(cs, px)
    assert _within(got, D.FWP_DERIVED_METRICS["market_cap_usd"], abs_tol=1e6)


def test_enterprise_value_uses_usd_reserve_not_balance_sheet_cash(fwp):
    """§5.5 / §8.4:官方 EV $55.710B 扣的是 USD Reserve,不是資產負債表現金。"""
    cs, _, px = fwp
    got = C.enterprise_value(cs, px, C.CashSource.USD_RESERVE)
    assert _within(got, D.FWP_DERIVED_METRICS["enterprise_value_usd"], abs_tol=2e6)

    # 用資產負債表現金會差 $2.2B —— 這就是混用的代價
    wrong = C.enterprise_value(cs, px, C.CashSource.BALANCE_SHEET)
    assert abs(wrong - D.FWP_DERIVED_METRICS["enterprise_value_usd"]) > 2e9


def test_btc_arr_breakeven(fwp):
    cs, btc, _ = fwp
    got = C.btc_arr_breakeven(cs.annual_obligations_usd, cs.btc_nav_usd(btc)) * 100
    assert got == pytest.approx(D.FWP_DERIVED_METRICS["btc_arr_breakeven_pct"], abs=0.005)


# ---------------------------------------------------------------------------
# §6.3 Break-even 三種算法 —— 全部都要實作
# ---------------------------------------------------------------------------

def test_break_even_three_definitions():
    a = D.BREAK_EVEN_ANCHORS

    official = a["strategy_official"]
    got = (official["claims_usd"] - official["less_usd_reserve"]) / official["btc_held"]
    assert got == pytest.approx(official["expected"], rel=1e-3)

    ceb = a["cebetracker"]
    got = ceb["claims_usd"] / ceb["btc_held"]
    assert got == pytest.approx(ceb["expected"], rel=1e-3)

    mn = a["mnav_com_gross"]
    got = mn["claims_usd"] / mn["btc_held"]
    assert got == pytest.approx(mn["expected"], rel=1e-3)


def test_break_even_all_bases_are_distinct(fwp):
    """§6.3 警告:三個數字都對。系統不能只顯示一個,也不該讓它們相等。"""
    cs, _, px = fwp
    bases = C.break_even_all_bases(cs, px)
    assert len(bases) == len(C.ClaimsBasis)
    assert len(set(round(v, 2) for v in bases.values())) >= 3

    # 官方(扣 USD Reserve)必然低於毛額定義
    assert bases["company_net_reserve"] < bases["company"]


def test_break_even_from_fwp_matches_official_20635(fwp):
    cs, _, px = fwp
    got = C.break_even_btc(cs, C.ClaimsBasis.COMPANY_NET_RESERVE, px)
    assert got == pytest.approx(20_635.0, rel=1e-3)


def test_mnav_com_basis_omits_stre(fwp):
    """§8.4:mnav.com 的 $21.1B 毛額**漏掉 STRE**。刻意複製這個定義差異。"""
    cs, _, px = fwp
    with_stre = C.net_senior_claims_usd(cs, C.ClaimsBasis.COMPANY, px)
    without = C.net_senior_claims_usd(cs, C.ClaimsBasis.MNAV_COM, px)
    stre = cs.preferred_by_ticker["STRE"]
    assert with_stre - without == pytest.approx(stre, rel=1e-9)
    assert without == pytest.approx(21.05 * D.B, rel=0.01)


# ---------------------------------------------------------------------------
# §7.3 對照表的正確答案
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("target,official",
                         sorted(D.IMPLIED_PRICE_ANSWERS_2026_08_13["net"].items()))
def test_implied_price_net_basis(fwp, target, official):
    cs, btc, _ = fwp
    got = C.implied_mstr_price(cs, btc, target, C.PriceBasis.NET)
    assert _within(got, official, abs_tol=0.05)


@pytest.mark.parametrize("target,official",
                         sorted(D.IMPLIED_PRICE_ANSWERS_2026_08_13["basic"].items()))
def test_implied_price_basic_basis(fwp, target, official):
    """§7.3 的「Basic 基準」用 basic shares(394.2M),不是 Gross BPS 的 423.8M。"""
    cs, btc, _ = fwp
    got = C.implied_mstr_price(cs, btc, target, C.PriceBasis.BASIC)
    assert got == pytest.approx(official, rel=0.005), (
        f"{target}x: 規格書約值 ~${official}, got ${got:.2f}"
    )


def test_gross_and_basic_bases_differ_by_denominator(fwp):
    """§8.2 只說兩個分母,其實是三個。這個測試把差異釘住。"""
    cs, btc, _ = fwp
    gross = C.implied_mstr_price(cs, btc, 1.0, C.PriceBasis.GROSS)
    basic = C.implied_mstr_price(cs, btc, 1.0, C.PriceBasis.BASIC)
    assert gross == pytest.approx(127.46, abs=0.02)
    assert basic == pytest.approx(137.04, abs=0.05)
    ratio = basic / gross
    assert ratio == pytest.approx(cs.shares_assumed_diluted / cs.shares_basic, rel=1e-9)


def test_round_trip_price_and_btc(fwp):
    """implied_mstr_price 與 implied_btc_price 必須互為反函數。"""
    cs, btc, _ = fwp
    for basis in (C.PriceBasis.GROSS, C.PriceBasis.BASIC,
                  C.PriceBasis.NET, C.PriceBasis.CEBE):
        for target in (0.8, 1.0, 1.5, 2.0):
            px = C.implied_mstr_price(cs, btc, target, basis)
            back = C.implied_btc_price(cs, px, target, basis) if basis is not C.PriceBasis.BASIC \
                else px * cs.shares_basic / (target * cs.btc_held)
            assert back == pytest.approx(btc, rel=1e-6), f"{basis} @ {target}x"


# ---------------------------------------------------------------------------
# 2026-08-24 FWP —— 較新的一份官方敏感度表(同樣是 Tier 1 黃金錨點)
#
# 這一份與 08-13 那份最大的差別是優先股 notional 掉了 $273M($15.239B →
# $14.966B),對應 STRC 從 7 月底開始的折價回購。兩份都釘住,任何一份被
# 改壞都會立刻爆掉。
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("btc_price,official", D.FWP_2026_08_24_SENSITIVITY_TABLE)
def test_fwp_2026_08_24_sensitivity_table(btc_price, official):
    got = C.net_reserve_per_share(btc_price, **D.PARAMS_2026_08_24)
    assert _within(got, official), (
        f"BTC ${btc_price:,}: official ${official}, got ${got:.4f} "
        f"({(got - official) / official * 1e4:+.2f}bp)"
    )


def test_fwp_2026_08_24_gross_bps():
    """Gross BPS 的分母是 assumed diluted,不是 FDSO —— 換錯就會差 6%。"""
    got = C.gross_bps_sats(D.PARAMS_2026_08_24["btc_held"],
                           D.FWP_2026_08_24_SHARES_ASSUMED_DILUTED)
    official = D.FWP_2026_08_24_DERIVED_METRICS["gross_bps_sats"]
    assert abs(got - official) / official <= 1e-3, f"official {official}, got {got:.0f}"


def test_fwp_2026_08_24_net_reserve_total():
    """Net Reserve 總額 = BTC Reserve + USD Assets − 債 − 優先股。"""
    p = D.PARAMS_2026_08_24
    # params 的 usd_reserve 已經是 USD Assets(Reserve + Cash),這裡順便確認拆分一致
    assert abs(p["usd_reserve"]
               - (D.FWP_2026_08_24_USD_RESERVE + D.FWP_2026_08_24_USD_CASH)) < 1e7
    got = (p["btc_held"] * D.FWP_2026_08_24_BTC_PRICE + p["usd_reserve"]
           - p["debt_otm_notional"] - p["pref_otm_notional"])
    official = D.FWP_2026_08_24_DERIVED_METRICS["net_reserve_usd"]
    assert abs(got - official) / official <= 2e-4, (
        f"official ${official/1e9:.3f}B, got ${got/1e9:.3f}B")


def test_fwp_2026_08_24_amplification():
    """放大倍數 = BTC Reserve / Net Reserve。"""
    p = D.PARAMS_2026_08_24
    btc_reserve = p["btc_held"] * D.FWP_2026_08_24_BTC_PRICE
    net_reserve = D.FWP_2026_08_24_DERIVED_METRICS["net_reserve_usd"]
    got = btc_reserve / net_reserve
    assert abs(got - D.FWP_2026_08_24_DERIVED_METRICS["amplification"]) <= 0.005


def test_preferred_notional_fell_between_the_two_fwps():
    """回歸測試:兩份 FWP 之間優先股 notional 必須是**下降**的。

    這是 STRC 折價回購留下的痕跡。若哪天有人把新 FWP 的參數抄錯成上升,
    整個 CEBE 會往錯的方向跑,這裡先擋下來。
    """
    old = D.PARAMS_2026_08_13["pref_otm_notional"]
    new = D.PARAMS_2026_08_24["pref_otm_notional"]
    assert new < old, f"優先股 notional 應下降:{old/1e9:.3f}B → {new/1e9:.3f}B"
    assert 0.2e9 < (old - new) < 0.4e9, "降幅應在 $200M–$400M 之間(對應約 280 萬股回購)"
