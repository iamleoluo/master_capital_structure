"""§4.1 五種 mNAV、§8 已知陷阱、§1.3 對數分解、§5.9 錨點交叉驗證。

這一檔的重點是**結構不變量**:不依賴任何單一資料源是否精確,
而是驗證「只要優先股存在,這些不等式就必須成立」。
不變量壞掉代表公式錯了;錨點對不上可能只是來源定義不同(見 data.FINDING_*)。
"""
from __future__ import annotations

import math
from datetime import date

import pytest

from mstr_cebe import core as C
from mstr_cebe import data as D


@pytest.fixture(scope="module")
def fwp():
    return D.fwp_snapshot(), D.FWP_BTC_PRICE, D.FWP_MSTR_PRICE


# ---------------------------------------------------------------------------
# §4.1 / §8.1 —— 五種 mNAV
# ---------------------------------------------------------------------------

def test_all_five_variants_computed(fwp):
    """§4.1:全部都要算,不能只算一種。"""
    cs, btc, px = fwp
    readings = C.all_mnavs(cs, btc, px)
    assert set(readings) == {v.value for v in C.MNavVariant}


def test_readings_straddle_1x_on_the_same_day(fwp):
    """§4.1 警告:同一天、同一個股價,五個數字可以落在 1.0x 兩側。"""
    cs, btc, px = fwp
    values = [r.value for r in C.all_mnavs(cs, btc, px).values()]
    assert min(values) < 1.0 < max(values), values


def test_every_reading_carries_variant_and_date(fwp):
    """§8.1:任何 mNAV 值都必須攜帶 variant + date,否則無意義。"""
    cs, btc, px = fwp
    for name, r in C.all_mnavs(cs, btc, px).items():
        assert isinstance(r, C.MNavReading)
        assert r.variant.value == name
        assert isinstance(r.as_of, date)
        assert r.btc_price == btc and r.mstr_price == px


def test_structural_inequality_basic_lt_diluted_lt_enterprise(fwp):
    """優先股存在時必然成立的排序 —— §5.10 的 2025-11-30 三讀數也符合此序。

    basic  < diluted    因為 FDSO > basic shares
    basic  < enterprise 因為加回的求償權遠大於扣掉的現金
    """
    cs, btc, px = fwp
    r = C.all_mnavs(cs, btc, px, cash_source=C.CashSource.BALANCE_SHEET)
    assert r["basic"].value < r["diluted"].value < r["enterprise"].value


@pytest.mark.parametrize("obs", [o for o in D.MNAV_OBSERVATIONS
                                 if len(o.readings) >= 2])
def test_published_readings_respect_the_ordering(obs):
    """§5.10 的多讀數觀測必須符合同一個排序,否則來源自相矛盾。"""
    order = ["basic", "diluted", "company", "cebe", "enterprise"]
    present = [(order.index(k), k, v) for k, v in obs.readings.items() if k in order]
    present.sort()
    values = [v for _, _, v in present]
    assert values == sorted(values), f"{obs.as_of}: {obs.readings}"


def test_basic_mnav_cannot_see_preferred_stock(fwp):
    """§1.2 核心論點:basic mNAV 在數學上**完全看不到優先股**。"""
    cs, btc, px = fwp
    baseline = C.mnav(cs, btc, px, C.MNavVariant.BASIC).value

    # 把優先股全部拿掉,basic mNAV 一點都不能變
    stripped = C.replace(cs, preferreds=())
    assert C.mnav(stripped, btc, px, C.MNavVariant.BASIC).value == pytest.approx(baseline)

    # 但 enterprise 與 company 一定要變
    assert C.mnav(stripped, btc, px, C.MNavVariant.ENTERPRISE).value != pytest.approx(baseline)
    assert (C.mnav(stripped, btc, px, C.MNavVariant.COMPANY).value
            < C.mnav(cs, btc, px, C.MNavVariant.COMPANY).value)


def test_preferred_issuance_widens_the_wedge(fwp):
    """§1.2:資本結構稀釋顯示在 basic 與 enterprise/CEBE 的**楔形差距**上。"""
    cs, btc, px = fwp

    def wedge(structure):
        r = C.all_mnavs(structure, btc, px)
        return r["enterprise"].value - r["basic"].value

    more_pref = C.replace(cs, preferreds=cs.preferreds + (
        C.PreferredSeries("STRX", 5e9, rank=6),))
    assert wedge(more_pref) > wedge(cs)


