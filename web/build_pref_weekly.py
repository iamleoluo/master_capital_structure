#!/usr/bin/env python3
"""把優先股股數從「3-5 個季度錨點、線性插值」升級成逐週。

現況(mstr_cebe.interpolate.preferred_share_anchors)每個系列只有 IPO 日 + 一個
2026-06-30 的精確點,中間 14 個月是直線猜的。但 8-K 的 ATM Program Summary 表格
其實逐週列出每個系列賣了多少股 —— 用這個當「形狀」,再用已知的精確季末股數校正
累積誤差,就能把同一段時間的解析度從 2 個點提升到每週一個點。

驗證(見對話記錄):STRC、STRD 用這個方法重建 2026-06-30 的股數,
誤差分別是 0.0% 與 -0.5%;STRF、STRK 誤差 -2.1% / -5.9%
(可能有非 ATM 的發行管道,或早期週次的 ATM 表格解析不完整)。
即便如此,逐週校正後的序列仍遠比「兩點直線」準確 —— 校正點之間的誤差
不會累積超過已知錨點之間的落差。

輸出:web/raw/pref_shares_weekly.json,格式 {ticker: [[date, cumulative_shares], ...]}
"""
from __future__ import annotations

import datetime as dt
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "web", "raw")

SECS = ("STRF", "STRC", "STRK", "STRD")

# 已知的精確股數錨點:IPO 日 + 後續申報揭露的股數。
# STRE 不在這裡 —— 它沒有 ATM,單次發行後股數就沒再變過。
KNOWN: dict[str, list[tuple[str, float]]] = {
    "STRF": [("2025-03-20", 8_500_000), ("2026-06-30", 12_839_689)],
    "STRK": [("2025-01-30", 7_300_000), ("2026-06-30", 14_020_744)],
    "STRD": [("2025-06-05", 11_764_700), ("2026-06-30", 14_024_221)],
    "STRC": [("2025-07-24", 28_011_111), ("2026-03-31", 50_247_000),
             ("2026-06-30", 104_894_705), ("2026-07-24", 104_600_000)],
}


def build(atm: list[dict], sec: str) -> list[list]:
    known = sorted(KNOWN[sec])
    weekly = sorted(
        (w["week_end"], w["by_security"].get(sec, {}).get("shares") or 0.0)
        for w in atm
    )
    # 沒有這個點,插值在 IPO 之前的日期會被外推成 IPO 當天的股數(該系列
    # 根本還不存在卻顯示上千萬股)—— 這是實測抓到的真實 regression。
    ipo_date = dt.date.fromisoformat(known[0][0])
    out: list[tuple[str, float]] = [
        ((ipo_date - dt.timedelta(days=1)).isoformat(), 0.0),
        (known[0][0], float(known[0][1])),
    ]

    for (d0, s0), (d1, s1) in zip(known, known[1:]):
        seg = [(d, v) for d, v in weekly if d0 < d <= d1 and v > 0]
        raw_total = sum(v for _, v in seg)
        target = s1 - s0
        cum = 0.0
        for d, v in seg:
            cum += (v / raw_total * target) if raw_total > 0 else 0.0
            out.append((d, s0 + cum))
        # 段末強制對齊已知精確值,消除這一段內累積的比例誤差
        if not out or out[-1][0] != d1 or abs(out[-1][1] - s1) > 0.5:
            out.append((d1, float(s1)))

    return [[d, v] for d, v in out]


def main() -> None:
    atm = json.load(open(os.path.join(RAW, "atm_weekly.json"), encoding="utf-8"))
    result = {}
    for sec in SECS:
        pts = build(atm, sec)
        gaps = [
            (dt.date.fromisoformat(pts[i + 1][0]) - dt.date.fromisoformat(pts[i][0])).days
            for i in range(len(pts) - 1)
        ]
        print(f"{sec}: {len(pts)} 個錨點,{pts[0][0]} → {pts[-1][0]},"
              f"最長間隔 {max(gaps)} 天,平均 {sum(gaps) / len(gaps):.1f} 天")
        result[sec] = pts

    out_path = os.path.join(RAW, "pref_shares_weekly.json")
    json.dump(result, open(out_path, "w", encoding="utf-8"))
    print(f"\n已寫入 {out_path}")


if __name__ == "__main__":
    main()
