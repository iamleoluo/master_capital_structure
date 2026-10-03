"""工具箱的測試。

這支的重點不是「函式會不會跑」,而是**代數宣告不能說謊**:
每一把工具的 `accretive` 謂詞都拿 `apply` 去驗,門檻兩側各驗一次。
改了 apply 卻沒改謂詞(或反過來),這裡就會紅。

reference/07-toolbox.md 的論述成不成立,看這支過不過。
"""
from __future__ import annotations

import math

import pytest

from mstr_cebe import toolbox as T


# 用接近真實的結構當基準:846k 顆幣、$14.84B 求償權、416M 股、$86k 幣價
BASE = T.State(held=846_000.0, claims=14.84e9, shares=415.9e6, price=86_404.0)


def test_state_reproduces_the_site_numbers():
    """L1 的尺要跟網站上的數字對得起來,否則底下全部免談。"""
    assert T.gross_bps(BASE) == pytest.approx(203_414, rel=1e-3)
    assert T.cebe(BASE) == pytest.approx(162_122, rel=1e-3)
    assert T.claims_per_share(BASE) == pytest.approx(
        T.gross_bps(BASE) - T.cebe(BASE), rel=1e-9)


def test_leverage_and_wipeout_are_consistent():
    """A(p) = 1/(1 − p₀/p) —— 兩個式子必須是同一件事。"""
    p0 = T.wipeout_price(BASE)
    assert T.leverage(BASE) == pytest.approx(1 / (1 - p0 / BASE.price), rel=1e-12)
    # 幣價正好跌到 p₀ 時,殘值歸零
    at_zero = T.State(BASE.held, BASE.claims, BASE.shares, p0)
    assert T.cebe(at_zero) == pytest.approx(0.0, abs=1e-6)


# --------------------------------------------------------------- 結構上的零

def test_buying_btc_with_cash_is_exactly_neutral():
    """不是「幾乎是零」,是零。這條錯了,phantom growth 整個論述就垮了。"""
    e = T.effect(T.BUY_BTC, BASE, c=1e9)
    assert e["dE"] == pytest.approx(0.0, abs=1e-9)
    assert e["dB"] > 0


def test_selling_btc_into_reserve_is_exactly_neutral():
    e = T.effect(T.SELL_BTC, BASE, x=1_000.0)
    assert e["dE"] == pytest.approx(0.0, abs=1e-9)
    assert e["dB"] < 0


def test_preferred_buyback_is_invisible_to_gross_bps():
    """B 的式子裡沒有求償權,所以這裡的零是結構性的,不是數值巧合。"""
    e = T.effect(T.BUYBACK_PREFERRED, BASE, c=0.73e9, F=1e9)
    assert e["dB"] == pytest.approx(0.0, abs=1e-12)
    assert e["dE"] > 0


def test_carry_is_the_only_unconditional_negative():
    """其餘工具的正負都取決於價格條件,只有這一項無論如何都是負的。"""
    for price in (30_000.0, 86_404.0, 250_000.0):
        s = T.State(BASE.held, BASE.claims, BASE.shares, price)
        assert T.effect(T.CARRY, s, c=1e8)["dE"] < 0


# --------------------------------------------------------------- 謂詞不能說謊

def _params_at_mnav(s: T.State, m: float) -> float:
    """由恆等式反解:要讓 mNAV 等於 m,股價該是多少。"""
    return m * T.cebe(s) / T.SATS * s.price


@pytest.mark.parametrize("m,expected", [(1.30, True), (1.05, True),
                                        (0.95, False), (0.70, False)])
def test_atm_predicate_matches_reality(m, expected):
    """ATM 的宣告是 m > 1。拿 apply 驗,門檻兩側都要對。"""
    P = _params_at_mnav(BASE, m)
    assert T.COMMON_ATM.accretive(BASE, {"n": 1e6, "P": P}) is expected
    assert (T.effect(T.COMMON_ATM, BASE, n=1e6, P=P)["dE"] > 0) is expected


@pytest.mark.parametrize("m,expected", [(0.70, True), (0.95, True),
                                        (1.05, False), (1.30, False)])
def test_common_buyback_predicate_matches_reality(m, expected):
    """庫藏股是反過來的:m < 1 才加分。這就是授權掛著不動用的原因。"""
    P = _params_at_mnav(BASE, m)
    assert T.COMMON_BUYBACK.accretive(BASE, {"n": 1e6, "P": P}) is expected
    assert (T.effect(T.COMMON_BUYBACK, BASE, n=1e6, P=P)["dE"] > 0) is expected