# ---------------------------------------------------------------------------
# §8.5 —— 2026-07-23 定義斷點
# ---------------------------------------------------------------------------

def test_company_mnav_timeseries_breaks_at_redefinition():
    """公司自訂 mNAV 前後不可比,comparable_key 必須把兩段分開。"""
    before = C.MNavReading(1.0, C.MNavVariant.COMPANY, date(2026, 7, 22), 6e4, 100)
    after = C.MNavReading(1.0, C.MNavVariant.COMPANY, date(2026, 7, 23), 6e4, 100)
    assert before.comparable_key != after.comparable_key
    assert C.COMPANY_MNAV_REDEFINITION == date(2026, 7, 23)


def test_pre_redefinition_company_mnav_is_flagged():
    cs = C.replace(D.fwp_snapshot(), as_of=date(2026, 6, 30))
    r = C.mnav(cs, 64_279, 97.33, C.MNavVariant.COMPANY)
    assert "not comparable" in r.note


def test_other_variants_are_not_broken_by_the_redefinition():
    """只有公司自訂 mNAV 斷開,basic/enterprise/CEBE 是第三方定義,連續。"""
    for v in (C.MNavVariant.BASIC, C.MNavVariant.ENTERPRISE, C.MNavVariant.CEBE):
        a = C.MNavReading(1.0, v, date(2026, 7, 22), 6e4, 100)
        b = C.MNavReading(1.0, v, date(2026, 7, 23), 6e4, 100)
        assert a.comparable_key == b.comparable_key


# ---------------------------------------------------------------------------
# §8.3 —— 面額 / 清算優先權 / 市值 三者不同
# ---------------------------------------------------------------------------

def test_liquidation_preference_is_stated_amount_times_shares():
    """§8.3:建模一律用 stated amount × 股數,不是 IPO 發行價。"""
    for ipo in D.PREFERRED_IPOS:
        assert ipo.ipo_liquidation_pref == pytest.approx(
            ipo.ipo_shares * ipo.stated_amount, rel=0.01), ipo.ticker
        # 發行價一律低於 stated amount ⇒ 用發行價會系統性低估求償權
        assert ipo.offer_price < ipo.stated_amount


def test_offer_price_would_understate_claims_materially():
    """用 IPO 發行價代替 stated amount,光是 IPO 當時就少算 $885M(約 14%)。

    這個誤差會隨 ATM 增發放大 —— 到 2026-06-30 優先股已達 $15.5B,
    同樣 14% 的低估就是 $2B 級別的錯誤。
    """
    ipos = D.PREFERRED_IPOS
    stated = sum(i.ipo_shares * i.stated_amount for i in ipos)
    offered = sum(i.ipo_shares * i.offer_price for i in ipos)
    gap = stated - offered
    assert gap == pytest.approx(885e6, rel=0.02)
    assert gap / stated == pytest.approx(0.14, abs=0.01)


def test_q2_2026_series_reconcile_to_the_filed_total():
    """2026-06-30 各系列 × $100 必須加總回 10-Q 的 $15,462,056 千元。"""
    pb = next(p for p in D.PREFERRED_BALANCES if p.as_of == date(2026, 6, 30))
    parts = [pb.strk, pb.strf, pb.strd, pb.strc, pb.stre_usd]
    assert sum(parts) == pytest.approx(pb.total, rel=1e-9)

    for ticker, shares in pb.shares_by_ticker.items():
        if ticker == "STRE":
            assert shares * 100 == pytest.approx(pb.stre_eur, rel=1e-9)
        else:
            amount = {"STRK": pb.strk, "STRF": pb.strf,
                      "STRD": pb.strd, "STRC": pb.strc}[ticker]
            assert shares * 100 == pytest.approx(amount, rel=1e-4), ticker

    assert sum(pb.shares_by_ticker.values()) == pytest.approx(pb.total_shares, rel=1e-4)


