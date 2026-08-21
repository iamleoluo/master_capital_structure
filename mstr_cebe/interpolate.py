"""把 §5 的季度資本結構錨點,線性插值成每日序列。

規格書 §3 的原始設計是「事件頻,查詢時 forward-fill」—— 這在申報間隔短時沒問題,
但 2025-03-31 到 2026-01-31 之間有 9 個月沒有觀測點,forward-fill 會做出「整整
9 個月資本結構完全不變」的假象,而且在下一個觀測點當天製造一個 20–30% 的假跳動
(mNAV 因為分母瞬間改變而暴衝,但那天股價可能只動 1%)。

這個模組改用線性插值:在任兩個真實觀測點之間,假設數值均勻變化。這同樣是假設,
但至少不會在單一天製造不存在的波動,更適合用來分離「結構變化」與「情緒變化」。

每個插值結果都攜帶 `days_to_anchor`(距離最近真實觀測點幾天),讓下游知道
哪些日子是紮實的,哪些是長距離插值出來的猜測。
"""
from __future__ import annotations

import bisect
import json
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from . import data as D
from .core import CapitalStructure, PreferredSeries


@dataclass(frozen=True)
class InterpResult:
    value: float
    days_to_anchor: int          # 0 = 當天就是觀測點
    is_extrapolated: bool        # True = 落在第一個或最後一個錨點之外


def interpolate_series(anchors: Sequence[Tuple[date, float]],
                       target: date) -> InterpResult:
    """線性插值。落在錨點範圍外時,用最近端點的值水平延伸(不外推斜率)。"""
    pts = sorted(anchors, key=lambda p: p[0])
    if not pts:
        raise ValueError("no anchors")
    dates = [p[0] for p in pts]

    if target <= dates[0]:
        return InterpResult(pts[0][1], (dates[0] - target).days, True)
    if target >= dates[-1]:
        return InterpResult(pts[-1][1], (target - dates[-1]).days, True)

    i = bisect.bisect_right(dates, target)
    d0, v0 = pts[i - 1]
    d1, v1 = pts[i]
    if d0 == target:
        return InterpResult(v0, 0, False)
    span = (d1 - d0).days
    frac = (target - d0).days / span
    value = v0 + (v1 - v0) * frac
    days_to_anchor = min((target - d0).days, (d1 - target).days)
    return InterpResult(value, days_to_anchor, False)


def _merge(*series: Sequence[Tuple[date, float]]) -> List[Tuple[date, float]]:
    """後面的來源覆蓋前面同一天的值(用來讓 XBRL 蓋掉舊的粗估值)。"""
    merged: Dict[date, float] = {}
    for s in series:
        for d, v in s:
            merged[d] = v
    return sorted(merged.items())


# ---------------------------------------------------------------------------
# 各欄位的錨點清單:合併 data.py 手工整理的 Tier 1 點 + 新抓的 XBRL 季度點
# ---------------------------------------------------------------------------

def btc_held_anchors() -> List[Tuple[date, float]]:
    """§5.7b 的逐週 8-K 觀測點(90 個,平均間隔 8.7 天)當主力,
    XBRL 季度數字與舊的 spec 點位當補充(只在週資料沒有覆蓋的日期生效)。"""
    weekly = [(d, float(v)) for d, v in D.WEEKLY_BTC_HELD]
    spec = [(d, v) for d, v, _ in D.BTC_HELD]
    return _merge(spec, D.XBRL_BTC_HELD, weekly)   # 週資料優先權最高(最後合併覆蓋)


def debt_anchors() -> List[Tuple[date, float]]:
    # XBRL LongTermDebtNoncurrent 提供每季,比原本 CONVERTIBLE_TOTALS 密得多
    return _merge(D.XBRL_DEBT)


def cash_anchors() -> List[Tuple[date, float]]:
    return _merge(D.XBRL_CASH)


def shares_basic_anchors() -> List[Tuple[date, float]]:
    """優先用期末在外股數(exact point-in-time),用單季加權平均補中繼點。"""
    exact = [(sc.as_of, sc.basic) for sc in D.SHARE_COUNTS if sc.basic]
    # 加權平均代表「該季度中點附近」的股數,指派到季度中點日期
    wavg = []
    for end, val in D.XBRL_WAVG_SHARES:
        mid = end - timedelta(days=45)   # 單季中點的粗略估計
        wavg.append((mid, val))
    return _merge(wavg, exact)   # exact 覆蓋(較準)


_PREF_WEEKLY_PATH = Path(__file__).resolve().parent.parent / "web" / "raw" / "pref_shares_weekly.json"


@lru_cache(maxsize=1)
def _pref_weekly_cache() -> Dict[str, List[Tuple[date, float]]]:
    """逐週優先股股數(見 web/build_pref_weekly.py)。

    用 ATM Program Summary 表格的逐週賣股數當「形狀」,再用已知的精確季末股數
    校正,把 STRF/STRC/STRK/STRD 從 3-5 個季度錨點升級成每週一個點
    (STRC/STRD 重建誤差 0.0%/-0.5%,STRF/STRK 誤差 -2%~-6%,
    仍遠比兩點直線插值準確)。檔案不存在時安靜回退,不炸掉。
    """
    if not _PREF_WEEKLY_PATH.exists():
        return {}
    raw = json.loads(_PREF_WEEKLY_PATH.read_text(encoding="utf-8"))
    return {t: [(date.fromisoformat(d), float(v)) for d, v in pts]
            for t, pts in raw.items()}


