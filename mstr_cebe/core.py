"""MSTR × BTC × mNAV × CEBE 核心計算.

實作規格書 §4 的所有公式。這個模組刻意不碰 I/O、不碰 API、不碰繪圖,
只做純函數,方便用 §6 的官方錨點驗證。

設計原則(對應規格書 §8 的陷阱):
  §8.1  任何 mNAV 數字都用 MNavReading 包裝,強制攜帶 variant + as_of。
  §8.2  Gross BPS 與 Net BPS 用不同的股數分母,型別上分開,不共用欄位。
  §8.3  優先股一律用 stated amount × 股數(清算優先權),不是發行價也不是市價。
  §8.4  三種「求償權總額」定義都保留,由 ClaimsBasis 明確選定。
  §8.6  STRE 為歐元計價,存 as-of 匯率,不用當期匯率回溯套用。
  §8.8  STRK 可轉換,價內時應排除在求償權之外。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import date
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

SATS_PER_BTC = 100_000_000

# STRK 每股可轉 0.1 股 MSTR,stated amount $100
# → 轉換價值 = 0.1 × MSTR 股價,價內門檻 = $100 / 0.1 = $1,000
STRK_CONVERSION_RATIO = 0.1
STRK_STATED_AMOUNT = 100.0
STRK_ITM_THRESHOLD_USD = STRK_STATED_AMOUNT / STRK_CONVERSION_RATIO  # $1,000


# ---------------------------------------------------------------------------
# 列舉
# ---------------------------------------------------------------------------

class MNavVariant(str, Enum):
    """五種 mNAV 變體(§4.1)。同一天同一股價,這五個數字可以落在 1.0x 兩側。"""
    BASIC = "basic"
    DILUTED = "diluted"
    ENTERPRISE = "enterprise"
    COMPANY = "company"          # Strategy 官方,2026-07-23 重新定義後 = price ÷ Net BPS
    CEBE = "cebe"


class PriceBasis(str, Enum):
    """反向映射的基準(§4.4)。

    ⚠️ GROSS 與 BASIC 都「不扣求償權」,差別只在分母,但結果差 7%:
        GROSS  = BTC NAV ÷ 423.838M assumed diluted  → $127.46 @ BTC 64,279
        BASIC  = BTC NAV ÷ 394.2M   basic shares     → $137.04 @ BTC 64,279
    規格書 §6.2 的 Gross BPS 是前者;§7.3 對照表的「Basic 基準 ~$137」是後者。
    §8.2 只點出 Gross/Net 兩個分母,實際上是**三個**。
    """
    GROSS = "gross"   # BTC NAV / assumed diluted shares(官方 Gross BPS)
    BASIC = "basic"   # BTC NAV / basic shares(§7.3 對照表用的基準)
    NET = "net"       # Strategy 官方 Net Reserve / Share(扣 OTM 債與優先股)
    CEBE = "cebe"     # cebetracker 框架,扣淨求償權後除以 basic shares


class ClaimsBasis(str, Enum):
    """§8.4 — 三個不同的「求償權總額」都在流通,定義差異不是錯誤。"""
    COMPANY = "company"          # 毛額含 STRE,不扣現金(債 + 優先股)
    COMPANY_NET_RESERVE = "company_net_reserve"  # 毛額扣 USD Reserve
    CEBETRACKER = "cebetracker"  # 扣現金與公司自持 STRC
    MNAV_COM = "mnav_com"        # 毛額但漏掉 STRE


class MoneyNess(str, Enum):
    IN_THE_MONEY = "itm"
    OUT_OF_THE_MONEY = "otm"
    UNKNOWN = "unknown"          # §5.3 缺口:轉換價未取得


class CashSource(str, Enum):
    """§5.5 — USD Reserve 與資產負債表現金**不是同一個東西**,不要混用。

    Strategy 官方 mNAV / EV 用 USD Reserve;第三方多用 balance-sheet cash。
    這個列舉存在的唯一理由就是強迫呼叫端明確選一個。
    """
    USD_RESERVE = "usd_reserve"
    BALANCE_SHEET = "balance_sheet"
    NONE = "none"


# ---------------------------------------------------------------------------
# 資料容器
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PreferredSeries:
    """單一系列優先股。金額一律為清算優先權(stated amount × 股數),見 §8.3。"""
    ticker: str
    liquidation_preference_usd: float
    shares: Optional[float] = None
    rank: int = 99                       # 1 = 最優先(STRF)
    convertible: bool = False
    currency: str = "USD"
    liquidation_preference_native: Optional[float] = None   # STRE 為 EUR
    fx_rate_as_of: Optional[float] = None                   # §8.6 存 as-of 匯率
    is_estimated: bool = False


@dataclass(frozen=True)
class ConvertibleSeries:
    """可轉債單一系列。§5.3 的轉換價多數未取得,用 Optional + confidence 誠實標記。"""
    name: str
    notional_usd: float
    coupon_pct: Optional[float] = None
    maturity_year: Optional[int] = None
    conversion_price_usd: Optional[float] = None
    confidence: str = "low"

    def moneyness(self, mstr_price: float) -> MoneyNess:
        if self.conversion_price_usd is None:
            return MoneyNess.UNKNOWN
        return (MoneyNess.IN_THE_MONEY if mstr_price >= self.conversion_price_usd
                else MoneyNess.OUT_OF_THE_MONEY)


@dataclass(frozen=True)
class CapitalStructure:
    """某一時點的資本結構快照(事件頻,不是日頻 —— 見 §3 設計要點)。"""
    as_of: date
    btc_held: float

    # 負債與優先股
    debt_notional_usd: float = 0.0
    preferreds: Tuple[PreferredSeries, ...] = ()
    convertibles: Tuple[ConvertibleSeries, ...] = ()

    # 現金類 —— §5.5:USD Reserve 與資產負債表現金不是同一個東西
    usd_reserve_usd: float = 0.0
    cash_and_equiv_usd: float = 0.0

    # §8.2 三個不同的股數分母,刻意分開三個欄位
    shares_basic: Optional[float] = None
    shares_fdso: Optional[float] = None              # → Net BPS
    shares_assumed_diluted: Optional[float] = None   # → Gross BPS

    annual_obligations_usd: Optional[float] = None
    source_tier: int = 1
    source_ref: str = ""
    is_estimated: bool = False
    note: str = ""

    # ---- 衍生量 ----
    @property
    def preferred_total_usd(self) -> float:
        return sum(p.liquidation_preference_usd for p in self.preferreds)

    @property
    def preferred_by_ticker(self) -> Dict[str, float]:
        return {p.ticker: p.liquidation_preference_usd for p in self.preferreds}

    def preferred_total_excluding(self, tickers: Sequence[str]) -> float:
        skip = {t.upper() for t in tickers}
        return sum(p.liquidation_preference_usd for p in self.preferreds
                   if p.ticker.upper() not in skip)

    def btc_nav_usd(self, btc_price: float) -> float:
        return self.btc_held * btc_price

    # ---- §8.8 價內/價外判定 ----
    def preferred_otm_usd(self, mstr_price: float) -> float:
        """排除價內的可轉換優先股(STRK)。價內時它會轉股,不是被償還。"""
        total = 0.0
        for p in self.preferreds:
            if p.convertible and mstr_price >= STRK_ITM_THRESHOLD_USD:
                continue
            total += p.liquidation_preference_usd
        return total

    def debt_otm_usd(self, mstr_price: float) -> float:
        """排除價內的可轉債。轉換價未知的系列**保守計入**求償權,並可用
        `debt_moneyness_unknown_usd` 查出有多少面額其實無法判定。"""
        if not self.convertibles:
            return self.debt_notional_usd
        total = 0.0
        for c in self.convertibles:
            if c.moneyness(mstr_price) is MoneyNess.IN_THE_MONEY:
                continue
            total += c.notional_usd
        return total

    def debt_moneyness_unknown_usd(self, mstr_price: float) -> float:
        return sum(c.notional_usd for c in self.convertibles
                   if c.moneyness(mstr_price) is MoneyNess.UNKNOWN)

    def cash_deduction(self, source: "CashSource") -> float:
        if source is CashSource.USD_RESERVE:
            return self.usd_reserve_usd
        if source is CashSource.BALANCE_SHEET:
            return self.cash_and_equiv_usd
        return 0.0


def market_cap(cs: CapitalStructure, mstr_price: float) -> float:
    """市值一律用 basic shares(§6.2 的 $38.368B 就是這樣算出來的)。"""
    if cs.shares_basic is None:
        raise ValueError(f"{cs.as_of}: shares_basic 未知")
    return mstr_price * cs.shares_basic


def enterprise_value(cs: CapitalStructure, mstr_price: float,
                     cash_source: "CashSource" = None) -> float:
    """EV = 市值 + 可轉債面額 + 優先股清算優先權 − 現金。

    cash_source 預設 USD_RESERVE,因為 §6.2 的官方 $55.710B 是這樣算的。
    """
    if cash_source is None:
        cash_source = CashSource.USD_RESERVE
    return (market_cap(cs, mstr_price)
            + cs.debt_notional_usd
            + cs.preferred_total_usd
            - cs.cash_deduction(cash_source))


# ---------------------------------------------------------------------------
# §8.1 — mNAV 讀數必須攜帶 variant + date
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MNavReading:
    value: float
    variant: MNavVariant
    as_of: date
    btc_price: float
    mstr_price: float
    note: str = ""

    def __str__(self) -> str:  # pragma: no cover - 便利輸出
        return f"{self.value:.3f}x ({self.variant.value}, {self.as_of.isoformat()})"

    @property
    def comparable_key(self) -> str:
        """§8.5:公司自訂 mNAV 在 2026-07-23 重新定義,前後不可比 ——
        用這個 key 分段,不同 key 的點不能連成一條線。"""
        if self.variant is not MNavVariant.COMPANY:
            return self.variant.value
        era = "pre" if self.as_of < COMPANY_MNAV_REDEFINITION else "post"
        return f"company::{era}"


COMPANY_MNAV_REDEFINITION = date(2026, 7, 23)   # §5.8 / §8.5 的定義斷點


# ---------------------------------------------------------------------------
# §4.2 — Strategy 官方公式(Tier 1,已驗證可重現)
# ---------------------------------------------------------------------------

def net_reserve_per_share(btc_price: float,
                          btc_held: float,
                          usd_reserve: float,
                          debt_otm_notional: float,
                          pref_otm_notional: float,
                          fdso: float) -> float:
    """Strategy 官方 Net Reserve / Share。

    'OTM'(out-of-the-money):價內的可轉債 / STRK 應排除在求償權之外,
    因為它們會轉成股權而不是被償還。
    """
    if fdso <= 0:
        raise ValueError("fdso must be positive")
    return (btc_held * btc_price
            + usd_reserve
            - debt_otm_notional
            - pref_otm_notional) / fdso


def net_reserve_per_share_from(cs: CapitalStructure,
                               btc_price: float,
                               mstr_price: float) -> float:
    """從 CapitalStructure 算 Net Reserve / Share,自動做 §8.8 的價內判定。"""
    if cs.shares_fdso is None:
        raise ValueError(f"{cs.as_of}: shares_fdso 未知,無法算 Net BPS")
    return net_reserve_per_share(
        btc_price=btc_price,
        btc_held=cs.btc_held,
        usd_reserve=cs.usd_reserve_usd,
        debt_otm_notional=cs.debt_otm_usd(mstr_price),
        pref_otm_notional=cs.preferred_otm_usd(mstr_price),
        fdso=cs.shares_fdso,
    )


# ---------------------------------------------------------------------------
# BPS(Bitcoin per share)—— §8.2 兩個不同分母
# ---------------------------------------------------------------------------

def gross_bps_sats(btc_held: float, shares_assumed_diluted: float) -> float:
    """Gross BPS。分母是 assumed diluted shares(~423.8M),**不是** FDSO。"""
    if shares_assumed_diluted <= 0:
        raise ValueError("shares_assumed_diluted must be positive")
    return btc_held / shares_assumed_diluted * SATS_PER_BTC


def gross_bps_usd(btc_held: float, shares_assumed_diluted: float,
                  btc_price: float) -> float:
    return gross_bps_sats(btc_held, shares_assumed_diluted) / SATS_PER_BTC * btc_price


def net_bps_sats(net_reserve_per_share_usd: float, btc_price: float) -> float:
    """Net BPS。分母是 FDSO(~398.2M),透過 net_reserve_per_share 隱含帶入。"""
    if btc_price <= 0:
        raise ValueError("btc_price must be positive")
    return net_reserve_per_share_usd / btc_price * SATS_PER_BTC


def phantom_growth_sats(cs: CapitalStructure, btc_price: float,
                        mstr_price: float) -> float:
    """Gross BPS 與 Net BPS 的每股落差(§1.2 第二點、§7.2.1 的面積)。"""
    if cs.shares_assumed_diluted is None:
        raise ValueError(f"{cs.as_of}: shares_assumed_diluted 未知")
    gross = gross_bps_sats(cs.btc_held, cs.shares_assumed_diluted)
    net = net_bps_sats(net_reserve_per_share_from(cs, btc_price, mstr_price), btc_price)
    return gross - net


# ---------------------------------------------------------------------------
# §4.3 — CEBE 框架(Tier 2,cebetracker.io)
# ---------------------------------------------------------------------------

def net_senior_claims_usd(cs: CapitalStructure,
                          basis: ClaimsBasis = ClaimsBasis.CEBETRACKER,
                          mstr_price: Optional[float] = None) -> float:
    """三種求償權定義(§8.4)。全部都對,只是扣除項不同。"""
    if basis is ClaimsBasis.COMPANY:
        debt = (cs.debt_otm_usd(mstr_price) if mstr_price is not None
                else cs.debt_notional_usd)
        pref = (cs.preferred_otm_usd(mstr_price) if mstr_price is not None
                else cs.preferred_total_usd)
        return debt + pref
    if basis is ClaimsBasis.COMPANY_NET_RESERVE:
        return net_senior_claims_usd(cs, ClaimsBasis.COMPANY, mstr_price) - cs.usd_reserve_usd
    if basis is ClaimsBasis.CEBETRACKER:
        return cs.debt_notional_usd + cs.preferred_total_usd - cs.cash_and_equiv_usd
    if basis is ClaimsBasis.MNAV_COM:
        # 毛額但漏掉 STRE —— 這是 mnav.com 的已知定義差異,刻意複製它
        return cs.debt_notional_usd + cs.preferred_total_excluding(["STRE"])
    raise ValueError(f"unknown claims basis: {basis}")


def net_senior_claims_btc(cs: CapitalStructure, btc_price: float,
                          basis: ClaimsBasis = ClaimsBasis.CEBETRACKER,
                          mstr_price: Optional[float] = None) -> float:
    if btc_price <= 0:
        raise ValueError("btc_price must be positive")
    return net_senior_claims_usd(cs, basis, mstr_price) / btc_price


def claims_pct(cs: CapitalStructure, btc_price: float,
               basis: ClaimsBasis = ClaimsBasis.CEBETRACKER,
               mstr_price: Optional[float] = None) -> float:
    return net_senior_claims_btc(cs, btc_price, basis, mstr_price) / cs.btc_held


def common_equity_pct(cs: CapitalStructure, btc_price: float,
                      basis: ClaimsBasis = ClaimsBasis.CEBETRACKER,
                      mstr_price: Optional[float] = None) -> float:
    return 1.0 - claims_pct(cs, btc_price, basis, mstr_price)


def cebe_btc_per_share(cs: CapitalStructure, btc_price: float,
                       basis: ClaimsBasis = ClaimsBasis.CEBETRACKER,
                       mstr_price: Optional[float] = None) -> float:
    if cs.shares_basic is None:
        raise ValueError(f"{cs.as_of}: shares_basic 未知,無法算 CEBE")
    claims = net_senior_claims_btc(cs, btc_price, basis, mstr_price)
    return (cs.btc_held - claims) / cs.shares_basic


def cebe_sats(cs: CapitalStructure, btc_price: float,
              basis: ClaimsBasis = ClaimsBasis.CEBETRACKER,
              mstr_price: Optional[float] = None) -> float:
    return cebe_btc_per_share(cs, btc_price, basis, mstr_price) * SATS_PER_BTC


def break_even_btc(cs: CapitalStructure,
                   basis: ClaimsBasis = ClaimsBasis.CEBETRACKER,
                   mstr_price: Optional[float] = None) -> float:
    """普通股歸零的 BTC 價格。§6.3 三種算法都對,只是求償權定義不同。"""
    return net_senior_claims_usd(cs, basis, mstr_price) / cs.btc_held


def break_even_all_bases(cs: CapitalStructure,
                         mstr_price: Optional[float] = None) -> Dict[str, float]:
    """§6.3 要求:系統不能只顯示一個 break-even。"""
    return {b.value: break_even_btc(cs, b, mstr_price) for b in ClaimsBasis}


def amplification(cs: CapitalStructure, btc_price: float,
                  mstr_price: float) -> float:
    """槓桿放大倍數 = BTC NAV ÷ 可分配給普通股的淨值(§6.2)。"""
    if cs.shares_fdso is None:
        raise ValueError(f"{cs.as_of}: shares_fdso 未知")
    net_total = net_reserve_per_share_from(cs, btc_price, mstr_price) * cs.shares_fdso
    if net_total == 0:
        return math.inf
    return cs.btc_nav_usd(btc_price) / net_total


# ---------------------------------------------------------------------------
# §4.1 — 五種 mNAV
# ---------------------------------------------------------------------------

def mnav(cs: CapitalStructure, btc_price: float, mstr_price: float,
         variant: MNavVariant,
         claims_basis: ClaimsBasis = ClaimsBasis.CEBETRACKER,
         cash_source: CashSource = CashSource.BALANCE_SHEET) -> MNavReading:
    nav = cs.btc_nav_usd(btc_price)
    if nav <= 0:
        raise ValueError("BTC NAV must be positive")
    note = ""

    if variant is MNavVariant.BASIC:
        _require(cs, "shares_basic")
        value = (mstr_price * cs.shares_basic) / nav
        note = "分子分母都不含優先股 —— 數學上完全看不到優先股(§1.2)"

    elif variant is MNavVariant.DILUTED:
        _require(cs, "shares_fdso")
        value = (mstr_price * cs.shares_fdso) / nav

    elif variant is MNavVariant.ENTERPRISE:
        value = enterprise_value(cs, mstr_price, cash_source) / nav
        note = f"cash source = {cash_source.value}"

    elif variant is MNavVariant.COMPANY:
        value = mstr_price / net_reserve_per_share_from(cs, btc_price, mstr_price)
        if cs.as_of < COMPANY_MNAV_REDEFINITION:
            note = ("⚠️ 2026-07-23 前公司定義不同,官方明言 not comparable。"
                    "不可與此日之後的讀數連成一條線(§8.5)")

    elif variant is MNavVariant.CEBE:
        per_share_usd = cebe_btc_per_share(cs, btc_price, claims_basis, mstr_price) * btc_price
        value = mstr_price / per_share_usd
        note = f"claims basis = {claims_basis.value}"

    else:
        raise ValueError(f"unknown variant: {variant}")

    return MNavReading(value=value, variant=variant, as_of=cs.as_of,
                       btc_price=btc_price, mstr_price=mstr_price, note=note)


def all_mnavs(cs: CapitalStructure, btc_price: float, mstr_price: float,
              claims_basis: ClaimsBasis = ClaimsBasis.CEBETRACKER,
              cash_source: CashSource = CashSource.BALANCE_SHEET
              ) -> Dict[str, MNavReading]:
    """§4.1 要求全部都算,不能只算一種。算不出來的變體跳過(缺股數等)。"""
    out: Dict[str, MNavReading] = {}
    for v in MNavVariant:
        try:
            out[v.value] = mnav(cs, btc_price, mstr_price, v, claims_basis, cash_source)
        except ValueError:
            continue
    return out


def _require(cs: CapitalStructure, attr: str) -> None:
    if getattr(cs, attr) is None:
        raise ValueError(f"{cs.as_of}: {attr} 未知")


# ---------------------------------------------------------------------------
# §4.4 — 反向映射(使用者要的核心功能)
# ---------------------------------------------------------------------------

def implied_mstr_price(cs: CapitalStructure, btc_price: float,
                       target_mnav: float,
                       basis: PriceBasis = PriceBasis.NET,
                       claims_basis: ClaimsBasis = ClaimsBasis.CEBETRACKER,
                       moneyness_price: Optional[float] = None) -> float:
    """在該 BTC 價格與該資本結構下,達到 target_mnav 所需的 MSTR 股價。

    moneyness_price:用來做 §8.8 價內判定的股價。預設用 target 自身迭代收斂,
    因為「要多少股價」跟「那個股價下 STRK 是否價內」互相依賴。
    """
    if basis is PriceBasis.GROSS:
        _require(cs, "shares_assumed_diluted")
        per_share = cs.btc_held * btc_price / cs.shares_assumed_diluted
        return target_mnav * per_share

    if basis is PriceBasis.BASIC:
        _require(cs, "shares_basic")
        per_share = cs.btc_held * btc_price / cs.shares_basic
        return target_mnav * per_share

    if basis is PriceBasis.CEBE:
        px = moneyness_price if moneyness_price is not None else 0.0
        per_share = cebe_btc_per_share(cs, btc_price, claims_basis, px) * btc_price
        return target_mnav * per_share

    if basis is PriceBasis.NET:
        # 不動點迭代:價內判定依賴結果股價
        px = moneyness_price if moneyness_price is not None else 0.0
        for _ in range(50):
            per_share = net_reserve_per_share_from(cs, btc_price, px)
            nxt = target_mnav * per_share
            if abs(nxt - px) < 1e-9:
                return nxt
            px = nxt
        return px

    raise ValueError(f"unknown basis: {basis}")


def implied_price_table(cs: CapitalStructure, btc_price: float,
                        targets: Sequence[float] = (1.0, 1.25, 1.5, 2.0, 3.0),
                        bases: Sequence[PriceBasis] = tuple(PriceBasis),
                        claims_basis: ClaimsBasis = ClaimsBasis.CEBETRACKER
                        ) -> List[Dict[str, object]]:
    """§7.3 的對照表。"""
    rows: List[Dict[str, object]] = []
    for t in targets:
        row: Dict[str, object] = {"target_mnav": t}
        for b in bases:
            try:
                row[b.value] = implied_mstr_price(cs, btc_price, t, b, claims_basis)
            except ValueError:
                row[b.value] = None
        rows.append(row)
    return rows


def implied_btc_price(cs: CapitalStructure, mstr_price: float,
                      target_mnav: float,
                      basis: PriceBasis = PriceBasis.NET) -> float:
    """反過來問:MSTR 在這個股價,要什麼 BTC 價格才會是 target_mnav?

    NET / CEBE 基準下 per_share 對 btc_price 是仿射的,可解析解;
    先算係數再解一次方程,不用數值搜尋。
    """
    if basis in (PriceBasis.GROSS, PriceBasis.BASIC):
        attr = ("shares_assumed_diluted" if basis is PriceBasis.GROSS
                else "shares_basic")
        _require(cs, attr)
        # mstr = t × btc_held × p / shares  →  p = mstr × shares / (t × btc_held)
        return mstr_price * getattr(cs, attr) / (target_mnav * cs.btc_held)

    if basis is PriceBasis.NET:
        _require(cs, "shares_fdso")
        slope = cs.btc_held / cs.shares_fdso
        intercept = (cs.usd_reserve_usd
                     - cs.debt_otm_usd(mstr_price)
                     - cs.preferred_otm_usd(mstr_price)) / cs.shares_fdso
    elif basis is PriceBasis.CEBE:
        _require(cs, "shares_basic")
        slope = cs.btc_held / cs.shares_basic
        intercept = -net_senior_claims_usd(cs, ClaimsBasis.CEBETRACKER,
                                           mstr_price) / cs.shares_basic
    else:
        raise ValueError(f"unknown basis: {basis}")

    # mstr = t × (slope × p + intercept)
    return (mstr_price / target_mnav - intercept) / slope


# ---------------------------------------------------------------------------
# §4.5 — 融資來源歸因(phantom growth 量化)
# ---------------------------------------------------------------------------
CEBE_EFFECT_BY_FUNDING = {
    "preferred_atm": "neutral",   # 新 BTC 完全被新求償權抵銷,但 BPS 上升 → phantom growth
    "common_atm": "accretive_if_above_1x",
    "convert": "temporary_claim",
    "cash": "neutral",
    "btc_sale": "dilutive",
    "pref_buyback_discount": "accretive",
    "mixed": "unknown",
}


def classify_funding(funding_source: str,
                     issue_mnav_net: Optional[float] = None) -> str:
    """§4.5 的歸因規則。普通股增發要看發行價是否高於 1.0x net mNAV。"""
    effect = CEBE_EFFECT_BY_FUNDING.get(funding_source, "unknown")
    if effect == "accretive_if_above_1x":
        if issue_mnav_net is None:
            return "unknown"
        return "accretive" if issue_mnav_net > 1.0 else "dilutive"
    return effect


# ---------------------------------------------------------------------------
# §6.2 — BTC ARR 門檻
# ---------------------------------------------------------------------------

def btc_arr_breakeven(annual_obligations_usd: float, btc_nav_usd: float) -> float:
    """BTC 需要多少年化報酬才能覆蓋固定義務(利息 + 優先股股利)。回傳小數。"""
    if btc_nav_usd <= 0:
        raise ValueError("btc_nav_usd must be positive")
    return annual_obligations_usd / btc_nav_usd


# ---------------------------------------------------------------------------
# §1.3 — 對數分解(basic mNAV 的變化歸因)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LogDecomposition:
    start: date
    end: date
    mnav_start: float
    mnav_end: float
    price_ratio: float
    btc_ratio: float
    shares_ratio: float
    log_price: float
    log_btc: float
    log_shares: float
    log_total: float
    reconstructed_mnav: float
    residual: float

    def as_rows(self) -> List[Tuple[str, float, float]]:
        return [
            ("MSTR 股價", self.price_ratio, self.log_price),
            ("BTC 價格", self.btc_ratio, self.log_btc),
            ("股數稀釋", self.shares_ratio, self.log_shares),
        ]


def decompose_basic_mnav(start: date, end: date,
                         mstr_price_start: float, mstr_price_end: float,
                         btc_price_start: float, btc_price_end: float,
                         btc_held_start: float, btc_held_end: float,
                         shares_start: float, shares_end: float
                         ) -> LogDecomposition:
    """把 basic mNAV 的變化拆成「股價 / BTC 價 / BTC-per-share」三個乘法項。

    basic mNAV = price / (BPS × btc_price),其中 BPS = btc_held / shares。
    所以 ratio(mNAV) = ratio(price) ÷ ratio(btc_price) ÷ ratio(BPS)。
    """
    bps_start = btc_held_start / shares_start
    bps_end = btc_held_end / shares_end
    mnav_start = mstr_price_start / (bps_start * btc_price_start)
    mnav_end = mstr_price_end / (bps_end * btc_price_end)

    price_ratio = mstr_price_end / mstr_price_start
    btc_ratio = btc_price_start / btc_price_end      # BTC 下跌 → 墊高 mNAV
    bps_ratio = bps_start / bps_end                  # BPS 上升 → 壓低 mNAV

    total = price_ratio * btc_ratio * bps_ratio
    return LogDecomposition(
        start=start, end=end,
        mnav_start=mnav_start, mnav_end=mnav_end,
        price_ratio=price_ratio, btc_ratio=btc_ratio, shares_ratio=bps_ratio,
        log_price=math.log(price_ratio),
        log_btc=math.log(btc_ratio),
        log_shares=math.log(bps_ratio),
        log_total=math.log(total),
        reconstructed_mnav=mnav_start * total,
        residual=mnav_start * total - mnav_end,
    )


# ---------------------------------------------------------------------------
# 便利:forward-fill 資本結構(§3 設計要點)
# ---------------------------------------------------------------------------

def as_of_structure(timeline: Sequence[CapitalStructure],
                    on: date) -> CapitalStructure:
    """取 `on` 當天有效的資本結構(最近一次申報),並在 note 標明延續距離。

    回傳物件的 as_of 會改成查詢日,但 `source_ref` / `note` 保留原申報資訊,
    讓圖上能區分「真實觀測」與「延續假設」。
    """
    ordered = sorted(timeline, key=lambda c: c.as_of)
    chosen: Optional[CapitalStructure] = None
    for cs in ordered:
        if cs.as_of <= on:
            chosen = cs
        else:
            break
    if chosen is None:
        raise ValueError(f"no capital structure on or before {on}")
    if chosen.as_of == on:
        return chosen
    stale_days = (on - chosen.as_of).days
    extra = f"forward-filled {stale_days}d from {chosen.as_of.isoformat()}"
    note = f"{chosen.note}; {extra}" if chosen.note else extra
    return replace(chosen, as_of=on, note=note)


def observation_dates(timeline: Sequence[CapitalStructure]) -> List[date]:
    """圖上要標出的申報日(§3)。"""
    return sorted(cs.as_of for cs in timeline)
