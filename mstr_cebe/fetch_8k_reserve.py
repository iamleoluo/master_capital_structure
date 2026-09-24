"""從 8-K 抓每週的 USD Reserve / USD Cash 餘額。

為什麼需要這個:
    CEBE 的求償權定義是「可轉債 + 優先股清算優先權 − 現金」,而現金原本只有
    XBRL 的季頻數字。2026 下半年公司靠普通股 ATM 募了 $51.6 億,大部分進了
    USD Reserve —— 但 XBRL 最後一個錨點停在 2026-06-30 的 $1.712B,
    整整看不到這筆錢。實測差距約 $44 億:公司自己在 8-K 揭露 2026-09-20 的
    Reserve $5.04B + Cash $1.05B = $6.09B。

    後果不是小數點問題:求償權被高估 $44 億、CEBE 被低估,而且做資本操作歸因時
    會只看到「增發稀釋」、看不到「換回來的資產」,把結論帶往完全相反的方向。

兩種版型:
    2026-06 起  「the balance of the USD Reserve was $2.55 billion」(只有 Reserve)
    2026-08-31 起「the balances of the USD Reserve and USD Cash were $5.04 billion
                  and $1.05 billion, respectively」(兩個數字)

⚠️ 只揭露 Reserve 的那段期間拿不到總流動性 —— Reserve 是「管理層指定用途的一部分」,
   是總現金的下限而非全部。所以那段期間回傳 usd_cash=None,由呼叫端決定怎麼跟
   XBRL 的總現金合併(見 interpolate.cash_anchors:取兩者較大值,寧可低估現金、
   高估求償權,也不要反過來)。
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from .fetch_8k_atm import CIK, _H, _parse_date, list_candidates

__all__ = ["parse_reserve", "fetch_all"]

_SCALE = {"million": 1e6, "billion": 1e9}

# 新版:Reserve 與 Cash 兩個數字
_BOTH_PAT = re.compile(
    r'As of ([A-Z][a-z]+ \d{1,2}, \d{4}), the balances of the USD Reserve and '
    r'USD Cash were\s*\$([\d.]+)\s*(million|billion)\s*and\s*\$([\d.]+)\s*(million|billion)',
    re.IGNORECASE)

# 舊版:只有 Reserve 一個數字(was / is 兩種時態都出現過)
_ONE_PAT = re.compile(
    r'As of ([A-Z][a-z]+ \d{1,2}, \d{4}), the balance of the USD Reserve '
    r'(?:was|is)\s*\$([\d.]+)\s*(million|billion)',
    re.IGNORECASE)


def parse_reserve(html: str) -> Optional[Dict]:
    """回傳 {as_of, usd_reserve, usd_cash} —— 舊版型的 usd_cash 是 None。"""
    text = re.sub(r"\s+", " ", BeautifulSoup(html, "html.parser")
                  .get_text(" ", strip=True))

    m = _BOTH_PAT.search(text)
    if m:
        return {
            "as_of": _parse_date(m.group(1)).isoformat(),
            "usd_reserve": float(m.group(2)) * _SCALE[m.group(3).lower()],
            "usd_cash": float(m.group(4)) * _SCALE[m.group(5).lower()],
        }

    m = _ONE_PAT.search(text)
    if m:
        return {
            "as_of": _parse_date(m.group(1)).isoformat(),
            "usd_reserve": float(m.group(2)) * _SCALE[m.group(3).lower()],
            "usd_cash": None,
        }
    return None


def fetch_all(start: dt.date = dt.date(2025, 12, 1),
              sleep: float = 0.15, verbose: bool = True) -> List[Dict]:
    """USD Reserve 是 2025-12-01 才設立的,更早的申報沒有這個欄位。"""
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
        rec = parse_reserve(html)
        if rec:
            rec["filed"] = filed
            merged[rec["as_of"]] = rec
        if verbose and n % 25 == 0:
            print(f"  {n}/{len(candidates)}...", file=sys.stderr)
        time.sleep(sleep)
    return [merged[k] for k in sorted(merged)]


def main() -> int:
    recs = fetch_all()
    json.dump(recs, sys.stdout, ensure_ascii=False)
    if recs:
        print(f"\n{len(recs)} 個觀測點,{recs[0]['as_of']} → {recs[-1]['as_of']}",
              file=sys.stderr)
        both = sum(1 for r in recs if r["usd_cash"] is not None)
        print(f"  其中 {both} 個同時有 USD Cash", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