def test_strc_below_par_means_market_value_differs_from_claim():
    """STRC 曾跌到 $89(低於面額 11%)—— 市值 ≠ 清算優先權。"""
    _, price, _ = D.STRC_BELOW_PAR_EVENT
    assert price < 100
    shares = 104_894_705
    assert shares * 100 - shares * price > 1e9


# ---------------------------------------------------------------------------
# §8.6 —— STRE 匯率
# ---------------------------------------------------------------------------

def test_stre_stores_native_currency_and_as_of_fx():
    """§8.6:不能用當前匯率回溯套用,必須存 as-of 匯率。"""
    pb = next(p for p in D.PREFERRED_BALANCES if p.as_of == date(2026, 6, 30))
    assert pb.stre_eur is not None and pb.fx_eur_usd is not None
    assert pb.stre_eur * pb.fx_eur_usd == pytest.approx(pb.stre_usd, rel=1e-9)
    assert 1.0 < pb.fx_eur_usd < 1.3

    cs = D.capital_structure_timeline()
    q2 = next(c for c in cs if c.as_of == date(2026, 6, 30))
    stre = next(p for p in q2.preferreds if p.ticker == "STRE")
    assert stre.currency == "EUR"
    assert stre.liquidation_preference_native == pytest.approx(pb.stre_eur)
    assert stre.fx_rate_as_of == pytest.approx(pb.fx_eur_usd)


# ---------------------------------------------------------------------------
# §8.7 —— STRC 是變動利率
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("on,expected", [
    (date(2025, 8, 1), 9.00),
    (date(2026, 5, 31), 9.00),
    (date(2026, 6, 1), 11.50),
    (date(2026, 7, 31), 11.50),
    (date(2026, 8, 17), 12.00),
])
def test_strc_dividend_rate_is_not_hardcoded(on, expected):
    assert D.strc_dividend_rate(on) == expected


def test_strc_payment_frequency_change_recorded():
    when, change = D.STRC_PAYMENT_FREQUENCY_CHANGE
    assert when == date(2026, 6, 8)
    assert "semi-monthly" in change


# ---------------------------------------------------------------------------
# §8.8 —— STRK 可轉換,價內時排除在求償權之外
# ---------------------------------------------------------------------------

def test_strk_itm_threshold_is_1000_usd():
    """0.1 MSTR/股 × stated $100 ⇒ 價內門檻 $1,000。"""
    assert C.STRK_ITM_THRESHOLD_USD == 1000.0


def test_strk_excluded_from_claims_only_when_in_the_money(fwp):
    cs, btc, _ = fwp
    strk = cs.preferred_by_ticker["STRK"]
    total = cs.preferred_total_usd

    assert cs.preferred_otm_usd(97.33) == pytest.approx(total)          # 深度價外
    assert cs.preferred_otm_usd(999.99) == pytest.approx(total)
    assert cs.preferred_otm_usd(1000.0) == pytest.approx(total - strk)  # 價內 → 排除
    assert cs.preferred_otm_usd(5000.0) == pytest.approx(total - strk)


def test_net_bps_jumps_up_when_strk_converts(fwp):
    """價內 STRK 轉股 ⇒ 求償權減少 ⇒ Net BPS 跳升。這是不連續點,不是 bug。"""
    cs, btc, _ = fwp
    below = C.net_reserve_per_share_from(cs, btc, 999.99)
    above = C.net_reserve_per_share_from(cs, btc, 1000.01)
    assert above > below
    assert above - below == pytest.approx(
        cs.preferred_by_ticker["STRK"] / cs.shares_fdso, rel=1e-6)


def test_implied_price_converges_across_the_strk_discontinuity(fwp):
    """§4.4 的不動點迭代必須收斂,不能在 $1,000 附近震盪。"""
    cs, btc, _ = fwp
    for target in (0.5, 1.0, 2.0, 5.0, 10.0, 12.0, 20.0):
        px = C.implied_mstr_price(cs, btc, target, C.PriceBasis.NET)
        assert math.isfinite(px) and px > 0
        # 自洽:算出來的股價餵回去,mNAV 必須就是 target
        assert C.mnav(cs, btc, px, C.MNavVariant.COMPANY).value == pytest.approx(
            target, rel=1e-6), f"target {target}x → ${px:,.2f}"


