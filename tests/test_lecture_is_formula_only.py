"""守門:講義只准有公式解,不准有數值。

CLAUDE.md 的核心概念是「同一個 L1–L4 解兩次」:講義解公式解、
儀表板解數值解。那條界線很容易在六個月後悄悄失守 —— 有人為了「順手補個
今天的數字」就 import 了 `../../data`,然後講義開始隨每週更新而過期。

所以把它變成會紅的東西,與兩個黃金錨點同一個等級的守門。
判準見 CLAUDE.md:**一句話裡出現具體數字,它就屬於數值解。**
"""
from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
LECTURE = ROOT / "app" / "src" / "pages" / "lecture"

PAGES = sorted(LECTURE.glob("*.ts"))


def test_the_lecture_directory_exists_and_is_not_empty():
    assert PAGES, "講義頁不見了 —— 這個守門就沒有意義了"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_a_lecture_page_never_imports_observed_data(page: pathlib.Path):
    """講義不得 import 資料入口。

    這是最硬的一道:拿不到 `daily` / `weekly` / `strategy` / `chronicle` / `meta`,
    就不可能顯示今天的讀數。**公式**從 `../../formulas` 來,那一份由
    `toolbox` 產生,裡面沒有任何觀測值。
    """
    src = page.read_text(encoding="utf-8")
    bad = re.findall(r'from\s+"[^"]*\bdata"', src)
    assert bad == [], (
        f"{page.name} import 了資料入口 {bad} —— 講義只准吃 ../../formulas")


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_a_lecture_page_has_no_hardcoded_observations(page: pathlib.Path):
    """就算不 import,也不准把數字抄進去。

    抓的是**觀測值長什麼樣**,不是所有數字:
      * 千分位(`1,234`)—— 公式裡不會出現逗號分隔的數
      * 錢(`$1.28B`、`$90`)
      * 百分比(`-26.3%`)

    公式常數不在此限,因為它們不長這樣:$10^{8}$ 寫成 `10^{8}`、
    面額門檻寫成 `m > 1 - d`。
    """
    src = page.read_text(encoding="utf-8")
    # 先把 style="..." 拿掉 —— 版面數值不是觀測值
    body = re.sub(r'style="[^"]*"', "", src)
    hits = (re.findall(r"\d,\d{3}", body)
            + re.findall(r"\$\s?\d", body)
            + re.findall(r"\d+\.\d+\s?%", body))
    assert hits == [], (
        f"{page.name} 出現看起來像觀測值的數字 {hits[:5]} —— "
        f"那屬於數值解,請放到儀表板")


def test_the_shared_lecture_layout_is_also_clean():
    """共用版型也算講義的一部分。"""
    for f in ("components/lecture.ts", "components/placeMap.ts"):
        src = (ROOT / "app" / "src" / f).read_text(encoding="utf-8")
        bad = re.findall(r'from\s+"[^"]*\bdata"', src)
        assert bad == [], f"{f} import 了資料入口 {bad}"
