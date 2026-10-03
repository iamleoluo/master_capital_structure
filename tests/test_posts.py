"""觀點系統的測試。

這一層是**詮釋**,所以它的紀律與前兩層不同:公式與數字由測試守著,
觀點不可能被驗證。能驗的是**形式**:
  * 日期與作者在不在(沒有這兩個,就不是一則觀點,是一段無主的文字)
  * 主張只能出現在資本結構那一類(那是兩種文體唯一的結構差異)
  * pin 的 key 解析得開 —— 解不開就沒有「寫的時候 vs 今天」的對照
"""
from __future__ import annotations

import datetime as dt
import json
import os

import pytest

from mstr_cebe import posts as P

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _data():
    """pin 解析器要用到的那幾份。**少載一份就等於那一類 pin 全部解不開** ——
    `program:` 的三個 pin 曾經因為這裡沒載 meta 而全軍覆沒。"""
    out = {}
    for k in ("daily", "chronicle", "meta"):
        with open(os.path.join(ROOT, "app", "data", f"{k}.json"),
                  encoding="utf-8") as f:
            out[k] = json.load(f)
    return out


@pytest.fixture(scope="module")
def all_posts():
    return P.load_all(_data())


def test_there_are_posts(all_posts):
    assert all_posts, "posts/ 是空的 —— 這一層就沒有意義了"


def test_every_post_has_a_date_and_an_author(all_posts):
    """**凍結的東西要標日期。** 沒有日期的觀點會被誤讀成現況,
    而那正是先前四段 Era 敘述出的問題。"""
    for p in all_posts:
        dt.date.fromisoformat(p.date)
        assert p.author.strip(), f"{p.slug} 沒有作者"
        assert p.title.strip() and p.html.strip()


def test_only_structure_posts_carry_a_claim(all_posts):
    """兩種文體唯一的結構差異:**資本結構帶主張,大事記沒有** ——
    因為主張可以被後續的資料檢驗,事件不行。"""
    for p in all_posts:
        if p.kind == "chronicle":
            assert not p.claim, f"{p.slug} 是大事記,不該有主張"


def test_every_pin_resolves(all_posts):
    """pin 的 key 解析不開就沒有「寫的時候 vs 今天」的對照 ——
    那是這個系統才做得到的東西,不該因為打錯一個字就默默消失。"""
    bad = [(p.slug, x.key) for p in all_posts for x in p.pins if x.now is None]
    assert bad == [], f"這些 pin 查不到現值:{bad}"


def test_a_pin_with_an_unknown_key_does_not_crash():
    """認不出來的 key 回 None,不要拋 —— 文章照樣顯示當時的值。"""
    assert P.resolve("nonsense:foo:bar", _data()) is None
    assert P.resolve("era:no-such-era:decision", _data()) is None


def test_front_matter_rejects_a_bad_kind(tmp_path):
    """kind 只有兩種。寫錯要在建置時就爆,不要讓文章悄悄不見。"""
    f = tmp_path / "x.md"
    f.write_text('---\ntitle: t\ndate: 2026-01-01\nkind: essay\n---\n內文\n',
                 encoding="utf-8")
    with pytest.raises(ValueError, match="kind"):
        P.load_all(_data(), str(tmp_path))


def test_posts_are_newest_first(all_posts):
    dates = [p.date for p in all_posts]
    assert dates == sorted(dates, reverse=True)


def test_every_era_has_a_chronicle_post(all_posts):
    """每一個階段都要有一則大事記。

    ⚠️ 這四則曾經被歸到「資本結構」,理由是那些文字有論述成分、
    讀起來像社論。那是**分類錯誤** —— 它們記的是「這一段期間發生了什麼」,
    本來就是大事記的內容。**文體像不像不是分類依據,內容是什麼才是。**
    """
    data = _data()
    eras = {e["id"] for e in data["chronicle"]}
    covered = {p.slug.split("-", 3)[-1] for p in all_posts if p.kind == "chronicle"}
    assert eras <= covered, f"這些階段還沒有對應的大事記:{sorted(eras - covered)}"
