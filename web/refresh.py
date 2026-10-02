#!/usr/bin/env python3
"""每週更新:一支指令跑完 SEC → 事件 → 市場價 → app/data。

    python3 web/refresh.py              # 完整更新(會打網路)
    python3 web/refresh.py --offline    # 只重算,不打網路
    python3 web/refresh.py --dry-run    # 只報告各來源的新鮮度,不動任何檔案

**為什麼需要這支**:更新要照順序跑六個指令,而這個順序沒有被寫下來 ——
2026-10-02 檢查時發現資料停在 09-22(落後 10 天),其中
`web/raw/preferred_prices.json` 根本沒有對應的抓取腳本,只能手動補。
把順序寫成程式,它就不會再被記錯。

順序不能換,因為下游吃上游的輸出:

    1. L1  SEC 文件 ────→ 2. L2 事件 + web/raw 視圖
    3. 市場日線(BTC / MSTR)      4. 優先股日收盤
    5. 優先股逐週股數(吃 atm_weekly.json,所以要在 2 之後)
    6. app/data/*.json(吃前面全部)

每一步都印出前後的覆蓋區間,對不上就看得見。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "web", "raw")
sys.path.insert(0, ROOT)

PREF_PATH = os.path.join(RAW, "preferred_prices.json")

# 各來源「正常」能落後幾天。門檻不一樣,因為節奏不一樣 ——
# 週 8-K 報的是上一週,所以 L2 事件天生就落後幾天,拿交易日的標準去量它
# 會每次都亮紅燈,而會亂叫的監測等於沒有監測。
LAG_OK = {
    "SEC 文件": 4,        # 8-K 一週一份,加上週末
    "L2 事件": 11,        # 申報日 − 報導期末 ≈ 4 天,再加一週的申報週期
    "市場日線": 4,        # 交易日,跨週末最多 3 天
    "優先股報價": 4,
    "app/data": 4,
}


def _run(label: str, argv: list) -> None:
    print(f"\n── {label}")
    r = subprocess.run([sys.executable] + argv, cwd=ROOT)
    if r.returncode:
        raise SystemExit(f"✗ {label} 失敗(exit {r.returncode})")


def coverage() -> dict:
    """各來源目前涵蓋到哪一天。--dry-run 與每步結束都用這個報告。"""
    from mstr_cebe import db as DB
    from mstr_cebe import events as E

    out = {}
    conn = E.connect()
    try:
        out["SEC 文件"] = conn.execute(
            "SELECT MAX(filed_at) FROM documents").fetchone()[0]
        out["L2 事件"] = conn.execute(
            "SELECT MAX(effective_at) FROM events").fetchone()[0]
    finally:
        conn.close()
    conn = DB.connect(os.path.join(ROOT, "mstr_cebe.sqlite"))
    try:
        out["市場日線"] = conn.execute(
            "SELECT MAX(date) FROM market_daily").fetchone()[0]
    finally:
        conn.close()
    with open(PREF_PATH, encoding="utf-8") as f:
        out["優先股報價"] = max(max(v) for v in json.load(f).values())
    with open(os.path.join(ROOT, "app", "data", "daily.json"), encoding="utf-8") as f:
        out["app/data"] = json.load(f)["date"][-1]
    return out


def report(title: str) -> None:
    today = dt.date.today()
    print(f"\n{title}")
    stale = []
    for k, v in coverage().items():
        lag = (today - dt.date.fromisoformat(v)).days
        ok = lag <= LAG_OK[k]
        print(f"  {'  ' if ok else '⚠️'} {k:<12}{v}   落後 {lag} 天"
              f"{'' if ok else f'(正常應在 {LAG_OK[k]} 天內)'}")
        if not ok:
            stale.append(k)
    if stale:
        print(f"  → 過期:{'、'.join(stale)}")


def refresh_preferred_prices() -> None:
    """優先股日收盤。重抓整段歷史並與舊檔對照 —— 不一致要看得見。"""
    from mstr_cebe import fetch as F

    with open(PREF_PATH, encoding="utf-8") as f:
        old = json.load(f)
    since = {t: dt.date.fromisoformat(min(v)) for t, v in old.items()}
    new = F.fetch_preferred_closes(since)

    bad = F.diff_closes(old, new)
    prev_last = max(max(v) for v in old.values())
    for t, days in bad.items():
        # 前次抓取當天可能抓到盤中價,重抓拿到最終收盤 —— 這是預期內的
        unexpected = [d for d in days if d != prev_last]
        if unexpected:
            raise SystemExit(
                f"✗ {t} 的歷史收盤與舊檔不一致(非前次抓取當天):{unexpected[:5]}\n"
                f"  資料源可能變了,先看過再決定,不要直接覆蓋。")
        print(f"  {t}: {days} 由盤中價更新為最終收盤")

    for t, v in new.items():
        print(f"  {t}: {len(old[t])} → {len(v)} 天,最後 {max(v)}")
    with open(PREF_PATH, "w", encoding="utf-8") as f:
        json.dump(new, f, ensure_ascii=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="不打網路,只重算下游")
    ap.add_argument("--dry-run", action="store_true", help="只報告新鮮度")
    a = ap.parse_args()

    report("更新前:")
    if a.dry_run:
        return 0

    if not a.offline:
        _run("1. L1 — 補抓 SEC 文件", ["-m", "mstr_cebe.archive", "backfill"])
    _run("2. L2 — 由文件重算事件,並寫出 web/raw 視圖",
         ["-m", "mstr_cebe.events", "rebuild"])
    if not a.offline:
        _run("3. 市場日線(BTC / MSTR)", ["build_db.py"])
        print("\n── 4. 優先股日收盤")
        refresh_preferred_prices()
    _run("5. 優先股逐週股數", ["web/build_pref_weekly.py"])
    _run("6. app/data/*.json(含兩個黃金錨點)", ["web/build_data.py"])

    report("更新後:")
    print("\n接著跑:")
    print("  python3 reference/verify.py      # 23 條恆等式")
    print("  python3 -m pytest tests/ -q      # 全部測試")
    print("  python3 reference/build.py       # reference/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
