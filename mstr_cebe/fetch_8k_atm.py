"""從 SEC 8-K 抓「ATM Program Summary」表格 —— 逐週、逐券種的募資金額。

這張表是回答「這批 BTC 是拿什麼錢買的」的關鍵:8-K 的敘述句只寫出動用了哪幾個
ATM(例:「proceeds from the STRF ATM, STRK ATM and MSTR ATM」),沒有金額;
金額在這張表裡,而且是逐券種拆好的淨募資(net proceeds)。

兩種版型都要支援(建置期已實測):

  2025 版:第一欄是「STRF ATM」「STRC ATM」…,表頭
           Shares Sold | Notional Value (in millions) | Net Proceeds (in millions) | Available…
           每個券種下方還跟一列說明文字(「$2.1 billion of 10.00% series A…」),要略過。

  2026 版:多一個「Security」表頭,第一欄改成「STRF Stock」「MSTR Stock」…,
           說明文字改成券種全名(「Class A Common Stock」),同樣要略過。

⚠️ 一律用 row/cell 結構解析。先前用「攤平文字後照順序取 token」的做法在這裡會壞掉 ——
   括號註記、跨欄的說明列、以及被拆成獨立 cell 的「$」符號都會讓順序錯位。
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

USER_AGENT = "mstr-cebe-research (contact: iamleo789@gmail.com)"
CIK = "0001050446"
_H = {"User-Agent": USER_AGENT}

SECURITIES = ("STRF", "STRC", "STRK", "STRD", "STRE", "MSTR")

_MONTHS = {m: i + 1 for i, m in enumerate([
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"])}

# 「During Period September 2, 2025 to September 7, 2025」
_PERIOD_PAT = re.compile(
    r'During Period ([A-Za-z]+ \d{1,2}, \d{4}) to ([A-Za-z]+ \d{1,2}, \d{4})')


def _parse_date(s: str) -> dt.date:
    m = re.match(r'([A-Za-z]+) (\d{1,2}), (\d{4})', s.strip())
    if not m:
        raise ValueError(f"cannot parse date: {s}")
    return dt.date(int(m.group(3)), _MONTHS[m.group(1)], int(m.group(2)))


def _num(cell: str) -> Optional[float]:
    """把表格 cell 轉成數字。'-'、'—'、空字串都視為 0;無法解析回 None。"""
    c = cell.strip().replace("$", "").replace(",", "").replace("—", "-")
    if c in ("", "-", "–"):
        return 0.0
    # 去掉括號註記編號,如 '11.6 (2)'
    c = re.sub(r'\(\d+\)', '', c).strip()
    # 「591,606 MSTR Shares」這種帶單位的,只取前面的數字
    m = re.match(r'^(-?\d+(?:\.\d+)?)', c)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _security_of(cell: str) -> Optional[str]:
    """第一欄 → 券種代碼。'STRF ATM' / 'STRF Stock' / 'MSTR Stock' 都要能認。"""
    token = cell.strip().split()
    if not token:
        return None
    head = token[0].upper().rstrip(":")
    return head if head in SECURITIES else None


def parse_atm_table(html: str) -> List[Dict]:
    """回傳這份 8-K 裡所有 ATM 表格的解析結果(通常 0 或 1 張)。"""
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict] = []

    for table in soup.find_all("table"):
        flat = re.sub(r'\s+', ' ', table.get_text(" ", strip=True))
        if "Shares Sold" not in flat and "Available for Issuance" not in flat:
            continue

        period = _PERIOD_PAT.search(flat)
        if not period:
            continue

        rows: List[List[str]] = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            # 「$」常被拆成獨立 cell,會讓欄位錯位,先濾掉
            cells = [c for c in cells if c and c not in ("$", "(", ")")]
            if cells:
                rows.append(cells)

        by_security: Dict[str, Dict[str, float]] = {}
        total_m: Optional[float] = None

        for row in rows:
            first = row[0]

            if first.strip().lower().startswith("total"):
                for cell in row[1:]:
                    v = _num(cell)
                    if v is not None:
                        total_m = v
                        break
                continue

            sec = _security_of(first)
            if sec is None:
                continue          # 說明列 / 表頭,略過

            # 券種列後面依序是 shares / notional / net_proceeds / available。
            # 兩種版型欄數一致(4 個數值欄),用位置取。
            vals = [_num(c) for c in row[1:]]
            vals = [v for v in vals if v is not None]
            if len(vals) < 4:
                # 欄位不齊時不猜,補 0 但記錄下來
                vals = vals + [0.0] * (4 - len(vals))

            by_security[sec] = {
                "shares": vals[0],
                "notional_m": vals[1],
                "net_proceeds_m": vals[2],
                "available_m": vals[3],
            }

        if not by_security:
            continue

        out.append({
            "week_start": _parse_date(period.group(1)).isoformat(),
            "week_end": _parse_date(period.group(2)).isoformat(),
            "by_security": by_security,
            "total_m": total_m,
        })

    return out


# ---------------------------------------------------------------------------
# 抓取
# ---------------------------------------------------------------------------

def list_candidates(start: dt.date) -> List[Tuple[str, str, str, str]]:
    r = requests.get(f"https://data.sec.gov/submissions/CIK{CIK}.json",
                     headers=_H, timeout=20)
    r.raise_for_status()
    recent = r.json()["filings"]["recent"]
    forms, dates = recent["form"], recent["filingDate"]
    accn, docs = recent["accessionNumber"], recent["primaryDocument"]
    items = recent.get("items", [""] * len(forms))
    out = []
    for i in range(len(forms)):
        if forms[i] != "8-K" or dates[i] < start.isoformat():
            continue
        if "7.01" in items[i] or "8.01" in items[i]:
            out.append((dates[i], accn[i], docs[i], items[i]))
    return sorted(out)


def fetch_all(start: dt.date = dt.date(2024, 7, 1),
              sleep: float = 0.2, verbose: bool = True) -> List[Dict]:
    candidates = list_candidates(start)
    merged: Dict[str, Dict] = {}     # week_end → record(後蓋前,取最新申報)
    for n, (filed, accn, doc, _items) in enumerate(candidates):
        url = (f"https://www.sec.gov/Archives/edgar/data/1050446/"
               f"{accn.replace('-', '')}/{doc}")
        try:
            html = requests.get(url, headers=_H, timeout=20).text
        except requests.RequestException as exc:
            if verbose:
                print(f"  [跳過] {filed}: {exc}", file=sys.stderr)
            continue
        for rec in parse_atm_table(html):
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
        print(f"\n{len(records)} 週有 ATM 資料,"
              f"{records[0]['week_end']} → {records[-1]['week_end']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
