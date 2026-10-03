"""L3 資本操作層的測試。

這一層是第一個**不可能被證明**的層,所以測試的重點不是「配對有沒有找到」,
而是幾條不可妥協的性質:

  1. 不得無中生有 —— 文件說了也不能生出不存在的事件
  2. 不得吃掉或重複計算任何現金流 —— 每個動作恰好屬於一個操作
  3. 沒有證據就不配對 —— 金額像不像不是依據
"""
from __future__ import annotations

import os

import pytest

from mstr_cebe import archive as A
from mstr_cebe import events as E
from mstr_cebe import operations as O


@pytest.fixture()
def conn(tmp_path):
    c = O.connect(str(tmp_path / "a.sqlite"))
    yield c
    c.close()


def _doc(c, content=b"<html/>", **kw):
    kw.setdefault("source", "sec_8k")
    kw.setdefault("url", "https://www.sec.gov/x")
    kw.setdefault("media_type", "text/html")
    kw.setdefault("filed_at", "2026-08-10")
    return A.store(c, content=content, **kw)


def _sale(doc, usd, week="2026-08-09", **attrs):
    return E.Event(kind="btc_sale", instrument="BTC", effective_at=week,
                   period_start="2026-08-03", period_end=week,
                   qty=1_690.0, unit="BTC", usd=usd, doc_id=doc,
                   locator=f"activity/{week}", attrs=attrs)


def _repurchase(doc, usd, week="2026-08-09", sec="STRC"):
    return E.Event(kind="preferred_repurchase", instrument=sec,
                   effective_at=week, period_start="2026-08-03",
                   period_end=week, qty=1_152_020.0, unit="shares", usd=usd,
                   doc_id=doc, locator=f"repurchase/{week}/00/{sec}")


# --------------------------------------------------------- 用途的分類

@pytest.mark.parametrize("text,expected", [
    ("fund repurchases of STRC Stock under the Digital Credit Securities "
     "Repurchase Program", "preferred_repurchase"),
    ("fund dividends on Strategy's preferred stock", "carry"),
    ("fund payment of distributions on preferred stock", "carry"),
    ("replenish the portion of the USD reserve used for this purpose", "reserve"),
])
def test_stated_purposes_are_classified(text, expected):
    assert E.classify_purpose(text) == expected


def test_an_unrecognised_purpose_is_not_guessed():
    """認不出來就回 None。寧可不配,也不要猜一個看起來合理的。"""
    assert E.classify_purpose("for general corporate purposes") is None
    assert E.classify_purpose("") is None


def test_itemised_allocation_is_parsed_with_amounts():
    """文件逐筆寫出金額時,要解析成結構而不是留一段自由文字給上層去猜。"""
    html = ("(1) $52.4 million in proceeds from the bitcoin sales were used to "
            "fund dividends on Strategy's preferred stock and $52.3 million in "
            "proceeds from the bitcoin sales were used to fund repurchases of "
            "STRC Stock under the Digital Credit Securities Repurchase Program.")
    alloc = E.parse_sale_allocation(html)
    assert [a["usd"] for a in alloc] == [52.4e6, 52.3e6]
    assert [a["kind"] for a in alloc] == ["carry", "preferred_repurchase"]


# --------------------------------------------------------- 不得無中生有

def test_no_pairing_without_a_stated_purpose(conn):
    """金額完全一致也不配 —— 因為現金是可替代的,像不像不是證據。"""
    doc = _doc(conn)
    E.insert(conn, [_sale(doc, 108.6e6), _repurchase(doc, -108.6e6)])
    merged, partial = O.match_sell_to_buyback(conn)
    assert merged == [] and partial == {}


def test_no_pairing_when_the_stated_target_does_not_exist(conn):
    """文件說錢拿去回購,但那一週根本沒有回購事件 —— 不自己生一個出來。"""
    doc = _doc(conn)
    E.insert(conn, [_sale(doc, 108.6e6,
                          sale_use="fund repurchases of STRC Stock")])
    merged, partial = O.match_sell_to_buyback(conn)
    assert merged == [] and partial == {}
    assert len(O.build(conn)) == 1          # 賣幣仍然是一個單一操作


def test_a_sale_stated_for_dividends_is_not_paired_to_a_repurchase(conn):
    """用途分類要真的被用上:說是付股息就不能配到回購。"""
    doc = _doc(conn)
    E.insert(conn, [
        _sale(doc, 80.8e6, sale_use="fund payment of distributions on "
                                    "preferred stock"),
        _repurchase(doc, -80.8e6),
    ])
    merged, _ = O.match_sell_to_buyback(conn)
    assert merged == []


# --------------------------------------------------------- 全額 vs 一部分

