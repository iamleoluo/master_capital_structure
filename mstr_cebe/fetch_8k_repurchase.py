"""從 SEC 8-K 抓逐週的「股票回購」表格 —— 方向與 ATM 表相反。

2026-07-27 起的 8-K 多出一張 "Shares Repurchased" 表,列出當週各券種買回的股數
與成本;2026-09-08 起 ATM 發行表(Shares Sold / Available for Issuance)整張消失,
只剩這張回購表 —— 也就是公司從「發優先股換現金」轉成「拿現金買回優先股」。

這件事對 CEBE 是實質利多,不能當成雜訊略過:買回的優先股會**永久消滅**它的清算
優先權(面額 $100/股),等於直接減少排在普通股前面的求償權。實測 2026-07-26 →
2026-09-20 這段期間已回購 STRC 約 1,173 萬股(約 $11.25 億成本,均價低於面額),
若不納入模型,求償權會被高估約 $11.7 億、CEBE 被低估。

表格結構(與 ATM 表同源,但只有兩個數值欄):

    During Period August 31, 2026 to September 7, 2026
    Security            | Shares Repurchased | Aggregate Purchase Price (in millions)
    STRF Stock (1)      | -                  | $ -
    10.00% Series A Perpetual Strife Preferred Stock      ← 說明列,要略過
    STRC Stock (1)      | 1,810,885          | $ 176.3
    ...
    Total                                                 ← 注意:Total 的標籤與數值
    1,810,885           | $ 176.3                            分屬兩個 <tr>

⚠️ 一律用 row/cell 結構解析,理由同 fetch_8k_atm(攤平文字猜順序會被 `$` 獨立 cell
   與跨欄說明列打壞)。
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import re
import time
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from .fetch_8k_atm import (
    CIK,
    SECURITIES,
    _H,
    _num,
    _parse_date,
    _PERIOD_PAT,
    _security_of,
    list_candidates,
)

__all__ = ["parse_repurchase_table", "fetch_all", "SECURITIES"]


def parse_repurchase_table(html: str) -> List[Dict]:
    """回傳這份 8-K 裡所有回購表的解析結果(通常 0 或 1 張)。

    金額單位為百萬美元;`-` 視為 0(該週沒買該券種),與 ATM 表一致。
    """
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict] = []

    for table in soup.find_all("table"):
        flat = re.sub(r"\s+", " ", table.get_text(" ", strip=True))
        if "Shares Repurchased" not in flat:
            continue

        period = _PERIOD_PAT.search(flat)
        if not period:
            continue

        rows: List[List[str]] = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            cells = [c for c in cells if c and c not in ("$", "(", ")")]
            if cells:
                rows.append(cells)

        by_security: Dict[str, Dict[str, float]] = {}
        total_shares: Optional[float] = None
        total_cost_m: Optional[float] = None

        for i, row in enumerate(rows):
            first = row[0]

            if first.strip().lower().startswith("total"):
                # Total 的數值可能在同一列,也可能被拆到下一列(實際版型是後者)
                vals = [v for v in (_num(c) for c in row[1:]) if v is not None]
                if len(vals) < 2 and i + 1 < len(rows):
                    vals = [v for v in (_num(c) for c in rows[i + 1]) if v is not None]
                if len(vals) >= 2:
                    total_shares, total_cost_m = vals[0], vals[1]
                continue

            sec = _security_of(first)
            if sec is None:
                continue          # 說明列 / 表頭,略過

            vals = [v for v in (_num(c) for c in row[1:]) if v is not None]
            if len(vals) < 2:
                vals = vals + [0.0] * (2 - len(vals))

            by_security[sec] = {"shares": vals[0], "cost_m": vals[1]}

        if not by_security:
            continue

        out.append({
            "week_start": _parse_date(period.group(1)).isoformat(),
            "week_end": _parse_date(period.group(2)).isoformat(),
            "by_security": by_security,
            "total_shares": total_shares,
            "total_cost_m": total_cost_m,
        })

    return out


def fetch_all(start: dt.date = dt.date(2026, 1, 1),
              sleep: float = 0.2, verbose: bool = True) -> List[Dict]:
    """爬所有 8-K,回傳逐週回購紀錄(同一週有多份申報時取最新那份)。

    預設從 2026-01-01 起 —— 回購表 2026-07-27 才首次出現,更早的申報沒有這張表。
    """
    candidates = list_candidates(start)
    merged: Dict[str, Dict] = {}
    for n, (filed, accn, doc, _items) in enumerate(candidates):
        url = (f"https://www.sec.gov/Archives/edgar/data/1050446/"
               f"{accn.replace('-', '')}/{doc}")
        try:
            html = requests.get(url, headers=_H, timeout=20).text
        except requests.RequestException as exc:
            if verbose:
                print(f"  [跳過] {filed}: {exc}", file=sys.stderr)
            continue
        for rec in parse_repurchase_table(html):
            rec["filed"] = filed
            merged[rec["week_end"]] = rec
        if verbose and n % 25 == 0:
            print(f"  {n}/{len(candidates)}...", file=sys.stderr)
        time.sleep(sleep)
    return [merged[k] for k in sorted(merged)]


def main() -> int:
    records = fetch_all()
    json.dump(records, sys.stdout, ensure_ascii=False)
    if records:
        tot: Dict[str, float] = {}
        for r in records:
            for sec, v in r["by_security"].items():
                tot[sec] = tot.get(sec, 0.0) + v["shares"]
        print(f"\n{len(records)} 週有回購表,"
              f"{records[0]['week_end']} → {records[-1]['week_end']}", file=sys.stderr)
        for sec, n in sorted(tot.items()):
            if n:
                print(f"  {sec}: 累計回購 {n:,.0f} 股", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
