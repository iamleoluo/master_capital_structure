#!/usr/bin/env python3
"""用已進版控的輸入重算 app/data 裡能重算的檔，再跟現況比。

市場日線在 mstr_cebe.sqlite。觀測在 data/obs 與 web/raw。
web/archive.sqlite 沒有進版控。沒有事件時，大事記、觀點、操作清單
與需要事件表的 findings 不在這次比對裡，腳本會明講。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _build_data():
    spec = importlib.util.spec_from_file_location("build_data", ROOT / "web" / "build_data.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _load(name: str):
    return json.loads((ROOT / "app" / "data" / name).read_text(encoding="utf-8"))


def main() -> int:
    bd = _build_data()
    failed = False
    for label, built, filename in (
        ("daily", bd.build_daily(), "daily.json"),
        ("weekly", bd.build_weekly(), "weekly.json"),
    ):
        committed = _load(filename)
        if built != committed:
            print(f"{filename} 與重算結果不同")
            failed = True
        else:
            n = len(built["date"]) if isinstance(built, dict) else len(built)
            print(f"{filename} 重算後相同（{n} 列）")

    from mstr_cebe import events as EV
    conn = EV.connect()
    try:
        n_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    except Exception as exc:
        n_events = 0
        print(f"事件表讀不到：{exc}")
    finally:
        conn.close()
    if n_events == 0:
        print("web/archive.sqlite 沒有事件（這個檔不進版控）。"
              "chronicle、posts、operations 與依賴事件的 findings 這次不重算。")
    else:
        print(f"事件表有 {n_events} 筆。這次仍只比對 daily 與 weekly；"
              "完整 build_data 會改寫 app/data，留給有檔案庫的那次手動跑。")

    from deploy_target import DEPLOY_PROJECT
    print(f"DEPLOY_PROJECT={DEPLOY_PROJECT!r}（只讀常數，不部署）")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