# ---------------------------------------------------------------------------
# §5.3 —— 可轉債缺口必須顯式暴露,不能靜默當成 0
# ---------------------------------------------------------------------------

def test_convertible_conversion_prices_are_mostly_unknown():
    """附錄評為最大缺口。未知就回 UNKNOWN,不要猜。"""
    unknown = [c for c in D.CONVERTIBLES_2026 if c.conversion_price_usd is None]
    assert len(unknown) >= 4
    for c in unknown:
        assert c.moneyness(97.33) is C.MoneyNess.UNKNOWN
        assert c.confidence == "low"


def test_2027_notes_conversion_price_known():
    c = next(c for c in D.CONVERTIBLES_2026 if c.name == "2027 notes")
    assert c.conversion_price_usd == 143.25
    assert c.moneyness(97.33) is C.MoneyNess.OUT_OF_THE_MONEY
    assert c.moneyness(150.0) is C.MoneyNess.IN_THE_MONEY


def test_2027_notes_conversion_lowers_break_even():
    """cebetracker 情境:MSTR > $143.25 ⇒ break-even 從 $23,270 降到 $20,887。"""
    s = D.CONVERT_2027_SCENARIO
    cs = C.CapitalStructure(
        as_of=date(2026, 7, 5), btc_held=843_775,
        debt_notional_usd=19.63e9 * 0 + 6.71e9,
        preferreds=(C.PreferredSeries("ALL", 19.63e9 - 6.71e9, rank=1),),
        shares_basic=371.6e6,
    )
    before = C.break_even_btc(cs, C.ClaimsBasis.CEBETRACKER)
    assert before == pytest.approx(s["break_even_before"], rel=0.01)

    converted = C.replace(cs, debt_notional_usd=cs.debt_notional_usd - s["notional"])
    after = C.break_even_btc(converted, C.ClaimsBasis.CEBETRACKER)
    assert after < before
    assert after == pytest.approx(s["break_even_after"], rel=0.02)


def test_timeline_does_not_silently_use_incomplete_convertible_series():
    """分系列面額加總 ≠ 總額,所以時間軸一律用總額,convertibles 留空。"""
    partial = sum(c.notional_usd for c in D.CONVERTIBLES_2026)
    assert partial < 6.754e9      # 確實不完整
    for cs in D.capital_structure_timeline():
        assert cs.convertibles == ()
        # 求償權用總額,不會因為缺系列而漏算
        if cs.as_of >= date(2025, 12, 31):
            assert cs.debt_notional_usd > 6e9


def test_unknown_moneyness_notional_is_reportable():
    """轉換價未知的面額保守計入求償權,但要能查得出來有多少。"""
    cs = C.CapitalStructure(as_of=date(2026, 8, 13), btc_held=840_447,
                            debt_notional_usd=6.754e9,
                            convertibles=D.CONVERTIBLES_2026)
    assert cs.debt_moneyness_unknown_usd(97.33) > 2e9
    # 未知者仍被計入(保守)
    assert cs.debt_otm_usd(97.33) >= cs.debt_moneyness_unknown_usd(97.33)


# ---------------------------------------------------------------------------
# §8.9 —— Split
# ---------------------------------------------------------------------------

def test_split_check_anchor():
    when, price, field, _ = D.SPLIT_CHECK
    assert D.SPLIT_DATE == date(2024, 8, 7) and D.SPLIT_RATIO == 10
    assert when == date(2024, 11, 21) and price == 543.0
    # 未調整的話會是 $5,430
    assert price * D.SPLIT_RATIO == 5430.0
    # $543 是盤中高點,檢查必須比對 high 而非 close
    assert field == "high"
    assert D.ATH_CLOSE_2024_11_21 == pytest.approx(397.28)
    assert D.ATH_CLOSE_2024_11_21 < price