def test_common_buyback_always_lifts_gross_bps():
    """兩個指標正面打架:m > 1 時 E 下降,但 B 照樣上升。"""
    P = _params_at_mnav(BASE, 1.30)
    e = T.effect(T.COMMON_BUYBACK, BASE, n=1e6, P=P)
    assert e["dB"] > 0 and e["dE"] < 0


@pytest.mark.parametrize("d,m,expected", [
    (0.27, 0.78, True), (0.27, 0.68, False),      # 門檻 0.73 兩側
    (0.10, 0.95, True), (0.10, 0.85, False),      # 門檻 0.90 兩側
    (0.00, 1.05, True), (0.00, 0.95, False),      # 退化成純 ATM
])
def test_atm_to_buyback_threshold_is_one_minus_d(d, m, expected):
    """組合 C 的宣告是 m > 1 − d。折價越深,適用區間越寬。"""
    P = _params_at_mnav(BASE, m)
    kw = {"n": 1e6, "P": P, "d": d}
    assert T.ATM_TO_BUYBACK.accretive(BASE, kw) is expected
    assert (T.effect(T.ATM_TO_BUYBACK, BASE, **kw)["dE"] > 0) is expected


def test_every_tool_predicate_agrees_with_applying_it():
    """掃過所有工具與組合:有謂詞的,就得跟實際套用的結果一致。

    這是整個設計的保險絲 —— 新增工具時忘了同步謂詞,這裡會抓到。
    """
    cases = {
        "issue_preferred": [{"c": 0.9e9, "F": 1e9}, {"c": 1.1e9, "F": 1e9}],
        "buyback_preferred": [{"c": 0.73e9, "F": 1e9}, {"c": 1.2e9, "F": 1e9}],
        "carry": [{"c": 1e8}],
        "common_atm": [{"n": 1e6, "P": _params_at_mnav(BASE, 1.3)},
                       {"n": 1e6, "P": _params_at_mnav(BASE, 0.7)}],
        "common_buyback": [{"n": 1e6, "P": _params_at_mnav(BASE, 1.3)},
                           {"n": 1e6, "P": _params_at_mnav(BASE, 0.7)}],
        "convert_conversion": [{"F": 1e9, "n": 2e6}, {"F": 1e9, "n": 20e6}],
        # 可轉債發行與優先股發行同形:溢價發行(c > F)才加分,實務上罕見
        "convert_issue": [{"c": 0.9e9, "F": 1e9}, {"c": 1.1e9, "F": 1e9}],
        "atm_to_btc": [{"n": 1e6, "P": _params_at_mnav(BASE, 1.2)},
                       {"n": 1e6, "P": _params_at_mnav(BASE, 0.8)}],
        "sell_to_buyback": [{"x": 5_000.0, "F": 1e9},
                            {"x": 5_000.0, "F": 0.2e9}],
        "preferred_to_btc": [{"c": 0.9e9, "F": 1e9}, {"c": 1.1e9, "F": 1e9}],
        "atm_to_buyback": [{"n": 1e6, "P": _params_at_mnav(BASE, 0.78), "d": 0.27},
                           {"n": 1e6, "P": _params_at_mnav(BASE, 0.68), "d": 0.27}],
    }
    checked = 0
    for tool in T.TOOLS + T.COMBOS:
        if tool.accretive is None:
            # 宣告恆中性的,就必須真的恆中性
            neutral = {"buy_btc": {"c": 1e9}, "sell_btc": {"x": 1_000.0}}[tool.id]
            assert T.effect(tool, BASE, **neutral)["dE"] == pytest.approx(0, abs=1e-9)
            checked += 1
            continue
        for kw in cases[tool.id]:
            claimed = tool.accretive(BASE, kw)
            actual = T.effect(tool, BASE, **kw)["dE"] > 0
            assert claimed is actual, f"{tool.id} 的謂詞與實際不符:{kw}"
            checked += 1
    assert checked >= len(T.TOOLS) + len(T.COMBOS)


# --------------------------------------------------------------- 組合

def test_combo_equals_applying_its_parts_in_order():
    """組合沒有魔法:就是依序套用。這條守住 compose() 的語意。"""
    manual = T.BUYBACK_PREFERRED(
        T.SELL_BTC(BASE, x=5_000.0), c=5_000.0 * BASE.price, F=1e9)
    combo = T.SELL_TO_BUYBACK(BASE, x=5_000.0, F=1e9)
    assert combo == manual


