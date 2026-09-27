"""L4 階段偵測的測試。

這一步的結論是「偵測器還不能取代人工分期」,所以測試的重點是
**前提檢查有沒有誠實反映缺口** —— 解釋率是這個判斷的依據。
"""
from __future__ import annotations

import json
import os

import pytest

from mstr_cebe import archive as A
from mstr_cebe import events as E
from mstr_cebe import operations as O
from mstr_cebe import phases as P

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def conn(tmp_path):
    c = O.connect(str(tmp_path / "a.sqlite"))
    yield c
    c.close()


def _doc(c, **kw):
    kw.setdefault("source", "sec_8k")
    kw.setdefault("url", "https://www.sec.gov/x")
    kw.setdefault("media_type", "text/html")
    kw.setdefault("filed_at", "2026-08-10")
    kw.setdefault("content", b"<html/>")
    return A.store(c, **kw)


def _action(doc, kind, instrument, week, qty, usd, locator=None):
    return E.Event(kind=kind, instrument=instrument, effective_at=week,
                   period_start=week, period_end=week, qty=qty, usd=usd,
                   unit="BTC" if instrument == "BTC" else "shares",
                   doc_id=doc, locator=locator or f"{kind}/{week}/{instrument}")


def test_every_tool_has_a_structural_role():
    """新增工具卻忘了宣告它在結構上做什麼,偵測器就會把它算成自己一類。"""
    from mstr_cebe import toolbox as T
    for tool in T.TOOLS + T.COMBOS:
        if tool.id in ("buy_btc", "sell_btc", "issue_preferred", "common_atm",
                       "buyback_preferred", "sell_to_buyback",
                       "convert_conversion", "common_buyback"):
            assert tool.id in P.STRUCTURAL_ROLE, tool.id


def test_mix_shares_sum_to_one(conn):
    doc = _doc(conn)
    E.insert(conn, [
        _action(doc, "btc_purchase", "BTC", "2026-08-09", 100.0, -8.6e6),
        _action(doc, "atm_issue", "MSTR", "2026-08-09", 1e6, 12.0e6),
    ])
    for row in P.weekly_mix(conn).values():
        assert sum(row.values()) == pytest.approx(1.0)


def test_mix_groups_by_structural_role_not_by_tool(conn):
    """發優先股與發可轉債對結構是同一件事,偵測器該看角色而非工具。"""
    doc = _doc(conn)
    E.insert(conn, [
        _action(doc, "btc_purchase", "BTC", "2026-08-09", 100.0, -8.6e6),
    ])
    assert list(P.weekly_mix(conn)["2026-08-09"]) == ["accumulate"]
    assert "buy_btc" in P.weekly_mix(conn, by="tool")["2026-08-09"]


def test_a_one_week_blip_is_not_a_boundary(conn):
    """某一週剛好買了一大筆幣,不代表策略變了。"""
    doc = _doc(conn)
    evs = []
    for i, w in enumerate(["2026-01-05", "2026-01-12", "2026-01-19",
                           "2026-01-26", "2026-02-02", "2026-02-09"]):
        # 只有第 4 週主導角色不同
        if i == 3:
            evs.append(_action(doc, "btc_purchase", "BTC", w, 100.0, -9e9))
        else:
            evs.append(_action(doc, "atm_issue", "MSTR", w, 1e6, 1e9))
    E.insert(conn, evs)
    assert P.detect(conn, persist=3) == []


def test_a_sustained_shift_is_a_boundary(conn):
    doc = _doc(conn)
    evs = []
    for w in ["2026-01-05", "2026-01-12", "2026-01-19"]:
        evs.append(_action(doc, "atm_issue", "MSTR", w, 1e6, 1e9))
    for w in ["2026-01-26", "2026-02-02", "2026-02-09"]:
        evs.append(_action(doc, "preferred_repurchase", "STRC", w, 1e6, -1e9))
    E.insert(conn, evs)
    (b,) = P.detect(conn, persist=3)
    assert (b.week, b.before, b.after) == ("2026-01-26", "dilute", "delever")


def test_claims_delta_counts_the_par_of_a_preferred_issue(conn):
    """發優先股有兩個結構效果:拿到現金、掛上清算優先權。

    只算現金那一邊,解釋率會算出 290% 這種數字 —— 這條測試就是為了
    擋住那個錯誤再發生。
    """
    doc = _doc(conn)
    E.insert(conn, [_action(doc, "atm_issue", "STRC", "2026-08-09",
                            1e6, 90e6)])          # 100 萬股、募得 $90M
    (op,) = O.build(conn)
    # 面額 $100M 掛上、現金 $90M 抵減 ⇒ 求償權淨增 $10M
    assert P.claims_delta(op) == pytest.approx(10e6)


def test_claims_delta_of_a_cash_purchase_is_the_cash(conn):
    doc = _doc(conn)
    E.insert(conn, [_action(doc, "btc_purchase", "BTC", "2026-08-09",
                            100.0, -8.6e6)])
    (op,) = O.build(conn)
    assert P.claims_delta(op) == pytest.approx(8.6e6)


# --------------------------------------------------------------- 真實資料

