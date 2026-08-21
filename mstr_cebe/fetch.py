"""§2 市場價格 API。

只做兩件事:抓日線、驗證抓對了。

實測筆記(2026-08-17,建置當日):
  * Binance klines —— 免費、免 key、日線完整,分頁抓即可。**最省事,設為預設**。
  * Coinbase candles —— 每次上限 300 根,可用,作為 BTC 備援。
  * yfinance 0.2.36 在本機**壞掉**(No timezone found / delisted),
    但 Yahoo 的 chart 端點直接用 requests 打是好的 ⇒ 改直連端點,不依賴 yfinance。
  * stooq 被 JS challenge 擋住,不可用。

⚠️ §2.1:不同交易所收盤價會差 0.1–0.5%,做驗證時要容許誤差。
⚠️ §8.9:必須存完整 OHLC —— split 檢查的 $543 是**盤中高點**,不是收盤價。
"""
from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import requests

from . import data as D

USER_AGENT = "mstr-cebe-research (contact: iamleo789@gmail.com)"
_HEADERS = {"User-Agent": USER_AGENT}
_TIMEOUT = 30


@dataclass(frozen=True)
class Bar:
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None
    source: str = ""


def _ts(d: dt.date) -> int:
    return int(dt.datetime(d.year, d.month, d.day).timestamp())


def _get(url: str, params: Dict, attempts: int = 4) -> requests.Response:
    last: Optional[Exception] = None
    for i in range(attempts):
        try:
            r = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
            if r.status_code == 429:            # rate limit → 退避
                time.sleep(2 ** i)
                continue
            r.raise_for_status()
            return r
        except Exception as exc:                # noqa: BLE001 - 重試後再拋
            last = exc
            time.sleep(1.5 ** i)
    raise RuntimeError(f"GET {url} failed after {attempts} attempts: {last}")


# ---------------------------------------------------------------------------
# §2.1 BTC
# ---------------------------------------------------------------------------

def fetch_btc_binance(start: dt.date, end: dt.date) -> List[Bar]:
    """Binance BTCUSDT 日線。免 key,分頁 1000 根一批。"""
    url = "https://api.binance.com/api/v3/klines"
    out: List[Bar] = []
    cursor = _ts(start) * 1000
    end_ms = _ts(end) * 1000
    seen = set()
    while cursor <= end_ms:
        rows = _get(url, {"symbol": "BTCUSDT", "interval": "1d",
                          "startTime": cursor, "endTime": end_ms,
                          "limit": 1000}).json()
        if not rows:
            break
        for k in rows:
            d = dt.datetime.utcfromtimestamp(k[0] / 1000).date()
            if d in seen:
                continue
            seen.add(d)
            out.append(Bar(d, float(k[1]), float(k[2]), float(k[3]), float(k[4]),
                           float(k[5]), "binance"))
        nxt = rows[-1][0] + 86_400_000
        if nxt <= cursor:
            break
        cursor = nxt
    return sorted(out, key=lambda b: b.date)


def fetch_btc_coinbase(start: dt.date, end: dt.date) -> List[Bar]:
    """Coinbase BTC-USD 日線備援。每次上限 300 根,往回分頁。"""
    url = "https://api.exchange.coinbase.com/products/BTC-USD/candles"
    out: Dict[dt.date, Bar] = {}
    window = dt.timedelta(days=290)
    cur_start = start
    while cur_start <= end:
        cur_end = min(cur_start + window, end)
        rows = _get(url, {"granularity": 86400,
                          "start": cur_start.isoformat(),
                          "end": cur_end.isoformat()}).json()
        # Coinbase: [time, low, high, open, close, volume]
        for t, low, high, op, close, vol in rows:
            d = dt.datetime.utcfromtimestamp(t).date()
            out[d] = Bar(d, float(op), float(high), float(low), float(close),
                         float(vol), "coinbase")
        cur_start = cur_end + dt.timedelta(days=1)
        time.sleep(0.35)
    return [out[d] for d in sorted(out)]


# ---------------------------------------------------------------------------
# §2.2 MSTR
# ---------------------------------------------------------------------------