def test_phantom_growth_has_opposite_signs():
    """發優先股買幣:B 上升而 E 下降。這兩行並排就是 phantom growth。"""
    e = T.effect(T.PREFERRED_TO_BTC, BASE, c=0.9e9, F=1e9)
    assert e["dB"] > 0 and e["dE"] < 0


def test_sell_to_buyback_gain_is_the_discount_only():
    """組合 B 的加分恰好等於折價本身,跟賣了多少幣無關。"""
    F = 1e9
    for x in (2_000.0, 5_000.0, 9_000.0):
        c = x * BASE.price
        gain = T.effect(T.SELL_TO_BUYBACK, BASE, x=x, F=F)["dE"]
        expected = (F - c) / (BASE.price * BASE.shares) * T.SATS
        assert gain == pytest.approx(expected, rel=1e-9)


def test_atm_to_buyback_nets_to_claims_down_shares_up():
    """兩步加總的淨效果:求償權 −F、股數 +n、持幣不動。"""
    n, P, d = 1e6, 150.0, 0.27
    after = T.ATM_TO_BUYBACK(BASE, n=n, P=P, d=d)
    assert after.held == BASE.held
    assert after.shares == pytest.approx(BASE.shares + n)
    assert after.claims == pytest.approx(BASE.claims - n * P / (1 - d))


def test_combos_are_closed_under_composition():
    """組合回傳的還是 Tool,所以可以再被組進另一個組合。"""
    twice = T.compose(
        id="buyback_twice", label="回購兩次", params=("c", "F"),
        steps=(T.Step(T.BUYBACK_PREFERRED, lambda s, k: {"c": k["c"], "F": k["F"]}),
               T.Step(T.BUYBACK_PREFERRED, lambda s, k: {"c": k["c"], "F": k["F"]})),
        latex_b=r"\Delta B = 0", latex_e=r"2 \times \Delta E")
    once = T.effect(T.BUYBACK_PREFERRED, BASE, c=0.73e9, F=1e9)["dE"]
    assert T.effect(twice, BASE, c=0.73e9, F=1e9)["dE"] == pytest.approx(
        2 * once, rel=1e-9)


# --------------------------------------------------------------- 資本效率

@pytest.mark.parametrize("d", [0.05, 0.10, 0.27, 0.40])
def test_buyback_efficiency_is_d_over_one_minus_d(d):
    """折價回購的資本報酬率就是 d/(1−d):折價 27% 換到 37% 的報酬。

    這是決策層真正要比較的數字 —— 同一塊錢拿去買幣的報酬是 0。
    """
    F = 1e9
    c = F * (1 - d)
    eff = T.efficiency(T.BUYBACK_PREFERRED, BASE, capital=c, c=c, F=F)
    assert eff == pytest.approx(d / (1 - d), rel=1e-9)


def test_buying_btc_has_zero_capital_efficiency():
    assert T.efficiency(T.BUY_BTC, BASE, capital=1e9, c=1e9) == pytest.approx(
        0.0, abs=1e-12)


def test_efficiency_rejects_zero_capital():
    with pytest.raises(ValueError):
        T.efficiency(T.BUY_BTC, BASE, capital=0.0, c=1e9)


# --------------------------------------------------------------- 介面健全性

def test_missing_parameter_is_caught_early():
    with pytest.raises(TypeError, match="common_atm"):
        T.COMMON_ATM(BASE, n=1e6)          # 少了 P


def test_every_tool_declares_both_rulers():
    """兩把尺都要有代數,不能只寫一邊 —— 兩欄並排才是重點。"""
    for tool in T.TOOLS + T.COMBOS:
        assert tool.latex_b.strip(), f"{tool.id} 缺 latex_b"
        assert tool.latex_e.strip(), f"{tool.id} 缺 latex_e"
        assert tool.params, f"{tool.id} 沒宣告參數"


def test_tools_do_not_mutate_the_input_state():
    """State 是 frozen,套用只產生新狀態 —— 歸因會反覆重放,不能有副作用。"""
    before = T.State(**vars(BASE))
    T.ATM_TO_BUYBACK(BASE, n=1e6, P=150.0, d=0.27)
    assert BASE == before


def test_price_is_untouched_by_every_tool():
    """工具只動結構,不動幣價。幣價是行情,不是決策 —— 這是四層拆解的前提。"""
    for tool, kw in ((T.BUY_BTC, {"c": 1e9}), (T.SELL_BTC, {"x": 1e3}),
                     (T.COMMON_ATM, {"n": 1e6, "P": 150.0}),
                     (T.ATM_TO_BUYBACK, {"n": 1e6, "P": 150.0, "d": 0.2})):
        assert tool(BASE, **kw).price == BASE.price