def _preferred_share_anchors(ticker: str) -> List[Tuple[date, float]]:
    """單一優先股系列的在外股數錨點:IPO 日掛 0→IPO股數,加上各季申報股數。

    STRF/STRC/STRK/STRD 優先用逐週的 ATM 重建序列(見上);STRE 沒有 ATM
    增發,單次發行後股數沒再變過,維持原本 IPO + 申報點的做法。
    """
    weekly = _pref_weekly_cache().get(ticker)
    if weekly:
        return _merge(weekly)

    anchors: List[Tuple[date, float]] = []
    ipo = next((i for i in D.PREFERRED_IPOS if i.ticker == ticker), None)
    if ipo:
        anchors.append((ipo.pricing_date - timedelta(days=1), 0.0))
        anchors.append((ipo.pricing_date, ipo.ipo_shares))
    for pb in D.PREFERRED_BALANCES:
        shares = (pb.shares_by_ticker or {}).get(ticker)
        if shares:
            anchors.append((pb.as_of, shares))
    if ticker == "STRC":
        for d, _usd, shares in D.STRC_TRAJECTORY:
            if shares:
                anchors.append((d, shares))
        # 2026-07-24 回購後:只知清算優先權,shares = 清算優先權 ÷ $100
        buyback = next(pb for pb in D.PREFERRED_BALANCES if pb.as_of == date(2026, 7, 24))
        if buyback.strc:
            anchors.append((buyback.as_of, buyback.strc / 100.0))
    return _merge(anchors)


PREFERRED_TICKERS = ("STRF", "STRC", "STRK", "STRD", "STRE")


def preferred_share_anchors() -> Dict[str, List[Tuple[date, float]]]:
    return {t: _preferred_share_anchors(t) for t in PREFERRED_TICKERS}


# ---------------------------------------------------------------------------
# 組裝:任一天的插值資本結構
# ---------------------------------------------------------------------------

_STATED = {"STRF": 100.0, "STRC": 100.0, "STRK": 100.0, "STRD": 100.0, "STRE": 100.0}
_FX_EUR = 884_120 / 775_000   # §5.2 2026-06-30 反解的 EUR/USD,STRE 沒有更好的逐日匯率


def interpolated_structure(on: date,
                           btc_a=None, debt_a=None, cash_a=None,
                           shares_a=None, pref_a=None) -> Tuple[CapitalStructure, Dict[str, int]]:
    """回傳 (插值後的資本結構, 各欄位的 days_to_anchor 字典)。"""
    btc_a = btc_a or btc_held_anchors()
    debt_a = debt_a or debt_anchors()
    cash_a = cash_a or cash_anchors()
    shares_a = shares_a or shares_basic_anchors()
    pref_a = pref_a or preferred_share_anchors()

    r_btc = interpolate_series(btc_a, on)
    r_debt = interpolate_series(debt_a, on)
    r_cash = interpolate_series(cash_a, on)
    r_shares = interpolate_series(shares_a, on)

    prefs = []
    staleness = {"btc": r_btc.days_to_anchor, "debt": r_debt.days_to_anchor,
                "cash": r_cash.days_to_anchor, "shares": r_shares.days_to_anchor}
    for t in PREFERRED_TICKERS:
        anchors = pref_a[t]
        if not anchors:
            continue
        r = interpolate_series(anchors, on)
        shares = max(0.0, r.value)
        if shares <= 0:
            continue
        native = shares * _STATED[t]
        usd = native * (_FX_EUR if t == "STRE" else 1.0)
        prefs.append(PreferredSeries(
            ticker=t, liquidation_preference_usd=usd, shares=shares,
            rank=D.SENIORITY_RANK.get(t, 99), convertible=(t == "STRK"),
            currency="EUR" if t == "STRE" else "USD",
            liquidation_preference_native=(native if t == "STRE" else None),
            fx_rate_as_of=(_FX_EUR if t == "STRE" else None),
            is_estimated=r.days_to_anchor > 0,
        ))
        staleness[f"pref_{t}"] = r.days_to_anchor

    cs = CapitalStructure(
        as_of=on,
        btc_held=r_btc.value,
        debt_notional_usd=r_debt.value,
        preferreds=tuple(prefs),
        usd_reserve_usd=D.usd_reserve_as_of(on),
        cash_and_equiv_usd=r_cash.value,
        shares_basic=r_shares.value,
        shares_fdso=None,
        shares_assumed_diluted=None,
        annual_obligations_usd=D.annual_obligations_as_of(on)[0] or None,
        source_tier=1,
        source_ref="季度 SEC XBRL 錨點線性插值",
        is_estimated=max(staleness.values()) > 0,
        note=f"max_days_to_anchor={max(staleness.values())}",
    )
    return cs, staleness