def fetch_mstr_yahoo(start: dt.date, end: dt.date,
                     symbol: str = "MSTR") -> List[Bar]:
    """Yahoo chart 端點直連。回傳的價格已回溯調整 split(見 verify_split)。"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    j = _get(url, {"period1": _ts(start),
                   "period2": _ts(end + dt.timedelta(days=1)),
                   "interval": "1d", "events": "div,split"}).json()
    result = j["chart"]["result"][0]
    q = result["indicators"]["quote"][0]
    out: List[Bar] = []
    for i, t in enumerate(result["timestamp"]):
        if q["close"][i] is None:
            continue
        d = dt.datetime.utcfromtimestamp(t).date()
        out.append(Bar(d, q["open"][i], q["high"][i], q["low"][i], q["close"][i],
                       q["volume"][i], "yahoo"))
    return sorted(out, key=lambda b: b.date)


# ---------------------------------------------------------------------------
# 驗證(§9 步驟 2:用 §5.10 的 fixture 驗證資料源正確)
# ---------------------------------------------------------------------------

@dataclass
class ValidationReport:
    name: str
    checked: int = 0
    matched: int = 0
    missing: List[str] = None
    mismatched: List[Tuple[str, float, float, float]] = None
    advisory: List[Tuple] = None      # Tier 3 的「~」約值:記錄但不判定失敗

    def __post_init__(self):
        self.missing = self.missing or []
        self.mismatched = self.mismatched or []
        self.advisory = self.advisory or []

    @property
    def ok(self) -> bool:
        return self.checked > 0 and not self.mismatched and not self.missing

    def summary(self) -> str:
        status = "PASS" if self.ok else "FAIL"
        s = (f"[{status}] {self.name}: {self.matched}/{self.checked} matched, "
             f"{len(self.mismatched)} mismatched, {len(self.missing)} missing")
        if self.advisory:
            s += f", {len(self.advisory)} advisory (Tier 3)"
        return s


def verify_mstr_against_fixture(bars: Sequence[Bar],
                                tolerance: float = 0.005) -> ValidationReport:
    """對照 §5.10 的 2026 年 6–8 月日線。容差 0.5%(§2.1 的交易所差異)。"""
    by_date = {b.date.isoformat(): b for b in bars}
    rep = ValidationReport("MSTR vs §5.10 fixture")
    for day, expected in sorted(D.MSTR_DAILY_FIXTURE.items()):
        rep.checked += 1
        bar = by_date.get(day)
        if bar is None:
            rep.missing.append(day)
            continue
        rel = abs(bar.close - expected) / expected
        if rel <= tolerance:
            rep.matched += 1
        else:
            rep.mismatched.append((day, expected, bar.close, rel))
    return rep


def verify_split(bars: Sequence[Bar]) -> ValidationReport:
    """§8.9:2024-11-21 的**盤中高點**應為 $543。若見 $5,430 代表未調整。"""
    when, expected, field, _ = D.SPLIT_CHECK
    rep = ValidationReport("MSTR 10-for-1 split adjustment")
    bar = next((b for b in bars if b.date == when), None)
    rep.checked = 1
    if bar is None:
        rep.missing.append(when.isoformat())
        return rep
    got = getattr(bar, field)
    rel = abs(got - expected) / expected
    if rel <= 0.005:
        rep.matched = 1
    else:
        rep.mismatched.append((when.isoformat(), expected, got, rel))
    return rep


# 依 tier 分容差 —— 混用一個容差會讓 Tier 3 的「~」約值把 Tier 1 的錨點一起拖下水。
# Tier 1 用 0.6%:§2.1 自己說不同交易所收盤價差 0.1–0.5%,FWP 用的是特定時點 spot。
BTC_TOLERANCE_BY_TIER = {"1": 0.006, "2": 0.02, "2/3": 0.02, "3": None}
# None = advisory only(記錄但不算失敗)


def verify_btc_anchors(bars: Sequence[Bar],
                       tolerance: Optional[float] = None) -> ValidationReport:
    """對照 §5.10 的 BTC 價格錨點,依 tier 分容差。

    傳 tolerance 可覆寫成單一容差(不建議,見 BTC_TOLERANCE_BY_TIER 的說明)。
    Tier 3 的「~」約值只記錄在 advisory,不列為 mismatch。
    """
    by_date = {b.date: b for b in bars}
    rep = ValidationReport("BTC vs §5.10 anchors (tier-aware)")
    for obs in D.MNAV_OBSERVATIONS:
        if obs.btc_price is None:
            continue
        bar = by_date.get(obs.as_of)
        tol = tolerance if tolerance is not None \
            else BTC_TOLERANCE_BY_TIER.get(obs.tier, 0.02)

        if bar is None:
            if tol is None:
                rep.advisory.append((obs.as_of.isoformat(), obs.btc_price,
                                     float("nan"), float("nan"), obs.tier))
            else:
                rep.checked += 1
                rep.missing.append(obs.as_of.isoformat())
            continue

        rel = abs(bar.close - obs.btc_price) / obs.btc_price
        if tol is None:                          # Tier 3:只記錄
            rep.advisory.append((obs.as_of.isoformat(), obs.btc_price,
                                 bar.close, rel, obs.tier))
            continue
        rep.checked += 1
        if rel <= tol:
            rep.matched += 1
        else:
            rep.mismatched.append((obs.as_of.isoformat(), obs.btc_price,
                                   bar.close, rel))
    return rep