def test_effect_matches_closed_form_for_buyback():
    """把 latex_e 宣告的封閉式子真的算一次,跟 apply 的結果比對。"""
    c, F = 0.73e9, 1e9
    closed = (F - c) / (BASE.price * BASE.shares) * T.SATS
    assert T.effect(T.BUYBACK_PREFERRED, BASE, c=c, F=F)["dE"] == pytest.approx(
        closed, rel=1e-9)


def test_atm_closed_form_threshold_equals_predicate():
    """latex_e 說門檻是 P/p×1e8 > E,謂詞說是 m > 1。兩者必須等價。"""
    for m in (0.8, 0.99, 1.01, 1.5):
        P = _params_at_mnav(BASE, m)
        by_formula = P / BASE.price * T.SATS > T.cebe(BASE)
        by_predicate = T.COMMON_ATM.accretive(BASE, {"n": 1e6, "P": P})
        assert by_formula is by_predicate, f"m={m} 兩種寫法不一致"


def test_log_decomposition_of_a_sequence_telescopes():
    """把一串操作依序套用,各步 ΔlnE 相加 = 總 ΔlnE。

    這就是逐日鏈結在做的事,只是把「天」換成「操作」。
    """
    steps = [(T.COMMON_ATM, {"n": 2e6, "P": 150.0}),
             (T.BUYBACK_PREFERRED, {"c": 0.3e9, "F": 0.41e9}),
             (T.CARRY, {"c": 5e7}),
             (T.BUY_BTC, {"c": 2e8})]
    s, total = BASE, 0.0
    for tool, kw in steps:
        nxt = tool(s, **kw)
        total += math.log(T.cebe(nxt)) - math.log(T.cebe(s))
        s = nxt
    assert total == pytest.approx(
        math.log(T.cebe(s)) - math.log(T.cebe(BASE)), rel=1e-12)


# ------------------------------------------------- 四個位置:宣告 vs apply

# 箭頭分兩類,方向語意不同:
#
#   替換(同類之間):起點減少、終點增加,規模不變
#       U→H 買幣、H→U 賣幣、DL→S 可轉債轉股
#   伸縮(跨類):從來源出發 = 募資(兩端都增);指向來源 = 償還(兩端都減)
#       DL→U 發行、S→U ATM、U→DL 回購、U→S 庫藏、U→OUT 股息
#
# 曾經想用一條規則涵蓋全部,結果為了讓規則成立而把「可轉債轉股」寫成
# S→DL —— 那是「發新股募資再去回購可轉債」,是兩個操作的組合,不是轉股。
# **為了救規則去改模型是本末倒置**,規則錯了就改規則。
ASSETS = set(T.ASSET_PLACES)
SOURCES = set(T.SOURCE_PLACES)


def _dir(frm: str, to: str) -> dict:
    """每個位置在這條箭頭下應該變大還是變小。+1 增、−1 減。"""
    same = (frm in ASSETS and to in ASSETS) or (frm in SOURCES and to in SOURCES)
    if same:                                   # 替換
        return {frm: -1, to: +1}
    if frm in SOURCES:                         # 募資
        return {frm: +1, to: +1}
    return {frm: -1, **({to: -1} if to != "OUT" else {})}   # 償還 / 流出


def _probe():
    return T.State(held=800_000.0, claims=15e9, shares=400e6, price=90_000.0)


@pytest.mark.parametrize("tool", T.TOOLS, ids=lambda t: t.id)
def test_every_tool_moves_exactly_two_places(tool):
    """「位置只有四個,所以動作可窮舉」這個主張的前提:
    每一把工具恰好連接兩個位置,而且兩端不同。"""
    a, b = tool.moves
    assert a and b and a != b, tool.id
    assert a in T.PLACES and b in T.PLACES
    assert a != "OUT", "OUT 只能當終點 —— 錢不會從系統外面流進來"


def test_only_carry_leaves_the_system():
    """股息與債息是唯一真正離開系統的錢。其餘動作都只是換位置。"""
    out = [t.id for t in T.TOOLS if "OUT" in t.moves]
    assert out == ["carry"]


