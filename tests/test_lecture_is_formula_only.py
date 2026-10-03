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


# ---------------------------------------------------------------------------
# 13-exposition.md 的守門:開場必須是框架
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_a_section_does_not_open_straight_into_a_formula(page: pathlib.Path):
    """每一節的 `body` 不得以 `${` 開頭 —— 那代表第一個元素是公式或插值。

    由來:2026-10-04 診斷推導「很亂」(reference/13-exposition.md)。
    症狀是每一節都從一個細節開始,讀者不知道自己為什麼要看它。
    最極端的形式就是**開場直接是一條公式**:連一句話都沒有。

    這一支抓的是那個最極端的形式。框架寫得好不好機器判斷不了,
    但「有沒有先說一句話」判斷得了。
    """
    src = page.read_text(encoding="utf-8")
    bad = []
    for m in re.finditer(r'q: "([^"]+)",\s*\n\s*body: `\s*\n?\s*(\S)', src):
        if m.group(2) == "$":
            bad.append(m.group(1))
    assert bad == [], (
        f"{page.name} 這幾節開場直接是公式,沒有框架:{bad} —— "
        f"見 reference/13-exposition.md §5"
    )


def test_every_symbol_a_lecture_page_uses_is_defined_somewhere_on_it():
    """一頁用到的符號,必須在那一頁的符號表裡 —— 或在它前面的頁定義過。

    由來:2026-10-04 整頁重寫「資本架構」時,把符號表與位置對照一起刪掉了,
    結果**第一頁就在用 C、p₀、m 卻沒有任何定義**。

    整頁重寫會連同基礎定義一起掉,而那不會讓任何測試變紅 ——
    頁面照樣渲染,只是讀者看不懂。所以要一支守門。
    """
    import json
    order = ["structure", "quantities", "tools", "pairing", "time"]
    # 這幾個在文字裡出現但屬於推導中途引入的,不要求進符號表
    DERIVED = {"p_{0}", "A", "X", "y", "Q", "DL", "U", "t", "d"}
    defined: set = set()
    missing = []
    for name in order:
        src = (ROOT / "app" / "src" / "pages" / "lecture" / f"{name}.ts").read_text()
        for m in re.finditer(r"symbolTable\(\[([^\]]*)\]", src):
            defined |= {x.strip().strip('"') for x in m.group(1).split(",") if x.strip()}
        used = {m for m in re.findall(r'tex\("([A-Za-z](?:_\{[^}]*\})?)"\)', src)}
        for u in sorted(used - defined - DERIVED):
            missing.append(f"{name}.ts 用了 {u} 但沒有任何一頁定義過它")
    assert missing == [], "\n".join(missing)