def _real():
    if not os.path.exists(A.DEFAULT_PATH):
        pytest.skip("檔案庫還沒建立")
    conn = O.connect()
    if not conn.execute("SELECT 1 FROM events LIMIT 1").fetchone():
        conn.close()
        pytest.skip("還沒有事件")
    O.rebuild(conn)
    return conn


def _daily():
    with open(os.path.join(ROOT, "app", "data", "daily.json"),
              encoding="utf-8") as f:
        return json.load(f)


def _eras():
    with open(os.path.join(ROOT, "app", "data", "chronicle.json"),
              encoding="utf-8") as f:
        return json.load(f)


def test_the_latest_era_is_fully_explained():
    """折價回收期間的揭露是完整的,所以解釋率該接近 100% ——
    這證明方法沒問題,問題在更早的資料。"""
    conn = _real()
    try:
        s = P.explained_share(conn, _daily(), "2026-06-29", "2026-09-22")
    finally:
        conn.close()
    assert 0.95 < s["share"] < 1.05, s


def test_the_early_eras_are_flagged_as_unexplained():
    """可轉債時代的結構在動,但操作層看不到 —— 前提檢查必須顯示這件事,
    而不是讓下游拿著一個看起來合理的分期去下結論。"""
    conn = _real()
    try:
        early = P.explained_share(conn, _daily(), "2024-07-01", "2025-01-29")
        stack = P.explained_share(conn, _daily(), "2025-01-30", "2026-05-29")
    finally:
        conn.close()
    assert early["share"] < 0.5          # 大部分解釋不了
    assert abs(early["unexplained_usd"]) > 1e9

    # 「優先股堆疊」是反向偏離:買幣(用途)記了,支應它的普通股 ATM
    # 要到 2025-09 才有逐週揭露(來源沒記),所以可解釋 > 實際。
    #
    # 這個數字曾經是 290%,其中一大半不是缺口而是重複計算 ——
    # 季末那份 8-K 的季合計列被當成週紀錄,2025 年多算了 192,561 顆買幣。
    # 修掉之後是 136%,剩下的才是真正的揭露缺口。
    assert 1.2 < stack["share"] < 1.5


def test_detector_misses_the_boundary_it_has_no_data_for():
    """2025-01-30 那個邊界由可轉債與優先股 IPO 定義,兩者都不在週 8-K 裡。

    這條測試記錄的是**已知限制**,不是期望行為 —— 哪天補了資料而它開始
    對得上,這裡會紅,那是好消息,順手把測試改掉即可。
    """
    conn = _real()
    try:
        bounds = P.detect(conn)
    finally:
        conn.close()
    (first,) = [c for c in P.compare(bounds, ["2025-01-30"])]
    assert not first["matched"], "補到資料了?那就把這條測試更新掉"


def test_sources_and_uses_close_once_coarse_grains_fill_the_gaps():
    """接上季與年的補洞之後,每一段的「錢從哪來、到哪去」要對得起來。

    這是與 explained_share() 互補的一條檢查:那一支走 L3 的操作(只有
    週粒度),所以 8-K 還沒開始揭露的早期必然低估;這一支走粒度解析後的
    現金流,四段都該收斂。收斂本身就是「三種粒度沒有互相重複或遺漏」的
    證據 —— 年報、季報、週報是三次獨立申報。
    """
    conn = _real()
    daily = _daily()
    eras = _eras()
    try:
        checked = 0
        for e in eras:
            hi = e["end"] or daily["date"][-1]
            u = P.sources_and_uses(conn, daily, e["start"], hi)
            assert u["uses_usd"] > 0
            if not u["resolvable"]:
                # 「壓力測試」只有 26 天,而那段最細的來源是季頻 ——
                # 對帳結果會由攤分假設決定而不是由資料決定。標出來,不假裝有結論。
                assert u["prorated_share"] >= 0.3
                continue
            slack = abs(u["unexplained_usd"]) / max(u["uses_usd"], u["sources_usd"])
            assert slack < 0.05, (
                f"{e['title']} 未解釋 ${u['unexplained_usd']/1e9:.2f}B "
                f"({slack*100:.1f}%)")
            checked += 1
        assert checked >= 3
    finally:
        conn.close()


def test_the_convertible_era_is_no_longer_a_blind_spot():
    """可轉債時代原本在操作層幾乎是空白(解釋率 29%)——
    季頻資料一接上,它的資金流就完整了。這條測試釘住那個改善。"""
    conn = _real()
    try:
        u = P.sources_and_uses(conn, _daily(), "2024-07-01", "2025-01-29")
    finally:
        conn.close()
    assert u["buy_usd"] > 15e9           # 週粒度只看得到 $1.1B
    assert u["common_atm_usd"] > 10e9    # 普通股 ATM 要到 2025-09 才有週揭露
    assert u["convert_net_usd"] > 1e9    # 可轉債在週 8-K 裡完全不存在
    # 這一段的末端切在 2025Q1 中間(29/90 天),那一季只能按天數攤 ——
    # 而實際的買幣在那一季是前重後輕,所以 ±5% 是攤分本身的誤差,不是缺口。
    assert u["prorated_share"] > 0.2
    assert abs(u["unexplained_usd"]) / u["uses_usd"] < 0.05