def test_full_coverage_merges_both_sides(conn):
    doc = _doc(conn)
    E.insert(conn, [
        _sale(doc, 108.6e6, sale_use="fund repurchases of STRC Stock"),
        _repurchase(doc, -108.6e6),
    ])
    merged, partial = O.match_sell_to_buyback(conn)
    assert len(merged) == 1 and not partial
    op = merged[0]
    assert op.combo_id == "sell_to_buyback"
    assert op.confidence == O.HIGH
    assert {r for _, r, _ in op.members} == {"source", "use"}
    # 合併之後兩邊都不再單獨成操作
    assert len(O.build(conn)) == 1


def test_partial_coverage_keeps_both_sides_separate(conn):
    """賣幣只支應了回購的一部分,其餘來自別處。

    硬合併會把另一個資金來源吃掉,所以兩邊維持獨立 ——
    但文件說的關係要留著,不能因為沒合併就消失。
    """
    doc = _doc(conn)
    E.insert(conn, [
        _sale(doc, 104.8e6, sale_allocation=[
            {"usd": 52.3e6, "purpose": "fund repurchases of STRC Stock",
             "kind": "preferred_repurchase"}]),
        _repurchase(doc, -81.2e6),
    ])
    merged, partial = O.match_sell_to_buyback(conn)
    assert merged == []
    assert len(partial) == 1
    ev = next(iter(partial.values()))
    assert ev["partial"] is True
    assert ev["covered_share_pct"] == pytest.approx(64.4, abs=0.1)

    ops = O.build(conn)
    assert len(ops) == 2                       # 賣幣與回購各自一個
    sale_op = next(o for o in ops if o.combo_id == "sell_btc")
    assert sale_op.rule == "partly_funded"
    assert sale_op.evidence["quoted"].startswith("fund repurchases")


# --------------------------------------------------------- 記帳

def test_every_action_belongs_to_exactly_one_operation(conn):
    doc = _doc(conn)
    E.insert(conn, [
        _sale(doc, 108.6e6, sale_use="fund repurchases of STRC Stock"),
        _repurchase(doc, -108.6e6),
        E.Event(kind="btc_purchase", instrument="BTC",
                effective_at="2026-08-09", period_end="2026-08-09",
                qty=100.0, unit="BTC", usd=-8.6e6, doc_id=doc,
                locator="activity/2026-08-09b"),
    ])
    O.rebuild(conn)
    rec = O.reconcile(conn)
    assert rec["ok"], rec
    assert rec["missing"] == [] and rec["doubled"] == [] and rec["invented"] == []


def test_cash_flow_is_neither_eaten_nor_double_counted(conn):
    doc = _doc(conn)
    E.insert(conn, [
        _sale(doc, 104.8e6, sale_allocation=[
            {"usd": 52.3e6, "purpose": "repurchases", "kind": "preferred_repurchase"}]),
        _repurchase(doc, -81.2e6),
    ])
    O.rebuild(conn)
    rec = O.reconcile(conn)
    assert rec["usd_gap"] == pytest.approx(0.0, abs=1e-6)
    assert rec["action_usd"] == pytest.approx(104.8e6 - 81.2e6)


def test_observations_never_become_operations(conn):
    """觀測是狀態不是動作,不該出現在操作層。"""
    doc = _doc(conn)
    E.insert(conn, [
        E.Event(kind="holdings_observation", instrument="BTC",
                effective_at="2026-08-09", qty=846_000.0, unit="BTC",
                doc_id=doc, locator="holdings/2026-08-09"),
        E.Event(kind="reserve_observation", instrument="USD",
                effective_at="2026-08-09", qty=6.09e9, unit="USD",
                doc_id=doc, locator="reserve/2026-08-09"),
    ])
    assert O.build(conn) == []


def test_rebuild_is_idempotent(conn):
    doc = _doc(conn)
    E.insert(conn, [_sale(doc, 108.6e6, sale_use="fund repurchases of STRC"),
                    _repurchase(doc, -108.6e6)])
    assert O.rebuild(conn) == O.rebuild(conn)
    assert O.reconcile(conn)["ok"]


# --------------------------------------------------------- 真實資料

def _real():
    if not os.path.exists(A.DEFAULT_PATH):
        pytest.skip("檔案庫還沒建立")
    conn = O.connect()
    if not conn.execute("SELECT 1 FROM events LIMIT 1").fetchone():
        conn.close()
        pytest.skip("還沒有事件,先跑 python3 -m mstr_cebe.events rebuild")
    return conn


def test_real_data_reconciles_exactly():
    """第 5 步的驗收條件:對帳等式成立,沒有流量遺漏。"""
    conn = _real()
    try:
        O.rebuild(conn)
        rec = O.reconcile(conn)
    finally:
        conn.close()
    assert rec["ok"], rec
    assert rec["covered"] == rec["actions"]
    assert abs(rec["usd_gap"]) < 1.0


def test_real_data_finds_the_stated_pairing():
    """2026-08-09 的 8-K 直接寫了賣幣所得用於回購 STRC,金額也對得上。"""
    conn = _real()
    try:
        merged, partial = O.match_sell_to_buyback(conn)
    finally:
        conn.close()
    assert [op.window_hi for op in merged] == ["2026-08-09"]
    op = merged[0]
    assert op.confidence == O.HIGH
    assert op.evidence["amount_gap_pct"] < 0.05
    assert op.evidence["same_document"] is True
    assert "repurchases of STRC" in op.evidence["quoted"]


