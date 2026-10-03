"""`if __name__ == "__main__":` 必須是模組的最後一段。

由來:`operations.py` 的 guard 原本卡在檔案中間,後面才定義 `PAR_PER_SHARE`。
import 時整個模組會跑完,所以**測試全綠**;但 `python3 -m` 會在 guard 那裡
就進 `main()`,常數還沒定義 —— CLI 直接 NameError,而測試看不到。

這種缺陷只有靜態檢查抓得到:它的症狀正是「測試通過」。
"""
import ast
import pathlib
from typing import Optional

import pytest

PKG = pathlib.Path(__file__).resolve().parent.parent / "mstr_cebe"
FILES = sorted(PKG.glob("*.py"))


def _guard_index(body) -> Optional[int]:
    for i, node in enumerate(body):
        if (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
                and isinstance(node.test.left, ast.Name)
                and node.test.left.id == "__name__"):
            return i
    return None


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_nothing_is_defined_after_the_main_guard(path: pathlib.Path) -> None:
    body = ast.parse(path.read_text()).body
    i = _guard_index(body)
    if i is None:
        return
    after = [type(n).__name__ for n in body[i + 1:]]
    assert not after, (
        f"{path.name}:guard 之後還有 {after} —— "
        f"`python3 -m mstr_cebe.{path.stem}` 跑不到那裡"
    )