def test_close_basis_decomposition_is_milder_than_the_spec():
    """FINDING:規格書用盤中高點 $543 當起點,誇大了壓縮幅度約 37%。"""
    a = D.LOG_DECOMPOSITION_ANCHOR
    _, p1 = a["mstr_price"]
    b0, b1 = a["btc_price"]
    btc0, shares0 = 446_400.0, 248e6
    btc1 = 840_447.0
    shares1 = btc1 / ((btc0 / shares0) * a["bps_ratio"])

    high = C.decompose_basic_mnav(a["start"], a["end"], 543.0, p1, b0, b1,
                                  btc0, btc1, shares0, shares1)
    close = C.decompose_basic_mnav(a["start"], a["end"],
                                   D.ATH_CLOSE_2024_11_21, p1, b0, b1,
                                   btc0, btc1, shares0, shares1)

    assert high.price_ratio == pytest.approx(0.179, abs=0.001)
    assert close.price_ratio == pytest.approx(0.245, abs=0.001)
    assert close.log_price == pytest.approx(-1.406, abs=0.005)

    # 只有股價項改變,BTC 與稀釋項完全不受影響
    assert close.log_btc == pytest.approx(high.log_btc)
    assert close.log_shares == pytest.approx(high.log_shares)

    # 結論方向不變
    assert close.log_price < 0 < close.log_btc
    assert abs(close.log_price) > abs(close.log_shares) * 3


# ---------------------------------------------------------------------------
# §1.3 —— 對數分解
# ---------------------------------------------------------------------------

def test_log_decomposition_reproduces_the_spec():
    a = D.LOG_DECOMPOSITION_ANCHOR
    p0, p1 = a["mstr_price"]
    b0, b1 = a["btc_price"]

    # 造一組 btc_held / shares 使 BPS 上升 1.367 倍
    btc0, shares0 = 446_400.0, 248e6
    btc1 = 840_447.0
    shares1 = btc1 / ((btc0 / shares0) * a["bps_ratio"])

    d = C.decompose_basic_mnav(a["start"], a["end"], p0, p1, b0, b1,
                               btc0, btc1, shares0, shares1)

    assert d.price_ratio == pytest.approx(0.179, abs=0.001)
    assert d.btc_ratio == pytest.approx(1.5246, abs=0.001)
    assert d.shares_ratio == pytest.approx(1 / a["bps_ratio"], rel=1e-9)

    net = d.price_ratio * d.btc_ratio * d.shares_ratio
    assert net == pytest.approx(a["expected_net_effect"], abs=0.005)

    # 對數項必須可加,且加總等於總對數效果
    assert d.log_price + d.log_btc + d.log_shares == pytest.approx(d.log_total)


def test_decomposition_signs_match_the_narrative():
    """§1.3 結論:BTC 下跌**墊高** mNAV;稀釋是次要拖累;股價是主因。"""
    a = D.LOG_DECOMPOSITION_ANCHOR
    p0, p1 = a["mstr_price"]
    b0, b1 = a["btc_price"]
    btc0, shares0 = 446_400.0, 248e6
    btc1 = 840_447.0
    shares1 = btc1 / ((btc0 / shares0) * a["bps_ratio"])
    d = C.decompose_basic_mnav(a["start"], a["end"], p0, p1, b0, b1,
                               btc0, btc1, shares0, shares1)

    assert d.log_price < 0            # 股價:主要拖累
    assert d.log_btc > 0              # BTC 下跌:反而墊高
    assert d.log_shares < 0           # 稀釋:拖累
    assert abs(d.log_price) > abs(d.log_shares) * 3   # 股價效果遠大於稀釋
    assert abs(d.log_shares) == pytest.approx(0.31, abs=0.02)


def test_decomposition_is_exact_not_approximate():
    """三項相乘必須完全還原,殘差為 0 —— 這是恆等式不是回歸。"""
    d = C.decompose_basic_mnav(
        date(2024, 11, 21), date(2026, 8, 13),
        543.0, 97.33, 98_000, 64_279, 446_400, 840_447, 248e6, 394e6)
    assert d.residual == pytest.approx(0.0, abs=1e-12)
    assert d.reconstructed_mnav == pytest.approx(d.mnav_end, rel=1e-12)


# ---------------------------------------------------------------------------
# §5.9 —— 第三方錨點交叉驗證(含已知缺陷)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("anchor", [a for a in D.CEBE_ANCHORS
                                    if a.label != "2026-07-05"])