@pytest.mark.parametrize("tool", T.TOOLS, ids=lambda t: t.id)
def test_the_declared_places_match_what_apply_does(tool):
    """宣告的位置必須與 apply 真的改了哪些欄位一致。

    這是 toolbox 一貫的紀律:代數、謂詞、位置都是**宣告**,
    而 apply 是唯一的真實語意 —— 所以宣告要能被 apply 打臉。
    """
    s = _probe()
    kw = {p: {"c": 1e9, "F": 1.2e9, "n": 5e6, "P": 200.0, "x": 1_000.0}[p]
          for p in tool.params}
    after = tool(s, **kw)
    frm, to = tool.moves

    want = _dir(frm, to)

    for place, field, sign in (("H", "held", +1), ("S", "shares", +1)):
        d = getattr(after, field) - getattr(s, field)
        if place in want:
            assert d * want[place] * sign > 0, f"{tool.id} {place} 方向不符"
        else:
            assert d == 0, f"{tool.id} 不該動到 {place}"

    # 求償權 C = DL − U,兩種位置都動到它,方向相反
    expect = want.get("DL", 0) - want.get("U", 0)
    d = after.claims - s.claims
    if expect:
        assert d * expect > 0, f"{tool.id} 宣告 C 應{'上升' if expect>0 else '下降'},實際 {d:+,.0f}"


def test_only_three_arrows_leave_the_balance_sheet_unchanged():
    """替換(同類之間)不改變規模,伸縮(跨類)才會。
    八條箭頭裡只有三條是替換 —— 這個二分本身就是內容。"""
    sub = [t.id for t in T.TOOLS
           if (t.moves[0] in ASSETS) == (t.moves[1] in ASSETS)
           and t.moves[1] != "OUT"]
    assert sorted(sub) == ["buy_btc", "convert_conversion", "sell_btc"]


def test_the_reserve_is_the_hub():
    """U 是樞紐 —— 除了可轉債轉股(求償權直接變股權),每把工具都經過它。

    這就是為什麼「把募到的錢放進儲備」不需要另外配對:
    它是每一個融資動作本身的另一半。
    """
    bypass = [t.id for t in T.TOOLS if "U" not in t.moves]
    assert bypass == ["convert_conversion"]


def test_the_reserve_has_exactly_one_exit():
    """USD Reserve 的用途由董事會政策界定,只有一個出口:付股息與債息。

    2026-06-29 的 8-K:"the Company may use the USD Reserve to pay preferred
    stock dividends and interest expenses as they become due and may
    subsequently replenish the USD Reserve through sales of BTC"。

    買幣與回購都**不動用 Reserve** —— 逐週 8-K 寫的是
    "bitcoin purchases were made using proceeds from the sale of shares
    under the ATM"、"net proceeds from MSTR Stock sales were used to fund
    repurchases of STRC Stock"。

    代數裡的 U 是**全部**美元流動性(Reserve + 過路現金),不區分這兩塊,
    因為 C 問的是「有多少美元可以抵掉求償權」。這條測試釘住的是:
    唯一真正離開系統的動作就是 carry,而那正好是 Reserve 的唯一用途。
    """
    leaves = [t for t in T.TOOLS if t.moves[1] == "OUT"]
    assert [t.id for t in leaves] == ["carry"]
    # carry 從 U 出發 —— Reserve 是它的資金來源
    assert leaves[0].moves[0] == "U"


# --------------------------------------------------------- 組合的路徑

def test_every_combo_path_is_connected():
    """組合的 path 由各步驟的 moves 串出來,而且必須首尾相接 ——
    前一步的終點就是後一步的起點,否則那兩步根本不是同一筆錢。"""
    for c in T.COMBOS:
        assert len(c.path) >= 3, c.id
        for a, b in zip(c.path, c.path[1:]):
            assert a != b, c.id


def test_every_combo_passes_through_the_cash_leg():
    """**所有組合的中間那一點都是 U。**

    這不是巧合:錢要先變成現金才能往下一步走。公司當週募資、當週部署,
    所以那筆過路現金在週頻揭露上幾乎看不見 —— 它被藏在操作裡面,
    但它在結構上一定存在。
    """
    for c in T.COMBOS:
        assert c.path[1:-1] == ("U",), f"{c.id} 的路徑是 {c.path}"