def test_real_data_marks_the_partly_funded_week():
    """2026-08-02 的文件逐筆寫出 $52.3M 用於回購,但那週回購總額 $81.2M。"""
    conn = _real()
    try:
        _, partial = O.match_sell_to_buyback(conn)
    finally:
        conn.close()
    assert len(partial) == 1
    ev = next(iter(partial.values()))
    assert ev["basis"] == "itemised"
    assert ev["partial"] is True
    assert 60 < ev["covered_share_pct"] < 70


def test_confidence_never_exceeds_what_the_evidence_supports():
    """這一層不可能被證明,所以沒有任何操作可以宣稱 1.0 以上的信心;
    而且有配對證據的那些,信心一定低於「就是這個動作本身」的單一操作。"""
    conn = _real()
    try:
        ops = O.build(conn)
    finally:
        conn.close()
    for op in ops:
        assert 0 < op.confidence <= 1.0
        if op.rule != "unpaired":
            assert op.confidence <= O.HIGH


# ------------------------------------------- 操作 → 工具的對應與效果

def test_the_param_translation_is_the_only_one():
    """L3 記 (qty, usd),toolbox 的參數是 (c, F, n, P, x) ——
    兩者之間的翻譯只能寫在一個地方,否則「網站顯示的效果」與
    「測試驗的效果」會各自漂開。那正是 CLAUDE.md 第一條規則在防的事。
    """
    conn = _real()
    try:
        ops = O.build(conn)
        missing = [o.combo_id for o in ops if O.tool_params(o, conn) is None]
    finally:
        conn.close()
    assert missing == [], f"這些操作翻不成工具參數:{sorted(set(missing))}"


def _state_at(day: str):
    import json
    import os
    from mstr_cebe import toolbox as T

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "app", "data", "daily.json"),
              encoding="utf-8") as f:
        d = json.load(f)
    i = d["date"].index(day) if day in d["date"] else len(d["date"]) - 1
    return T.State(held=d["held"][i],
                   claims=(d["debt"][i] + d["pref_total"][i]
                           - d["cash"][i]) * 1e9,
                   shares=d["shares"][i] * 1e6, price=d["btc"][i])


def test_every_operation_effect_matches_its_tools_structural_claim():
    """每一筆操作的 ΔB / ΔE 必須符合那把工具在代數上的宣告。

    這是把講義與儀表板綁在一起:講義說「買幣對實得每股恆中性」,
    那麼儀表板上**每一筆**買幣的 ΔE 都必須是 0。
    說一套做一套的話,兩邊就不是同一個模型了。
    """
    conn = _real()
    try:
        ops = O.build(conn)
        bad = []
        for op in ops:
            eff = O.effect_of(op, _state_at(op.window_hi), conn)
            assert eff is not None, op.combo_id
            if op.combo_id == "buy_btc":
                # 買幣:B 上升、E 恰好中性
                if not (eff["dB"] > 0 and abs(eff["dE"]) < 1e-6):
                    bad.append((op.window_hi, "buy_btc", eff))
            elif op.combo_id == "buyback_preferred":
                # 折價回購:B 完全看不到(式子裡沒有求償權)、E 上升
                if not (abs(eff["dB"]) < 1e-9 and eff["dE"] > 0):
                    bad.append((op.window_hi, "buyback", eff))
            elif op.combo_id == "sell_btc":
                if not (eff["dB"] < 0 and abs(eff["dE"]) < 1e-6):
                    bad.append((op.window_hi, "sell_btc", eff))
            elif op.combo_id == "common_atm":
                # 增發必定稀釋帳面每股;對實得的方向由 m 決定,不在這裡斷言
                if not eff["dB"] < 0:
                    bad.append((op.window_hi, "common_atm", eff))
    finally:
        conn.close()
    assert bad == [], f"與代數宣告不符:{bad[:3]}"


def test_a_common_stock_buyback_is_not_priced_at_par():
    """普通股沒有面額。真的出現普通股庫藏時,`qty × $100` 的對應不成立 ——
    要擋掉而不是算出一個看起來合理的數字。

    目前公司的普通股回購授權掛著沒動用(見 chronicle.UNUSED_BY_DESIGN),
    所以這條現在是預防性的 —— 哪天開始動用,它會逼人回來處理。
    """
    from mstr_cebe import toolbox as T

    fake = O.Operation(
        combo_id="buyback_preferred", window_lo="2026-09-01",
        window_hi="2026-09-07", rule="unpaired", confidence=1.0,
        params={"qty": 1e6, "usd": -3e8}, members=())
    # 沒有 conn 就查不到標的,維持原本的優先股對應
    tool, kw = O.tool_params(fake)
    assert tool is T.BUYBACK_PREFERRED
    assert kw["F"] == 1e6 * O.PAR_PER_SHARE
