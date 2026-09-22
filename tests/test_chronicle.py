"""大事記的結構性測試。

這組測試守的不是數字對不對(數字是管線從 daily.json 算的,會隨資料更新而變),
而是**分期本身的完整性**:不能有空隙、不能重疊、不能漏掉時間軸的任何一段,
而且人工標註的工具要跟原始資料對得上。

新增主題時最容易犯的錯就是忘記把前一則的 end 補上(造成重疊)或補錯一天
(造成空隙),這裡把那兩種情況釘死。
"""
from __future__ import annotations

import datetime as dt

import pytest

from mstr_cebe import chronicle as CH


def test_ids_are_unique():
    ids = [e.id for e in CH.ERAS]
    assert len(ids) == len(set(ids)), f"重複的 era id: {ids}"


def test_eras_are_chronological():
    starts = [e.start for e in CH.ERAS]
    assert starts == sorted(starts), "ERAS 必須依時間排序(append-only)"


def test_only_the_last_era_is_open():
    """進行中的階段只能有一個,而且必須是最後一則。"""
    open_ = [e.id for e in CH.ERAS if e.end is None]
    assert open_ == [CH.ERAS[-1].id], f"進行中的階段應只有最後一則,實得 {open_}"


def test_no_gaps_or_overlaps():
    """相鄰兩期必須無縫銜接:前一期的 end 就是後一期 start 的前一天。

    空隙會讓某段歷史沒有任何主題涵蓋;重疊會讓同一天同時屬於兩個階段,
    兩者都會讓前端的區間圖表畫出錯的東西。
    """
    for a, b in zip(CH.ERAS, CH.ERAS[1:]):
        assert a.end is not None, f"{a.id} 不是最後一則,end 不能是 None"
        expected = b.start - dt.timedelta(days=1)
        assert a.end == expected, (
            f"{a.id} 的 end ({a.end}) 應該是 {b.id} 起點的前一天 ({expected})")


def test_every_era_has_positive_duration():
    for e in CH.ERAS:
        end = e.end or dt.date.today()
        assert end > e.start, f"{e.id} 的區間長度不是正的"


@pytest.mark.parametrize("era", CH.ERAS, ids=[e.id for e in CH.ERAS])
def test_tools_reference_real_toolkit_entries(era):
    for t in era.tools:
        assert t in CH.TOOLS_BY_ID, f"{era.id} 標註了不存在的工具 {t!r}"


@pytest.mark.parametrize("era", CH.ERAS, ids=[e.id for e in CH.ERAS])
def test_era_has_narrative(era):
    """每一則都要有標題、定性與至少一段敘述 —— 空殼條目不該被發布。"""
    assert era.title.strip()
    assert era.subtitle.strip()
    assert era.body and all(p.strip() for p in era.body)
    assert era.trigger.strip()


def test_toolkit_ids_unique_and_complete():
    ids = [t.id for t in CH.TOOLS]
    assert len(ids) == len(set(ids))
    for t in CH.TOOLS:
        assert t.label.strip() and t.note.strip() and t.cebe.strip()


def test_unused_tools_are_declared_intentional():
    """工具箱裡沒被任何階段用到的項目,必須明確列在 UNUSED_BY_DESIGN。

    這樣「公司有這把工具但從來沒用」是一個被記錄下來的判斷,而不是漏標。
    哪天真的開始動用了,這個測試會逼人回來把它從例外清單移除。
    """
    used = {t for e in CH.ERAS for t in e.tools}
    unused = {t.id for t in CH.TOOLS} - used
    assert unused == set(CH.UNUSED_BY_DESIGN), (
        f"未被使用的工具 {sorted(unused)} 與 UNUSED_BY_DESIGN "
        f"{sorted(CH.UNUSED_BY_DESIGN)} 不一致")
