"""從 SEC 8-K 抓逐週 BTC 持有量。

之前的建置紀錄(§2.4 / FINDING_BTC_DATE_PAIRING)誤判「2025-03-24 之後 Strategy
把 BTC 持有量從 8-K 移到官網 dashboard」—— 那個結論來自一次範圍過窄的
full-text-search(只搜尋 "bitcoins for approximately" 這句 prose 用語)。

實際狀況:公司只是換了揭露格式,數字始終都在 8-K 裡:
  - 2024-09 ~ 2025-03-24:prose 格式,"As of {date}, the Company ... held an
    aggregate of approximately {N} bitcoins"
  - 2025-03-31 起:改成結構化表格,標題「BTC Update」,內含
    "As of {date} / Aggregate BTC Holdings / {N}" 的表格列

兩種格式都要解析,合併起來後平均間隔 8.7 天,基本上就是逐週覆蓋整個 2024-09
到現在的範圍,只剩 3 個超過 14 天的間隔(最長 52 天),取代原本只有 ~8 個
季度點、最長 306 天空白的粗糙資料。

用法:
    python3 -m mstr_cebe.fetch_8k_btc > btc_weekly.json
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

_MONTHS = {m: i + 1 for i, m in enumerate([
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"])}

# prose 格式(2025-03-24 前):日期與「held an aggregate」限制在 100 字元內,
# 避免像文件裡別的「As of {某日}」段落(例如債務揭露)被錯誤配對到持有量數字。
_PROSE_PAT = re.compile(
    r'As of ([A-Za-z]+ \d{1,2}, \d{4}), [A-Za-z][^.]{0,80}'
    r'held an aggregate of approximately ([\d,]+) bitcoins')


def _parse_as_of(s: str) -> dt.date:
    m = re.match(r'([A-Za-z]+) (\d{1,2}), (\d{4})', s)
    if not m:
        raise ValueError(f"cannot parse date: {s}")
    return dt.date(int(m.group(3)), _MONTHS[m.group(1)], int(m.group(2)))


def list_weekly_8k_candidates(start: dt.date) -> List[Tuple[str, str, str, str]]:
    """回傳 (filed_date, accession, primary_doc, items) 清單,只留 7.01/8.01。"""
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


def _fetch_doc(accn: str, doc: str) -> str:
    url = f"https://www.sec.gov/Archives/edgar/data/1050446/{accn.replace('-', '')}/{doc}"
    r = requests.get(url, headers=_H, timeout=20)
    r.raise_for_status()
    return r.text


def _parse_table_format(html: str) -> List[Tuple[dt.date, int]]:
    """2025-03-31 起的「BTC Update」表格格式。用 row/cell 結構解析,不猜文字順序。"""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for table in soup.find_all("table"):
        txt = table.get_text(" ", strip=True)
        if "Aggregate BTC Holdings" not in txt:
            continue
        rows = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            cells = [c for c in cells if c and c != "$"]
            if cells:
                rows.append(cells)
        date_m = re.search(r'As of ([A-Za-z]+ \d{1,2}, \d{4})', txt)
        if not date_m:
            continue
        hdr_idx = hdr_row_i = None
        for ri, row in enumerate(rows):
            for ci, cell in enumerate(row):
                if cell.strip() == "Aggregate BTC Holdings":
                    hdr_idx, hdr_row_i = ci, ri
                    break
            if hdr_idx is not None:
                break
        if hdr_idx is None:
            continue
        btc_val: Optional[int] = None
        for row in rows[hdr_row_i + 1:]:
            if hdr_idx < len(row):
                cand = row[hdr_idx].replace(",", "").replace("$", "").strip()
                if cand.isdigit():
                    btc_val = int(cand)
                    break
        if btc_val is not None:
            out.append((_parse_as_of(date_m.group(1)), btc_val))
    return out


def _parse_prose_format(html: str) -> List[Tuple[dt.date, int]]:
    text = re.sub(r'\s+', ' ', BeautifulSoup(html, "html.parser").get_text(" "))
    matches = _PROSE_PAT.findall(text)
    if not matches:
        return []
    as_of, btc = matches[-1]     # 保留最後一筆(通常是最新的週更新段落)
    return [(_parse_as_of(as_of), int(btc.replace(",", "")))]


# ---------------------------------------------------------------------------
# 逐週買賣量 + 融資來源
# ---------------------------------------------------------------------------

# 「During Period September 2, 2025 to September 7, 2025」
_PERIOD_PAT = re.compile(
    r'During Period ([A-Za-z]+ \d{1,2}, \d{4}) to ([A-Za-z]+ \d{1,2}, \d{4})')

# 8-K 明示的融資來源。限制在 180 字元內,避免跨段落誤配對(與 _PROSE_PAT 同理)。
_FUNDING_PAT = re.compile(
    r'(?:bitcoin )?purchases were made using ([^.]{0,180})', re.I)
_SALE_USE_PAT = re.compile(
    r'proceeds from the bitcoin sales were used to ([^.]{0,160})', re.I)

# 敘述用語 → 券種。注意 Common ATM / Sales Agreement / MSTR ATM 都是指普通股。
_FUNDING_ALIASES = (
    (re.compile(r'\bSTRF\b', re.I), "STRF"),
    (re.compile(r'\bSTRC\b', re.I), "STRC"),
    (re.compile(r'\bSTRK\b', re.I), "STRK"),
    (re.compile(r'\bSTRD\b', re.I), "STRD"),
    (re.compile(r'\bSTRE\b', re.I), "STRE"),
    (re.compile(r'\bMSTR\b|Common ATM|Sales Agreement|class A common', re.I), "MSTR"),
    (re.compile(r'convertible note', re.I), "CONVERT"),
)


def normalize_funding(phrase: str) -> List[str]:
    """把敘述句正規化成券種清單。

    只寫「proceeds from the sale of shares under the ATM」這種沒指名的,
    回傳空清單 —— 交給呼叫端標成 unspecified,**不要猜**。
    """
    found = [code for pat, code in _FUNDING_ALIASES if pat.search(phrase)]
    seen: List[str] = []
    for c in found:
        if c not in seen:
            seen.append(c)
    return seen


# 2025-03-24 之前的 prose 版週買入:
# 「during the period between December 16, 2024 and December 22, 2024, the Company
#   acquired approximately 5,262 bitcoins ... at an average price of approximately $106,662」
_PROSE_ACTIVITY_PAT = re.compile(
    r'during the period between ([A-Za-z]+ \d{1,2}, \d{4}) and ([A-Za-z]+ \d{1,2}, \d{4}),'
    r'[^.]{0,120}?acquired approximately ([\d,]+) bitcoins'
    r'[^.]{0,200}?average price of approximately \$([\d,]+)', re.I)


def _cell_num(cell: str) -> Optional[float]:
    """資料列(非表頭)的數字解析。

    財務報表慣例:整個 cell 被括號包住代表負數,例如「(1,690)」。
    只在整個 cell 恰好是「(數字)」時才視為負號 —— 表頭文字裡的註腳標記
    像「(2)」不會流經這個函式(呼叫端只對資料列的 cell 呼叫它)。
    """
    c = cell.replace("$", "").replace(",", "").strip()
    if c in ("", "-", "–", "—"):
        return 0.0
    m = re.match(r'^\(([\d.]+)\)$', c)
    if m:
        return -float(m.group(1))
    m = re.match(r'^(-?\d+(?:\.\d+)?)', c)
    return float(m.group(1)) if m else None


def parse_activity(html: str) -> List[Dict]:
    """解析每週買賣量表格,取逐週買賣量與均價。

    版型是一張 6 欄的合併表:前三欄是本期買賣,後三欄是期末累計。
    用表頭文字定位欄位,不靠固定索引。買賣方向的表頭文字出現過三種版本:
      - "BTC Acquired"                 只有買
      - "BTC Sold"                     只有賣
      - "BTC Purchased / (Sold)"       兩者合併(2026-08-17 起出現的新版型)

    合併版的表頭本身含糊(同時出現 "Purchased" 與 "Sold" 字樣),
    不能再用「表頭有沒有 Sold 字樣」判斷方向 —— 那樣會把買入誤判成賣出。
    合併版的正負號改成完全依賴 _cell_num 對括號的解析
    (賣出以「(1,690)」表示,買入是純數字)。只有表頭**恰好**是
    「BTC Sold」(舊版,無合併)時才對數值取負號。
    """
    soup = BeautifulSoup(html, "html.parser")
    text = re.sub(r'\s+', ' ', soup.get_text(" "))

    funding: List[str] = []
    funding_raw = ""
    fm = _FUNDING_PAT.search(text)
    if fm:
        funding_raw = fm.group(1).strip()
        funding = normalize_funding(funding_raw)

    sale_use = ""
    sm = _SALE_USE_PAT.search(text)
    if sm:
        sale_use = sm.group(1).strip()

    out: List[Dict] = []

    # 先試 prose 版(2025-03-24 之前沒有表格,只有敘述句)
    pm = _PROSE_ACTIVITY_PAT.search(text)
    if pm:
        holdings_m = _PROSE_PAT.search(text)
        out.append({
            "week_start": _parse_as_of(pm.group(1)).isoformat(),
            "week_end": _parse_as_of(pm.group(2)).isoformat(),
            "btc_delta": float(pm.group(3).replace(",", "")),
            "avg_price": float(pm.group(4).replace(",", "")),
            "holdings": (float(holdings_m.group(2).replace(",", ""))
                         if holdings_m else None),
            "funding": funding,
            "funding_raw": funding_raw,
            "sale_use": sale_use,
        })

    for table in soup.find_all("table"):
        flat = re.sub(r'\s+', ' ', table.get_text(" ", strip=True))
        if not re.search(r'BTC (Acquired|Sold|Purchased)', flat):
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

        hdr_i = hdr = None
        for i, row in enumerate(rows):
            if any(re.match(r'BTC (Acquired|Sold|Purchased)', c) for c in row):
                hdr_i, hdr = i, row
                break
        if hdr is None:
            continue

        col_delta = next((j for j, c in enumerate(hdr)
                          if re.match(r'BTC (Acquired|Sold|Purchased)', c)), None)
        # 只有表頭「恰好」是 BTC Sold(舊版,單一方向)才對數值取負號。
        # 合併版「BTC Purchased / (Sold)」的正負號完全交給 _cell_num 判斷括號,
        # 不能用「表頭含 Sold 字樣」判斷 —— 那樣連買入週都會被誤判成賣出。
        delta_header = hdr[col_delta] if col_delta is not None else ""
        sold_only = bool(re.match(r'^BTC Sold\b', delta_header))
        col_avg = next((j for j, c in enumerate(hdr)
                        if re.search(r'Average (Purchase|Sale) Price', c)), None)
        col_hold = next((j for j, c in enumerate(hdr)
                         if "Aggregate BTC Holdings" in c), None)

        data = next((r for r in rows[hdr_i + 1:]
                     if _cell_num(r[0]) is not None), None)
        if data is None or col_delta is None:
            continue

        def at(idx: Optional[int]) -> Optional[float]:
            if idx is None or idx >= len(data):
                return None
            return _cell_num(data[idx])

        delta = at(col_delta)
        if delta is None:
            continue

        out.append({
            "week_start": _parse_as_of(period.group(1)).isoformat(),
            "week_end": _parse_as_of(period.group(2)).isoformat(),
            "btc_delta": -delta if sold_only else delta,
            "avg_price": at(col_avg),
            "holdings": at(col_hold),
            "funding": funding,
            "funding_raw": funding_raw,
            "sale_use": sale_use,
        })

    return out


def fetch_everything(start: dt.date = dt.date(2024, 7, 1),
                     sleep: float = 0.2, verbose: bool = True
                     ) -> Tuple[Dict[dt.date, int], List[Dict]]:
    """一次爬完,同時回傳 (累計持有量, 逐週活動)。避免為了兩種資料爬兩遍。"""
    candidates = list_weekly_8k_candidates(start)
    holdings: Dict[dt.date, int] = {}
    activity: Dict[str, Dict] = {}      # week_end → record(後蓋前)

    for n, (filed, accn, doc, items) in enumerate(candidates):
        try:
            html = _fetch_doc(accn, doc)
        except requests.RequestException as exc:
            if verbose:
                print(f"  [跳過] {filed} {doc}: {exc}", file=sys.stderr)
            continue
        for d, v in _parse_table_format(html):
            holdings[d] = v
        for d, v in _parse_prose_format(html):
            holdings[d] = v
        for rec in parse_activity(html):
            rec["filed"] = filed
            activity[rec["week_end"]] = rec
        if verbose and n % 25 == 0:
            print(f"  {n}/{len(candidates)}...", file=sys.stderr)
        time.sleep(sleep)

    return holdings, [activity[k] for k in sorted(activity)]


def fetch_all(start: dt.date = dt.date(2024, 7, 1),
             sleep: float = 0.2, verbose: bool = True) -> Dict[dt.date, int]:
    holdings, _ = fetch_everything(start, sleep, verbose)
    return holdings


def main() -> int:
    merged = fetch_all()
    pts = sorted(merged.items())
    payload = [[d.isoformat(), v] for d, v in pts]
    json.dump(payload, sys.stdout)
    gaps = [(pts[i + 1][0] - pts[i][0]).days for i in range(len(pts) - 1)]
    print(f"\n{len(pts)} 個觀測點,{pts[0][0]} → {pts[-1][0]}，"
          f"最長間隔 {max(gaps) if gaps else 0} 天", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