def test_a_combo_that_does_not_relay_has_no_path():
    """接不起來的兩步仍然組得成一把工具(型別封閉性不該被破壞),
    但它不是一條中繼,所以沒有路徑 —— 用 path 是不是空的來分辨。"""
    bad = T.compose(
        id="bad", label="接不起來", params=("c",),
        steps=(T.Step(T.BUY_BTC, lambda s, k: {"c": k["c"]}),            # U→H
               T.Step(T.COMMON_ATM, lambda s, k: {"n": 1.0, "P": 1.0})),  # S→U
        latex_b="", latex_e="")
    assert bad.path == ()
    assert callable(bad.apply)


def test_the_new_combo_is_the_one_the_filings_describe_every_week():
    """ATM 增發 → 買幣曾經不在組合清單裡 —— 它被藏在 chronicle 的
    common_atm 當成單一工具,所以沒人發現 combos 少了一條。
    而逐週 8-K 寫的就是它。"""
    atm_btc = next(c for c in T.COMBOS if c.id == "atm_to_btc")
    assert atm_btc.path == ("S", "U", "H")
    # 買幣那一步對 E 恆中性,所以判準就是增發那一步的判準
    s = T.State(held=800_000.0, claims=15e9, shares=400e6, price=90_000.0)
    hi = _params_at_mnav(s, 1.2)
    lo = _params_at_mnav(s, 0.8)
    assert T.effect(atm_btc, s, n=1e6, P=hi)["dE"] > 0
    assert T.effect(atm_btc, s, n=1e6, P=lo)["dE"] < 0
    # 而且持幣一定增加 —— 單純增發不會
    assert T.effect(atm_btc, s, n=1e6, P=hi)["dB"] != \
        T.effect(T.COMMON_ATM, s, n=1e6, P=hi)["dB"]


# ------------------------------------------- 文件宣稱的數量不能與程式漂開

_CN = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六",
       7: "七", 8: "八", 9: "九", 10: "十"}


def test_the_docs_do_not_claim_a_stale_tool_count():
    """reference 與 CLAUDE.md 宣稱的工具數,必須與 toolbox 實際的數量一致。

    這條是補一次實害:合併兩份工具清單之後,README 與 CLAUDE.md 還寫著
    「七把工具 + 三個組合」,02-operations 的組合章節還列著三個(而且其中
    一個「賣幣→增加美元儲備」根本是單一工具)。文件與程式各自漂了一段時間,
    沒有任何東西會紅。

    守門的方式與黃金錨點相同:**把一個容易悄悄失守的規則變成會紅的測試。**
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parent.parent
    want_tools = f"{_CN[len(T.TOOLS)]}把"
    want_combos = f"{_CN[len(T.COMBOS)]}個組合"

    bad = []
    for f in list((root / "reference").glob("*.md")) + [root / "CLAUDE.md"]:
        text = f.read_text(encoding="utf-8")
        # 排除「一」—— 中文裡「每一把工具」「加一把」是量詞不是計數
        # 引號裡的是**引用**(例如記錄「文件曾經寫七把」),不是宣稱。
        # 掃描器要分得出這兩者,否則就沒辦法把走過的彎路寫進文件。
        quoted = lambda i: i > 0 and text[i - 1] == "\u300c"
        for m in re.finditer(r"([二三四五六七八九十])把(?:原子)?工具", text):
            if m.group(1) != _CN[len(T.TOOLS)] and not quoted(m.start()):
                bad.append(f"{f.name}: 「{m.group(0)}」應為 {want_tools}")
        for m in re.finditer(r"([二三四五六七八九十])個組合", text):
            if m.group(1) != _CN[len(T.COMBOS)] and not quoted(m.start()):
                bad.append(f"{f.name}: 「{m.group(0)}」應為 {want_combos}")
    assert bad == [], "\n".join(bad)


def test_tool_notes_do_not_leak_code_identifiers():
    """工具說明是**給讀者看的**,不該出現 Python 的識別字。

    這一條是補一次實害:講義頁上出現過「見 CONVERT_CONVERSION」——
    程式註解的寫法直接流到了使用者眼前。toolbox 的 note 欄位有雙重身分
    (程式註解 + 網頁文案),所以要有東西盯著它別寫成前者。
    """
    import re

    bad = []
    for t in list(T.TOOLS) + list(T.COMBOS):
        ids = re.findall(r"\b[A-Z][A-Z_]{3,}\b", t.note)
        # 允許的全大寫詞:金融術語與券種代碼,不是識別字
        ids = [i for i in ids if i not in {"ATM", "KPI", "USD", "BTC", "MSTR",
                                           "STRC", "STRF", "STRK", "STRD", "STRE"}]
        if ids:
            bad.append(f"{t.id}: {ids}")
    assert bad == [], "\n".join(bad)