def test_cebe_anchor_claims_pct_self_consistent(anchor):
    """claims% 必須等於(求償權 ÷ BTC 價)÷ BTC 持有量,容差 2%。"""
    computed = anchor.net_claims_usd / anchor.btc_price / anchor.btc_held
    assert computed == pytest.approx(anchor.claims_pct, rel=0.02), anchor.label


def test_2026_07_05_anchor_has_a_bad_claims_figure():
    """FINDING:§5.9 的 ~$21,000M 與同列的 38.3% 矛盾;$19.63B 才對。"""
    a = next(x for x in D.CEBE_ANCHORS if x.label == "2026-07-05")
    as_filed = a.net_claims_usd / a.btc_price / a.btc_held
    assert as_filed == pytest.approx(0.4095, abs=0.001)
    assert abs(as_filed - a.claims_pct) > 0.02        # 對不上

    corrected = D.FINDING_2026_07_05_CLAIMS["corrected_value"]
    fixed = corrected / a.btc_price / a.btc_held
    assert fixed == pytest.approx(a.claims_pct, abs=0.001)   # 修正後對上


def test_2026_07_05_anchor_reproducible_with_basic_shares():
    """修正 claims 後,BPS 與 CEBE 都能用 §5.4 的 371.6M basic 股數重現。"""
    a = next(x for x in D.CEBE_ANCHORS if x.label == "2026-07-05")
    cs = C.CapitalStructure(
        as_of=a.as_of, btc_held=a.btc_held,
        debt_notional_usd=D.FINDING_2026_07_05_CLAIMS["corrected_value"],
        shares_basic=371.6e6, shares_assumed_diluted=371.6e6)

    assert C.gross_bps_sats(a.btc_held, 371.6e6) == pytest.approx(a.bps_sats, rel=1e-3)
    assert C.cebe_sats(cs, a.btc_price) == pytest.approx(a.cebe_sats, rel=1e-3)


def test_cebe_anchor_denominators_are_inconsistent_across_dates():
    """FINDING:4 月反解 ~398.7M 股,7 月 ~371.6M。basic 股數不可能下降。"""
    apr = next(x for x in D.CEBE_ANCHORS if x.label == "2026-04-12")
    jul = next(x for x in D.CEBE_ANCHORS if x.label == "2026-07-05")
    shares_apr = apr.btc_held / (apr.bps_sats / 1e8)
    shares_jul = jul.btc_held / (jul.bps_sats / 1e8)
    assert shares_apr > shares_jul + 20e6, (shares_apr, shares_jul)
    assert D.FINDING_CEBE_DENOMINATOR["impact"]


def test_coincidence_hypothesis_self_consistency_check():
    """§5.9 的 22.8% 巧合論證:(BPS − CEBE) / BPS 必須等於 claims%。

    這個檢查與股數分母無關(分子分母同一個股數會約掉),所以即使 4 月與 7 月
    分母基準不同,巧合判定仍然成立。
    """
    apr = next(x for x in D.CEBE_ANCHORS if x.label == "2026-04-12")
    implied = (apr.bps_sats - apr.cebe_sats) / apr.bps_sats
    assert implied == pytest.approx(0.228, abs=0.002)

    jan = next(x for x in D.CEBE_ANCHORS if x.label == "2026-01")
    assert jan.claims_pct == pytest.approx(apr.claims_pct, abs=0.001)

    # 推翻條件:若 4 月 BTC 價明顯低於 ~$95K 則不成立
    assert apr.btc_price >= 95_000


def test_claims_pct_rises_monotonically_through_2025_2026():
    """§1.2 的稀釋軌跡:優先股開始吃掉普通股。"""
    ordered = sorted(D.CEBE_ANCHORS, key=lambda a: a.as_of)
    pcts = [a.claims_pct for a in ordered]
    assert pcts[0] == pytest.approx(0.12)
    assert pcts[-1] == pytest.approx(0.398)
    # 2024-Q4 是低點(BTC 漲 + 求償權小),之後單調上升
    trough = pcts.index(min(pcts))
    assert pcts[trough:] == sorted(pcts[trough:])


# ---------------------------------------------------------------------------
# §8.4 —— 三個求償權總額
# ---------------------------------------------------------------------------

