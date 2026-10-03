"""`reference/` 的每一條章節引用都必須指到存在的檔案。

由來:2026-10-03 把 reference 重新編號(插入 01-architecture 與 04-narrative,
其餘整批後移),一次動到 32 個檔案、241 條交叉連結。這種改動靠眼睛看一定會
漏掉一兩條,而**漏掉的症狀是讀者點了連結進到 404,不是任何測試會紅**。

所以這一支守的不是模型,是**文件自己的完整性**。
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
REF = ROOT / "reference"

CHAPTERS = {p.name for p in REF.glob("[0-9][0-9]-*.md")}

# 會引用章節的所有地方
SCANNED = (
    sorted(REF.glob("*.md"))
    + sorted(REF.glob("*.py"))
    + [ROOT / "CLAUDE.md"]
    + sorted((ROOT / "mstr_cebe").glob("*.py"))
    + sorted((ROOT / "web").glob("*.py"))
    + sorted((ROOT / "app" / "src").rglob("*.ts"))
)

CHAPTER_RE = re.compile(r"\b(\d\d-[a-z-]+\.md)\b")


@pytest.mark.parametrize("path", SCANNED, ids=lambda p: str(p.relative_to(ROOT)))
def test_every_chapter_reference_points_at_a_file_that_exists(path) -> None:
    if not path.exists():
        pytest.skip(f"{path} 不存在")
    bad = sorted({m for m in CHAPTER_RE.findall(path.read_text())
                  if m not in CHAPTERS})
    assert not bad, (
        f"{path.relative_to(ROOT)} 指向不存在的章節:{bad}。"
        f"現有章節:{sorted(CHAPTERS)}"
    )


def test_the_markdown_link_label_agrees_with_its_target_number() -> None:
    """`[02 §4](03-operations.md)` 這種編號對不上的連結要抓出來。

    重編號時最容易留下的殘骸:路徑改對了,顯示文字還是舊編號。
    讀者看到的是錯的章號,而連結本身是好的 —— 點進去才發現不對。
    """
    wrong = []
    pat = re.compile(r"\[(\d\d)(?=[\s §\-\]])([^\]]*)\]\((?:reference/)?(\d\d)-[a-z-]+\.md")
    for p in sorted(REF.glob("*.md")) + [ROOT / "CLAUDE.md"]:
        for i, line in enumerate(p.read_text().split("\n"), 1):
            for label_no, _, target_no in pat.findall(line):
                if label_no != target_no:
                    wrong.append(f"{p.name}:{i} 顯示 {label_no} 但指向 {target_no}")
    assert not wrong, "編號對不上的連結:\n" + "\n".join(wrong)


def test_build_order_covers_every_chapter() -> None:
    """`build.py` 的 ORDER 漏掉一章,HTML 版就會少一章而不報錯。"""
    order = re.findall(r'\("([^"]+\.md)"', (REF / "build.py").read_text())
    assert set(order) == CHAPTERS, (
        f"ORDER 少了 {sorted(CHAPTERS - set(order))};"
        f"多了 {sorted(set(order) - CHAPTERS)}"
    )
    assert order == sorted(order), f"ORDER 沒有照編號排:{order}"
