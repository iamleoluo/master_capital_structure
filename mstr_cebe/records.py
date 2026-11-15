"""data.py 與 CSV 讀寫共用的列型別。數字仍以 data/obs、data/ref 為正本。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, Optional


@dataclass(frozen=True)
class PreferredIPO:
    ticker: str
    name: str
    pricing_date: date
    ipo_shares: float
    offer_price: float
    stated_amount: float
    currency: str
    ipo_liquidation_pref: float
    net_proceeds: float
    dividend_rate_pct: Optional[float]
    rank: int
    convertible: bool
    note: str = ""


@dataclass(frozen=True)
class PreferredBalance:
    as_of: date
    strk: Optional[float]
    strf: Optional[float]
    strd: Optional[float]
    strc: Optional[float]
    stre_usd: Optional[float]
    total: Optional[float]
    total_shares: Optional[float]
    source: str
    is_estimated: bool
    stre_eur: Optional[float] = None
    fx_eur_usd: Optional[float] = None
    shares_by_ticker: Optional[Dict[str, float]] = None


@dataclass(frozen=True)
class ShareCount:
    as_of: date
    class_a: Optional[float]
    class_b: Optional[float]
    basic: Optional[float]
    fdso: Optional[float]
    source: str
    is_estimated: bool


@dataclass(frozen=True)
class PolicyBreak:
    as_of: date
    title: str
    detail: str
    breaks_timeseries: bool