def test_three_claims_totals_in_circulation(fwp):
    cs, _, px = fwp
    totals = D.CLAIMS_TOTALS_IN_CIRCULATION
    assert totals["company"][0] == pytest.approx(
        D.PARAMS_2026_08_13["debt_otm_notional"]
        + D.PARAMS_2026_08_13["pref_otm_notional"], rel=0.01)
    assert C.net_senior_claims_usd(cs, C.ClaimsBasis.COMPANY, px) == pytest.approx(
        totals["company"][0], rel=0.01)
    assert C.net_senior_claims_usd(cs, C.ClaimsBasis.MNAV_COM, px) == pytest.approx(
        totals["mnav_com"][0], rel=0.01)


def test_claims_basis_ordering(fwp):
    """毛額含 STRE > 漏 STRE > 扣現金 > 扣 USD Reserve。"""
    cs, _, px = fwp
    company = C.net_senior_claims_usd(cs, C.ClaimsBasis.COMPANY, px)
    mnav_com = C.net_senior_claims_usd(cs, C.ClaimsBasis.MNAV_COM, px)
    ceb = C.net_senior_claims_usd(cs, C.ClaimsBasis.CEBETRACKER, px)
    net_res = C.net_senior_claims_usd(cs, C.ClaimsBasis.COMPANY_NET_RESERVE, px)
    assert company > mnav_com > ceb > net_res


# ---------------------------------------------------------------------------
# §3 —— forward-fill 與申報日標記
# ---------------------------------------------------------------------------

def test_forward_fill_marks_staleness():
    tl = D.capital_structure_timeline()
    cs = C.as_of_structure(tl, date(2026, 5, 15))
    assert cs.as_of == date(2026, 5, 15)
    assert "forward-filled" in cs.note
    assert "2026-03-31" in cs.note


def test_forward_fill_exact_hit_is_not_marked():
    tl = D.capital_structure_timeline()
    cs = C.as_of_structure(tl, date(2026, 6, 30))
    assert "forward-filled" not in cs.note


def test_no_structure_before_first_observation():
    tl = D.capital_structure_timeline()
    with pytest.raises(ValueError):
        C.as_of_structure(tl, date(2024, 1, 1))


def test_observation_dates_exposed_for_charting():
    """§3:圖上要標出申報日,區分真實觀測與延續假設。"""
    dates = C.observation_dates(D.capital_structure_timeline())
    assert dates == sorted(dates)
    assert date(2026, 6, 30) in dates and date(2026, 8, 13) in dates


# ---------------------------------------------------------------------------
# §4.5 —— 融資來源歸因
# ---------------------------------------------------------------------------

def test_preferred_funded_purchases_are_cebe_neutral():
    """§4.5:優先股融資買幣 → CEBE-neutral,但 BPS 上升 = phantom growth。"""
    assert C.classify_funding("preferred_atm") == "neutral"


def test_common_atm_depends_on_issue_price():
    assert C.classify_funding("common_atm", issue_mnav_net=1.2) == "accretive"
    assert C.classify_funding("common_atm", issue_mnav_net=0.8) == "dilutive"
    assert C.classify_funding("common_atm") == "unknown"


def test_discounted_preferred_buyback_is_accretive():
    assert C.classify_funding("pref_buyback_discount") == "accretive"


def test_phantom_growth_is_positive_when_preferred_dominates(fwp):
    """Gross BPS 與 Net BPS 的落差就是 phantom growth(§7.2.1 的面積)。"""
    cs, btc, px = fwp
    gap = C.phantom_growth_sats(cs, btc, px)
    assert gap > 50_000
    gross = C.gross_bps_sats(cs.btc_held, cs.shares_assumed_diluted)
    net = C.net_bps_sats(C.net_reserve_per_share_from(cs, btc, px), btc)
    assert gap == pytest.approx(gross - net)


def test_phantom_growth_vanishes_without_senior_claims(fwp):
    """沒有優先股也沒有債時,兩個 BPS 只差在分母。"""
    cs, btc, px = fwp
    clean = C.replace(cs, preferreds=(), debt_notional_usd=0.0,
                      usd_reserve_usd=0.0,
                      shares_assumed_diluted=cs.shares_fdso)
    assert C.phantom_growth_sats(clean, btc, px) == pytest.approx(0.0, abs=1e-6)
