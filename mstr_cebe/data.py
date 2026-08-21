"""規格書 §5 的人工整理資料 + §6 的驗證錨點。

**這個模組是整個專案的事實來源(source of truth)。**
每一筆都帶 tier 與 source_ref;推估值一律 is_estimated=True。
不要在這裡放推論或分析結論,只放可追溯到申報文件/新聞稿的數字。

金額單位一律 USD(絕對值,不是千元)。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

from .core import (
    CapitalStructure,
    ConvertibleSeries,
    PreferredSeries,
)

K = 1_000.0
M = 1_000_000.0
B = 1_000_000_000.0


# ===========================================================================
# §5.1 優先股發行帳(IPO,Tier 1)
# 關鍵區分:IPO 發行價 ≠ 清算優先權(stated amount,一律 100/股)
# ===========================================================================

@dataclass(frozen=True)
class PreferredIPO:
    ticker: str
    name: str
    pricing_date: date
    ipo_shares: float
    offer_price: float          # 發行價 —— **不要拿來建模**
    stated_amount: float        # 清算優先權 —— 建模用這個
    currency: str
    ipo_liquidation_pref: float
    net_proceeds: float
    dividend_rate_pct: Optional[float]   # None = 變動利率
    rank: int                            # 1 = 最優先
    convertible: bool
    note: str = ""


PREFERRED_IPOS: Tuple[PreferredIPO, ...] = (
    PreferredIPO("STRK", "Strike", date(2025, 1, 30), 7_300_000, 80.0, 100.0, "USD",
                 730 * M, 563.4 * M, 8.00, rank=3, convertible=True,
                 note="可轉換 0.1 MSTR/股"),
    PreferredIPO("STRF", "Strife", date(2025, 3, 20), 8_500_000, 85.0, 100.0, "USD",
                 850 * M, 711.2 * M, 10.00, rank=1, convertible=False,
                 note="累積型,最優先"),
    PreferredIPO("STRD", "Stride", date(2025, 6, 5), 11_764_700, 85.0, 100.0, "USD",
                 1_176 * M, 979.7 * M, 10.00, rank=4, convertible=False,
                 note="非累積、非強制,最劣後"),
    PreferredIPO("STRC", "Stretch", date(2025, 7, 24), 28_011_111, 90.0, 100.0, "USD",
                 2_801 * M, 2_474 * M, None, rank=2, convertible=False,
                 note="變動利率;2025 年全美最大 IPO"),
    PreferredIPO("STRE", "Stream", date(2025, 11, 6), 7_750_000, 80.0, 100.0, "EUR",
                 775 * M, 608.8 * M, 10.00, rank=5, convertible=False,
                 note="歐元計價,LuxSE;此列金額為 EUR"),
)

# 清償順位:STRF(最優先)→ STRC → STRK → STRD(最劣後)→ 普通股
# 可轉債在所有優先股之上(rank 0)
SENIORITY_RANK: Dict[str, int] = {
    "CONVERTS": 0, "STRF": 1, "STRC": 2, "STRK": 3, "STRD": 4, "STRE": 5,
}
# ⚠️ STRE 的相對順位規格書未明列,此處置於最劣後為推估
SENIORITY_CONFIDENCE = {"STRE": "low — 規格書未明列 STRE 順位,暫置最劣後"}

# §5.1 / §8.7 STRC 是變動利率,建模不能寫死
STRC_DIVIDEND_SCHEDULE: Tuple[Tuple[date, float], ...] = (
    (date(2025, 7, 24), 9.00),
    (date(2026, 6, 1), 11.50),
    (date(2026, 8, 1), 12.00),   # 「2026-08 起的記錄日」
)
STRC_PAYMENT_FREQUENCY_CHANGE = (date(2026, 6, 8), "monthly → semi-monthly")


def strc_dividend_rate(on: date) -> float:
    """§8.7 —— 年度義務不能寫死。"""
    rate = STRC_DIVIDEND_SCHEDULE[0][1]
    for eff, r in STRC_DIVIDEND_SCHEDULE:
        if on >= eff:
            rate = r
    return rate


# ===========================================================================
# §5.2 季末優先股餘額(清算優先權,USD)
# ===========================================================================

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


PREFERRED_BALANCES: Tuple[PreferredBalance, ...] = (
    PreferredBalance(date(2024, 12, 31), 0, 0, 0, 0, 0, 0, 0,
                     source="—(優先股時代之前)", is_estimated=False),
    PreferredBalance(date(2025, 3, 31), 730_000 * K, 850_000 * K, 0, 0, 0,
                     1_580_000 * K, 15_800 * K,
                     source="IPO 加總推估", is_estimated=True),
    PreferredBalance(date(2025, 6, 30), 900_000 * K, 950_000 * K, 1_176_000 * K, 0, 0,
                     3_026_000 * K, 30_300 * K,
                     source="含 ATM 推估(STRD 為 IPO 實數)", is_estimated=True),
    PreferredBalance(date(2025, 9, 30), 1_100_000 * K, 1_150_000 * K, 1_250_000 * K,
                     2_900_000 * K, 0, 6_400_000 * K, 64_000 * K,
                     source="含 ATM 推估", is_estimated=True),
    PreferredBalance(date(2025, 12, 31), 1_364_000 * K, 1_184_000 * K, 1_266_000 * K,
                     3_400_000 * K, 818_000 * K,
                     8_032_324 * K, 78_183 * K,
                     source="10-K / 8-K(總計與總股數為申報實數,分系列為推估)",
                     is_estimated=True),
    PreferredBalance(date(2026, 3, 31), None, None, None, 5_024_700 * K, None,
                     10_005_000 * K, None,
                     source="Q1 10-Q(總計約 $10.005B,分系列僅 STRC 已知)",
                     is_estimated=False),
    PreferredBalance(date(2026, 6, 30),
                     1_402_074 * K, 1_283_969 * K, 1_402_422 * K, 10_489_471 * K,
                     884_120 * K,          # 反解使總計吻合申報值 15,462,056
                     15_462_056 * K, 153_529 * K,
                     source="Q2 10-Q(全部為申報實數)", is_estimated=False,
                     stre_eur=775_000 * K, fx_eur_usd=884_120 / 775_000,
                     shares_by_ticker={"STRK": 14_020_744, "STRF": 12_839_689,
                                       "STRD": 14_024_221, "STRC": 104_894_705,
                                       "STRE": 7_750_000}),
    PreferredBalance(date(2026, 7, 24), None, None, None, 10_460_000 * K, None,
                     None, None,
                     source="8-K(STRC 回購後)", is_estimated=True),
)

# §5.2 10-Q 原文(2026-06-30),保留以便追溯
TENQ_QUOTE_2026Q2 = (
    "Series A Perpetual Preferred Stock … 153,529 and 78,183 issued and "
    "outstanding at June 30, 2026 and December 31, 2025 … redemption value and "
    "liquidation preference of $15,462,056 and $8,032,324 …"
)

# §5.2 STRC 成長軌跡 —— 單一系列佔總優先股 2/3
STRC_TRAJECTORY: Tuple[Tuple[date, float, Optional[float]], ...] = (
    (date(2025, 7, 24), 2_801 * M, 28_011_111),
    (date(2025, 12, 31), 3_400 * M, None),
    (date(2026, 3, 31), 5_024.7 * M, 50_247_000),
    (date(2026, 6, 30), 10_489.5 * M, 104_894_705),
)
STRC_YTD_2026_RAISE = 7.53 * B     # Q2 2026 8-K:成長 254%
STRC_BELOW_PAR_EVENT = (date(2026, 6, 17), 89.0, "跌到 $89,低於面額 11%")


# ===========================================================================
# §5.3 可轉債
# ⚠️ 這是本專案最大的資料缺口(附錄評為信心度「低」)。
#    各系列轉換價 / 到期日需從某一期 10-Q 債務附註人工抄一次。
# ===========================================================================

CONVERTIBLE_TOTALS: Tuple[Tuple[date, float, str], ...] = (
    (date(2025, 12, 31), 8.21 * B, "2025 年底"),
    (date(2026, 5, 31), 6.71 * B, "回購 $1.50B 的 2029 年零息可轉債"),
    (date(2026, 8, 13), 6.754 * B, "FWP notional"),
)

CONVERTIBLES_2026: Tuple[ConvertibleSeries, ...] = (
    ConvertibleSeries("0.625% due 2028", 1.01 * B, 0.625, 2028,
                      conversion_price_usd=None, confidence="low"),
    ConvertibleSeries("0% due 2030", 0.0, 0.0, 2030,
                      conversion_price_usd=None, confidence="low"),
    ConvertibleSeries("0.875% due 2031", 603.75 * M, 0.875, 2031,
                      conversion_price_usd=None, confidence="low"),
    ConvertibleSeries("2.25% due 2032", 800 * M, 2.25, 2032,
                      conversion_price_usd=None, confidence="low"),
    ConvertibleSeries("0% due 2029", 0.0, 0.0, 2029,
                      conversion_price_usd=None, confidence="low"),
    ConvertibleSeries("2027 notes", 1.7 * B, None, 2027,
                      conversion_price_usd=143.25, confidence="medium"),
)
# ⚠️ 上表面額加總 ≠ $6.754B(多個系列面額未取得,以 0 佔位)。
#    因此系統的求償權一律用 CONVERTIBLE_TOTALS 的總額,
#    CONVERTIBLES_2026 只用於 moneyness 情境分析。
CONVERTIBLE_SERIES_GAP_NOTE = (
    "各系列面額/轉換價不完整;總額用 CONVERTIBLE_TOTALS,"
    "分系列僅供 in/out-of-the-money 情境分析(§5.3 缺口)"
)

# cebetracker:若 MSTR 回到 $143.25 以上,$1.7B 的 2027 notes 轉股,
# break-even 會從 $23,270 降到 $20,887
CONVERT_2027_SCENARIO = {
    "conversion_price": 143.25,
    "notional": 1.7 * B,
    "break_even_before": 23_270.0,
    "break_even_after": 20_887.0,
    "source": "cebetracker (Tier 2)",
}


# ===========================================================================
# §5.4 股數(已反映 2024-08-07 的 10-for-1 分割)
# ===========================================================================

@dataclass(frozen=True)
class ShareCount:
    as_of: date
    class_a: Optional[float]
    class_b: Optional[float]
    basic: Optional[float]
    fdso: Optional[float]
    source: str
    is_estimated: bool


SHARE_COUNTS: Tuple[ShareCount, ...] = (
    ShareCount(date(2024, 12, 31), 248 * M, None, 248 * M, None, "推估", True),
    ShareCount(date(2025, 12, 31), 292.4 * M, None, 292.4 * M, None, "10-K", False),
    ShareCount(date(2026, 6, 30), 351.96 * M, 19.64 * M, 371.6 * M, None, "10-Q", False),
    ShareCount(date(2026, 7, 24), 364.6 * M, 19.64 * M, 384.2 * M, None, "8-K", False),
    ShareCount(date(2026, 8, 10), None, None, 394_204_253, 398_220_309,
               "FWP 反解(basic 由市值 $38.368B ÷ $97.33 反解)", True),
)

WEIGHTED_AVG_DILUTED: Tuple[Tuple[str, float], ...] = (
    ("FY2024", 192.5 * M), ("FY2025", 277.7 * M), ("Q1 2026", 333.9 * M),
)

SPLIT_DATE = date(2024, 8, 7)
SPLIT_RATIO = 10
# ⚠️ $543 是 2024-11-21 的**盤中高點**,不是收盤價(收盤 $397.28,已實測確認)。
#    做 split 檢查時必須比對 high 欄位,比 close 會誤判資料源有問題。
SPLIT_CHECK = (date(2024, 11, 21), 543.0, "high",
               "ATH $543 為盤中高點(已調整);收盤為 $397.28;若見 $5,430 代表未調整")
ATH_CLOSE_2024_11_21 = 397.28

FINDING_ATH_IS_INTRADAY = {
    "where": "§5.10 與 §1.3,起點 MSTR = $543",
    "problem": (
        "$543 是 2024-11-21 的盤中高點;當日收盤為 $397.28(Yahoo 實測)。"
        "§1.3 的對數分解把這個盤中高點與終點的**收盤價** $97.33 相比,"
        "屬於混用基準。"
    ),
    "impact": (
            "以收盤對收盤重算:397.28 → 97.33 = ×0.245(log −1.406),"
            "而非規格書的 ×0.179(log −1.72)。起點 basic mNAV 也應從 3.67x "
            "降為約 2.69x。**結論方向不變**(溢價收縮仍是主因、BTC 下跌仍墊高 mNAV、"
            "稀釋仍是次要),但壓縮幅度被高估了約 37%。"
    ),
    "resolution": "market_daily 存完整 OHLC;分解函數預設用 close,盤中高點另存欄位。",
}


# ===========================================================================
# §5.5 USD Reserve(非 GAAP,只在 8-K / 新聞稿揭露)
# ⚠️ 與資產負債表 cash & equivalents 不是同一個東西
# ===========================================================================

USD_RESERVE: Tuple[Tuple[date, float], ...] = (
    (date(2026, 6, 29), 2.55 * B),
    (date(2026, 7, 26), 3.75 * B),
    (date(2026, 8, 9), 4.65 * B),
    (date(2026, 8, 16), 4.80 * B),
)
BALANCE_SHEET_CASH: Tuple[Tuple[date, float], ...] = (
    (date(2026, 6, 30), 2.45 * B),
)
USD_RESERVE_FLOOR = 1.25 * B      # Digital Credit Capital Framework 下限


def usd_reserve_as_of(on: date) -> float:
    """USD Reserve 只有四個時點,forward-fill;啟動日之前為 0。"""
    value = 0.0
    for d, v in USD_RESERVE:
        if on >= d:
            value = v
    return value


# ===========================================================================
# §5.6 年度固定義務(利息 + 優先股股利)
# ===========================================================================

ANNUAL_OBLIGATIONS: Tuple[Tuple[date, float, int, str], ...] = (
    (date(2025, 11, 1), 775 * M, 3, "CEO Phong Le 受訪,~$750–800M 取中點"),
    (date(2026, 8, 13), 1.736 * B, 1, "FWP"),
)


def annual_obligations_as_of(on: date) -> Tuple[float, int]:
    value, tier = 0.0, 3
    for d, v, t, _ in ANNUAL_OBLIGATIONS:
        if on >= d:
            value, tier = v, t
    return value, tier


# ===========================================================================
# §5.7 BTC 持有量與重大事件
# ===========================================================================

BTC_HELD: Tuple[Tuple[date, float, str], ...] = (
    (date(2024, 9, 30), 252_220, ""),
    (date(2024, 12, 31), 446_400, ""),
    (date(2025, 3, 31), 550_000, ""),
    (date(2026, 1, 31), 709_715, ""),
    (date(2026, 4, 12), 780_897, ""),
    (date(2026, 7, 5), 843_775, ""),
    (date(2026, 8, 10), 840_447, "FWP"),
    (date(2026, 8, 16), 842_137, "mnav.com (Tier 2)"),
)

# ---------------------------------------------------------------------------
# §5.7b — SEC 8-K 逐週 BTC 持有量(2026-08-18 建置期追加,免費、免 key、Tier 1)
#
# ⚠️ 更正:先前的建置紀錄一度誤判「2025-03-24 之後 Strategy 把 BTC 持有量從
# 8-K 移到官網 dashboard,免費資料源只剩季度」。那個結論來自一次範圍過窄的
# SEC full-text-search(只搜尋 "bitcoins for approximately" 這句 prose 用語),
# 沒發現公司只是換了揭露格式 —— 數字始終都在 8-K 裡,從未間斷:
#   - 2024-09 ~ 2025-03-24:prose 格式,"As of {date} ... held an aggregate
#     of approximately {N} bitcoins"
#   - 2025-03-31 起:改成結構化的「BTC Update」表格
#
# 用 mstr_cebe/fetch_8k_btc.py 重新抓取、解析兩種格式並合併,得到 90 個真實
# 觀測點,平均間隔 8.7 天(基本上就是逐週),最長間隔從原本的 306 天壓到 52
# 天。所有「下降」都對應已知的真實賣幣事件(2026 年 5 月底起首次賣幣、
# 8 月為回購 STRC 賣幣),沒有無法解釋的倒退。
#
# 這組資料取代原本的 BTC_HELD 表格(該表仍保留,供交叉核對用)。
# ---------------------------------------------------------------------------
WEEKLY_BTC_HELD: Tuple[Tuple[date, int], ...] = (
    (date(2024, 9, 12), 244800),
    (date(2024, 9, 19), 252220),
    (date(2024, 11, 10), 279420),
    (date(2024, 11, 17), 331200),
    (date(2024, 11, 24), 386700),
    (date(2024, 12, 1), 402100),
    (date(2024, 12, 8), 423650),
    (date(2024, 12, 15), 439000),
    (date(2024, 12, 22), 444262),
    (date(2024, 12, 29), 446400),
    (date(2025, 1, 5), 447470),
    (date(2025, 1, 12), 450000),
    (date(2025, 1, 20), 461000),
    (date(2025, 1, 26), 471107),
    (date(2025, 2, 2), 471107),
    (date(2025, 2, 9), 478740),
    (date(2025, 2, 17), 478740),
    (date(2025, 2, 23), 499096),
    (date(2025, 3, 2), 499096),
    (date(2025, 3, 9), 499096),
    (date(2025, 3, 16), 499226),
    (date(2025, 3, 23), 506137),
    (date(2025, 3, 30), 528185),
    (date(2025, 4, 13), 531644),
    (date(2025, 4, 20), 538200),
    (date(2025, 4, 27), 553555),
    (date(2025, 5, 4), 555450),
    (date(2025, 5, 11), 568840),
    (date(2025, 5, 18), 576230),
    (date(2025, 6, 1), 580955),
    (date(2025, 6, 8), 582000),
    (date(2025, 6, 15), 592100),
    (date(2025, 6, 22), 592345),
    (date(2025, 6, 29), 597325),
    (date(2025, 6, 30), 597325),
    (date(2025, 7, 6), 597325),
    (date(2025, 7, 13), 601550),
    (date(2025, 7, 20), 607770),
    (date(2025, 7, 27), 607770),
    (date(2025, 8, 3), 628791),
    (date(2025, 8, 10), 628946),
    (date(2025, 8, 17), 629376),
    (date(2025, 8, 24), 632457),
    (date(2025, 9, 1), 636505),
    (date(2025, 9, 7), 638460),
    (date(2025, 9, 14), 638985),
    (date(2025, 9, 21), 639835),
    (date(2025, 9, 28), 640031),
    (date(2025, 10, 19), 640418),
    (date(2025, 10, 26), 640808),
    (date(2025, 11, 2), 641205),
    (date(2025, 11, 9), 641692),
    (date(2025, 11, 16), 649870),
    (date(2025, 12, 7), 660624),
    (date(2025, 12, 14), 671268),
    (date(2025, 12, 21), 671268),
    (date(2025, 12, 28), 672497),
    (date(2025, 12, 31), 672500),
    (date(2026, 1, 4), 673783),
    (date(2026, 1, 11), 687410),
    (date(2026, 1, 19), 709715),
    (date(2026, 1, 25), 712647),
    (date(2026, 2, 1), 713502),
    (date(2026, 2, 8), 714644),
    (date(2026, 2, 16), 717131),
    (date(2026, 2, 22), 717722),
    (date(2026, 3, 1), 720737),
    (date(2026, 3, 15), 761068),
    (date(2026, 3, 22), 762099),
    (date(2026, 3, 31), 762099),
    (date(2026, 4, 5), 766970),
    (date(2026, 4, 12), 780897),
    (date(2026, 4, 19), 815061),
    (date(2026, 4, 26), 818334),
    (date(2026, 5, 3), 818334),
    (date(2026, 5, 10), 818869),
    (date(2026, 5, 17), 843738),
    (date(2026, 5, 31), 843706),
    (date(2026, 6, 7), 845256),
    (date(2026, 6, 14), 846842),
    (date(2026, 6, 21), 847363),
    (date(2026, 6, 28), 847363),
    (date(2026, 6, 30), 846000),
    (date(2026, 7, 5), 843775),
    (date(2026, 7, 12), 843775),
    (date(2026, 7, 19), 843775),
    (date(2026, 7, 26), 843775),
    (date(2026, 8, 2), 842138),
    (date(2026, 8, 9), 840447),
    (date(2026, 8, 16), 840447),
)

# ---------------------------------------------------------------------------
# §5.7c — SEC XBRL 季度錨點(debt / cash / 股數;BTC 持有量已被上面的週資料取代)
# 端點:https://data.sec.gov/api/xbrl/companyconcept/CIK0001050446/us-gaap/{tag}.json
# 抓取日:2026-08-18。數字為 10-K/10-Q 申報的期末(instant)值。
# ---------------------------------------------------------------------------

# us-gaap:CryptoAssetNumberOfUnits — 期末 BTC 持有量(ASU 2023-08 公允價值法)
# ⚠️ 2024-12-31 這裡是 447,470,與上面 BTC_HELD 表的 446,400 差 1,070 顆(0.24%)——
#    上面那筆來自 8-K 初次揭露,這筆來自 FY2025 10-K 的比較期重編數字,更權威。
#    兩者並存,插值時使用這裡的 XBRL 值。
XBRL_BTC_HELD: Tuple[Tuple[date, float], ...] = (
    (date(2024, 12, 31), 447_470),
    (date(2025, 12, 31), 672_500),   # 填補 BTC_HELD 表最大的空白
    (date(2026, 3, 31), 762_099),
    (date(2026, 6, 30), 846_000),    # 注意:高於 7/5 的 843,775 —— 5 月底至 8 月的賣幣是真的
)

# us-gaap:LongTermDebtNoncurrent — 每季,取代原本只有 3 個點的 CONVERTIBLE_TOTALS
XBRL_DEBT: Tuple[Tuple[date, float], ...] = (
    (date(2024, 3, 31), 3.559e9), (date(2024, 6, 30), 3.703e9),
    (date(2024, 9, 30), 4.212e9), (date(2024, 12, 31), 7.191e9),
    (date(2025, 3, 31), 8.140e9), (date(2025, 6, 30), 8.162e9),
    (date(2025, 9, 30), 8.174e9), (date(2025, 12, 31), 8.159e9),
    (date(2026, 3, 31), 8.165e9), (date(2026, 6, 30), 6.670e9),
)

# us-gaap:CashAndCashEquivalentsAtCarryingValue — 每季,資產負債表現金(非 USD Reserve)
XBRL_CASH: Tuple[Tuple[date, float], ...] = (
    (date(2024, 3, 31), 0.081e9), (date(2024, 6, 30), 0.067e9),
    (date(2024, 9, 30), 0.046e9), (date(2024, 12, 31), 0.038e9),
    (date(2025, 3, 31), 0.060e9), (date(2025, 6, 30), 0.050e9),
    (date(2025, 9, 30), 0.054e9), (date(2025, 12, 31), 2.301e9),
    (date(2026, 3, 31), 2.207e9), (date(2026, 6, 30), 1.712e9),
)

# us-gaap:WeightedAverageNumberOfSharesOutstandingBasic — 單季(非 YTD)加權平均。
# 拿來補期末在外股數(SHARE_COUNTS)之間的中繼點,精度略遜於期末數但覆蓋密得多。
XBRL_WAVG_SHARES: Tuple[Tuple[date, float], ...] = (
    (date(2024, 3, 31), 171_942_000), (date(2024, 6, 30), 178_607_000),
    (date(2024, 9, 30), 197_273_000),
    (date(2025, 3, 31), 256_473_000), (date(2025, 6, 30), 275_244_000),
    (date(2025, 9, 30), 284_376_000),
    (date(2026, 3, 31), 333_913_000), (date(2026, 6, 30), 352_534_000),
)

BTC_EVENTS: Tuple[Tuple[date, str], ...] = (
    (date(2026, 4, 20), "買進 34,164 BTC(史上第三大)"),
    (date(2026, 5, 11), "買進 535 BTC —— 斷崖式縮小"),
    (date(2026, 5, 25), "2022 年以來首次賣出 BTC(32 枚)"),
    (date(2026, 6, 22), "買進 520 BTC"),
    (date(2026, 8, 9), "賣出 1,690 BTC($108.6M)用來回購 STRC"),
    (date(2026, 8, 16), "2026-08-10~16 無買賣"),
)
# §5.7 結構性轉折:融資飛輪已反轉 ——
# 從「發溢價股票買幣」變成「賣幣 + 募資去折價回購優先股」


def btc_held_as_of(on: date) -> float:
    value = BTC_HELD[0][1]
    for d, v, _ in BTC_HELD:
        if on >= d:
            value = v
    return value


# ===========================================================================
# §5.8 政策與定義變更(建模斷點)
# ===========================================================================

@dataclass(frozen=True)
class PolicyBreak:
    as_of: date
    title: str
    detail: str
    breaks_timeseries: bool


POLICY_BREAKS: Tuple[PolicyBreak, ...] = (
    PolicyBreak(date(2025, 8, 18), "mNAV 政策帶",
                ">4x 積極增發 / 2.5–4x 機會性 / <2.5x 戰術性付息 / <1x 考慮發債回購 MSTR"
                "(隱含股價 $210 / $600 / $1,000)", False),
    PolicyBreak(date(2026, 6, 29), "Digital Credit Capital Framework",
                "取代舊政策帶。USD Reserve 下限 $1.25B;$1.0B 優先股回購授權;"
                "$1.0B MSTR 回購授權;$1.25B BTC 變現授權", False),
    PolicyBreak(date(2026, 7, 23), "Strategy 重新定義自家 mNAV 為 price ÷ Net BPS",
                "⚠️ 時間序列必須在此斷開,公司明言前後 not comparable", True),
)


# ===========================================================================
# §5.9 第三方 CEBE 錨點(Tier 2,cross-check 用,不當事實)
# ===========================================================================

@dataclass(frozen=True)
class CebeAnchor:
    label: str
    as_of: date
    btc_price: float
    btc_held: float
    net_claims_usd: float
    claims_pct: float
    bps_sats: Optional[float]
    cebe_sats: Optional[float]
    source: str


CEBE_ANCHORS: Tuple[CebeAnchor, ...] = (
    CebeAnchor("2024-Q3", date(2024, 9, 30), 63_000, 252_220, 1_900 * M, 0.120,
               None, None, "cebetracker"),
    CebeAnchor("2024-Q4", date(2024, 12, 31), 95_000, 446_400, 1_400 * M, 0.033,
               None, None, "cebetracker"),
    CebeAnchor("2025-Q1", date(2025, 3, 31), 85_000, 550_000, 8_000 * M, 0.171,
               None, None, "cebetracker"),
    CebeAnchor("2026-01", date(2026, 1, 31), 88_348, 709_715, 14_324 * M, 0.228,
               None, None, "cebetracker"),
    CebeAnchor("2026-04-12", date(2026, 4, 12), 97_000, 780_897, 17_370 * M, 0.228,
               195_726, 151_015, "cebetracker"),
    CebeAnchor("2026-07-05", date(2026, 7, 5), 60_773, 843_775, 21_000 * M, 0.383,
               227_057, 140_200, "cebetracker"),
    CebeAnchor("2026-08-16", date(2026, 8, 16), 63_900, 842_137, 21_100 * M, 0.398,
               None, 119_309, "mnav.com"),
)

# 2026-01 與 2026-04 都是 22.8% —— 判定為真實巧合而非資料過期(信心度中)。
# 推翻條件:若實際使用的 4 月 BTC 價格明顯低於 ~$95K,則此判斷不成立。
COINCIDENCE_HYPOTHESIS = {
    "claim": "2026-01 與 2026-04 的 22.8% 是巧合,非資料過期",
    "confidence": "medium",
    "self_consistency_check": "(195,726 − 151,015) / 195,726 = 22.8%",
    "falsifier": "4 月實際 BTC 價格明顯低於 ~$95K",
    # 建置時的補充:上述自洽檢查與分母無關(分子分母同一個股數會約掉),
    # 所以即使 4 月與 7 月的股數基準不同(見 FINDING_CEBE_DENOMINATOR),
    # 這個巧合判定仍然成立。
    "verified_at_build": True,
}


# ---------------------------------------------------------------------------
# 建置期交叉驗證發現的規格書資料缺陷
# 這些不是我們的計算錯誤,是來源表格內部矛盾。全部保留原值並標記,不偷改。
# ---------------------------------------------------------------------------

FINDING_2026_07_05_CLAIMS = {
    "where": "§5.9 CEBE 錨點,2026-07-05 列,淨求償權 ~$21,000M",
    "problem": (
        "該列自己的另外三個欄位(claims% 38.3%、BPS 227,057 sats、CEBE 140,200 sats)"
        "彼此一致,但一致於 claims = $19.63B、股數 = 371.6M,不是 $21,000M。"
        "用 $21,000M 反算 claims% 會得到 40.95%,與同列的 38.3% 差 2.6 個百分點。"
    ),
    "evidence": {
        "claims_19_63B_implies_pct": 0.3828,      # 對上 38.3%
        "claims_21_00B_implies_pct": 0.4095,      # 對不上
        "shares_from_bps": 371.6e6,               # 對上 §5.4 的 2026-06-30 basic
        "shares_from_cebe": 371.5e6,
    },
    "resolution": (
        "採用 $19.63B —— 這正是規格書 §6.3 自己列給 cebetracker 的求償權金額。"
        "§5.9 的 ~$21,000M 視為筆誤(可能誤抄了 mnav.com 的 $21.1B 毛額)。"
    ),
    "corrected_value": 19.63 * B,
}

FINDING_CEBE_DENOMINATOR = {
    "where": "§5.9 CEBE 錨點,2026-04-12 vs 2026-07-05",
    "problem": (
        "4 月的 BPS/CEBE 反解出 ~398.7M 股,7 月反解出 ~371.6M 股。"
        "basic 股數只會單調上升,不可能從 4 月的 398.7M 掉到 7 月的 371.6M。"
        "⇒ 兩個錨點用了**不同的股數基準**(4 月接近 FDSO,7 月是 basic)。"
    ),
    "impact": (
        "CEBE sats 不能把這兩點直接連成一條連續序列。畫圖時必須斷開或標註分母變更,"
        "否則 4→7 月的 CEBE 下降會同時混入『分母定義改變』與『真實稀釋』兩種效果。"
    ),
    "resolution": "圖上把 cebetracker 錨點畫成散點而非折線,並標註分母不一致。",
}

FINDING_SPEC_ARITHMETIC = (
    {
        "where": "§6.1 驗算示範最後一行",
        "problem": "寫 36,680,092,713 ÷ 398,220,309 = $92.115,實際為 $92.11005",
        "impact": "無 —— 官方揭露值 $92.11 才是對的,只是示範的中間值多打了一位",
    },
    {
        "where": "§6.2 Net BPS 檢查列",
        "problem": "寫 $92.11 ÷ $64,279 × 1e8 = 143,280,實際為 143,297",
        "impact": "無 —— 與官方 143,292 的差距其實比規格書自己算的更小",
    },
    {
        "where": "§6.1 / 附錄「已完全反解驗證」「必須精確吻合」",
        "problem": (
            "不存在任何單一 FDSO 能在單一 rounding 規則下重現全部六列敏感度表。"
            "FWP 的 usd_reserve / debt / pref 只揭露到 $1M 精度,fdso 只寫 ~398.2M。"
        ),
        "impact": (
            "驗證必須帶容差。規格書給的 398,220,309 在六列全部落在 1bp 內(最差 1.5 分),"
            "最佳擬合值約 398,237,000(最差 0.4 分)。公式本身是對的。"
        ),
    },
)

FINDING_THIRD_DENOMINATOR = {
    "where": "§8.2(兩個分母)vs §7.3(對照表答案)",
    "problem": (
        "§8.2 只點出 Gross BPS 用 423.838M assumed diluted、Net BPS 用 398.2M FDSO。"
        "但 §7.3 的『Basic 基準 1.0x → ~$137』用的是第三個分母:394.2M basic shares。"
        "用 423.838M 只會得到 $127.46。"
    ),
    "resolution": "PriceBasis 分成 GROSS(423.8M)與 BASIC(394.2M)兩個獨立基準。",
}

# §5.10 的 Tier 3 讀數無法用 §5 的資本結構重現(缺當期 btc_held 與股數)
FINDING_ITM_CONVERTS_DOMINATE_2024 = {
    "where": "§5.9 的 2024-Q3/Q4 淨求償權($1.9B / $1.4B)",
    "observation": (
        "2024 年完全沒有優先股,所以淨求償權應該就是「可轉債 − 現金」。"
        "但 §5.3 說 2025 年底可轉債有 $8.21B,而 §5.9 卻說 2024-Q4 淨求償權只有 $1.4B。"
        "兩者差一個數量級。"
    ),
    "explanation": (
        "cebetracker 排除**價內**可轉債(§8.8 的同一個道理:價內會轉股,不是被償還)。"
        "2024 年底 MSTR 在 $290–$543 之間,而已知的轉換價在 $143 附近 ⇒ "
        "當時幾乎所有可轉債都是價內,因此幾乎全部被排除,淨求償權才會那麼小。"
        "2025 年 MSTR 下跌後可轉債轉為價外、同時優先股開始發行,"
        "淨求償權才從 $1.4B 跳到 $8.0B(2025-Q1)。"
    ),
    "confidence": "medium — 邏輯自洽且與已知的 $143.25 轉換價一致,但未逐系列驗證",
    "implication": (
        "**這強化了規格書自己的判斷:§5.3 的各系列轉換價是最該優先補的缺口。**"
        "2024→2025 淨求償權暴增的很大一部分不是新發債,而是既有可轉債從價內變價外。"
        "缺了轉換價,這段歷史的 claims 軌跡無法正確重建。"
    ),
}

FINDING_BTC_DATE_PAIRING = {
    "where": "§5.10,2025-12-01 列的 BTC ~$80,000",
    "problem": (
        "2025-12-01 的 Binance 實際收盤為 $86,286(盤中低 $83,823)。"
        "最接近 $80,000 的低點($80,600)出現在 **2025-11-21**,不是 12-01。"
        "該列把 MSTR 的 12-01 低點 ~$155 與另一天的 BTC 低點配在一起。"
    ),
    "impact": (
        "若照抄該列算 mNAV,分母會低估約 7.9%,mNAV 被高估約 8.6%。"
        "系統一律用 market_daily 的當日實際收盤,不用 §5.10 的 BTC 約值。"
    ),
    "resolution": "§5.10 的 BTC 價格欄僅作 advisory 對照,不作為計算輸入。",
}

FINDING_FDSO_COVERAGE = {
    "where": "§5.4 股數表,FDSO 只有 2026-08-10 一個時點",
    "problem": (
        "diluted mNAV 與公司自訂 mNAV 都需要 FDSO,但整條時間軸只有一個 FDSO 值。"
        "§5.4 給的『稀釋後加權平均股數』(192.5M / 277.7M / 333.9M)是**期間加權平均**,"
        "不是期末在外股數,拿來當 FDSO 會系統性偏低。"
    ),
    "impact": (
        "日頻序列裡 diluted 與 company 兩個變體只在 2026-08-10 之後有值(約 2 天),"
        "basic / enterprise / CEBE 則有完整覆蓋。這是資料缺口,不是計算失敗。"
    ),
    "resolution": (
        "core 在 shares_fdso 為 None 時**拒絕計算並拋錯**,由 all_mnavs 跳過,"
        "絕不用加權平均值代入。要補齊需從各期 10-Q 抄期末 FDSO。"
    ),
}

FINDING_TIER3_NOT_REPRODUCIBLE = {
    "where": "§5.10,2025-11-30 的 0.856 / 0.954 / 1.105 三讀數",
    "problem": (
        "§5 沒有 2025-11-30 的 btc_held 與股數(最近的觀測是 2025-03-31 的 550,000 BTC "
        "與 2025-12-31 的 292.4M 股),forward-fill 後算出的 basic mNAV 約 1.4x,"
        "與 Tier 3 讀數 0.856x 差距過大,無法交叉驗證。"
    ),
    "resolution": (
        "這三個讀數只用於檢查**結構不等式** basic < diluted < enterprise,"
        "不用於數值驗證。要真正驗證需補 2025 各季的 btc_held 與股數(附錄已標為缺口)。"
    ),
}


# ===========================================================================
# §5.10 已驗證的 mNAV 歷史讀數
# ===========================================================================

@dataclass(frozen=True)
class MNavObservation:
    as_of: date
    btc_price: Optional[float]
    mstr_price: Optional[float]
    readings: Dict[str, float]      # variant → value
    tier: str
    note: str = ""


MNAV_OBSERVATIONS: Tuple[MNavObservation, ...] = (
    MNavObservation(date(2024, 11, 21), 98_000, 543.0, {"basic": 3.4}, "3",
                    "ATH;峰值 basic mNAV"),
    MNavObservation(date(2025, 11, 30), 91_500, 247.0,
                    {"basic": 0.856, "diluted": 0.954, "enterprise": 1.105}, "3",
                    "同日三讀數 —— §8.1 的教科書例子"),
    MNavObservation(date(2025, 12, 1), 80_000, 155.0, {}, "3", "低點"),
    MNavObservation(date(2026, 6, 26), None, 82.31, {}, "2/3",
                    "52 週低;enterprise 首次 <1.0x(6/27 前後)"),
    MNavObservation(date(2026, 8, 3), 63_800, 94.86,
                    {"basic": 0.68, "enterprise": 1.02}, "2/3",
                    "跨越 1.0x 兩側"),
    MNavObservation(date(2026, 8, 10), 64_279, 97.33,
                    {"company": 1.06, "basic": 0.71}, "1",
                    "FWP —— Tier 1"),
    MNavObservation(date(2026, 8, 16), 63_900, None,
                    {"company": 1.06, "cebe": 1.12}, "2",
                    "naive 1.06x / CEBE 1.12x;52 週區間 0.97–1.43x"),
)

# §5.10 MSTR 日線 fixture(Tier 2,stockanalysis.com / S&P Global)
# 用來驗證 API 資料源是否正確(§9 步驟 2)
MSTR_DAILY_FIXTURE: Dict[str, float] = {
    "2026-06-04": 129.37, "2026-06-05": 120.44, "2026-06-08": 127.20,
    "2026-06-09": 117.02, "2026-06-10": 115.35, "2026-06-11": 120.15,
    "2026-06-12": 123.97, "2026-06-15": 131.14, "2026-06-16": 122.81,
    "2026-06-17": 116.56, "2026-06-18": 112.53, "2026-06-22": 109.46,
    "2026-06-23": 103.84, "2026-06-24": 94.13, "2026-06-25": 85.33,
    "2026-06-26": 82.31, "2026-06-29": 92.68, "2026-06-30": 86.93,
    "2026-07-01": 93.39, "2026-07-02": 100.77, "2026-07-07": 97.36,
    "2026-07-08": 93.87, "2026-07-09": 93.89, "2026-07-10": 94.64,
    "2026-07-13": 92.10, "2026-07-14": 97.58, "2026-07-15": 97.47,
    "2026-07-16": 94.03, "2026-07-17": 94.85, "2026-07-20": 97.82,
    "2026-07-21": 101.95, "2026-07-22": 100.01, "2026-07-23": 93.63,
    "2026-07-24": 91.67, "2026-07-27": 98.65, "2026-07-28": 96.16,
    "2026-07-29": 93.33, "2026-07-30": 97.74, "2026-07-31": 93.28,
    "2026-08-03": 94.86, "2026-08-04": 97.65, "2026-08-05": 98.37,
    "2026-08-06": 96.85, "2026-08-07": 100.01, "2026-08-10": 97.33,
    "2026-08-11": 96.09, "2026-08-12": 94.83, "2026-08-13": 97.10,
    "2026-08-14": 93.04,
}

OTHER_KNOWN_PRICES = {
    "52w_high": (date(2025, 8, 11), 414.36),
    "52w_low_intraday": (date(2025, 6, 26), 81.81),
    "2025-07-11": (date(2025, 7, 11), 434.58),
    "ath": (date(2024, 11, 21), 543.0),
}


# ===========================================================================
# §6 驗證錨點
# ===========================================================================

# §4.2 / §6.1 —— 2026-08-13 FWP 的確切參數(已反解驗證)
PARAMS_2026_08_13 = {
    "btc_held": 840_447,
    "usd_reserve": 4.650 * B,
    "debt_otm_notional": 6.754 * B,
    "pref_otm_notional": 15.239 * B,
    "fdso": 398_220_309,          # FWP 只寫 "~398.2M",此值為反解
}
FWP_2026_08_13_ACCESSION = "d169243dfwp"
FWP_SHARES_ASSUMED_DILUTED = 423.838 * M     # §8.2 Gross BPS 的分母,與 FDSO 不同
FWP_MSTR_PRICE = 97.33
FWP_BTC_PRICE = 64_279.0

# §6.1 黃金測試:官方敏感度表
FWP_SENSITIVITY_TABLE: Tuple[Tuple[float, float], ...] = (
    (40_000, 40.87),
    (50_000, 61.97),
    (64_279, 92.11),
    (75_000, 114.73),
    (100_000, 167.49),
    (150_000, 273.01),
)

# §6.2 其他必過檢查(同一份 FWP)
FWP_DERIVED_METRICS = {
    "mnav_company": 1.06,
    "gross_bps_sats": 198_289,
    "net_bps_sats": 143_292,
    "gross_bps_usd": 127.46,
    "net_bps_usd": 92.11,
    "amplification": 1.47,
    "market_cap_usd": 38.368 * B,
    "enterprise_value_usd": 55.710 * B,
    "btc_arr_breakeven_pct": 3.21,
    "btc_arr_floor_pct": -11.53,
    "btc_arr_hurdle_pct": 10.77,
    "vol_30d_pct": 64,
    "vol_1y_pct": 74,
}
FWP_ANNUAL_OBLIGATIONS = 1.736 * B

# §6.3 Break-even 三種算法 —— 全部都對,只是求償權定義不同
BREAK_EVEN_ANCHORS = {
    "strategy_official": {
        "claims_usd": 21.993 * B, "less_usd_reserve": 4.65 * B,
        "btc_held": 840_447, "expected": 20_635.0,
    },
    "cebetracker": {
        "claims_usd": 19.63 * B, "btc_held": 843_775, "expected": 23_270.0,
    },
    "mnav_com_gross": {
        "claims_usd": 21.05 * B, "btc_held": 840_447, "expected": 25_054.0,
    },
}
BREAK_EVEN_HISTORY = {2020: 9_224.0, 2026: (20_635.0, 25_054.0)}

# §8.4 三個並存的求償權總額
CLAIMS_TOTALS_IN_CIRCULATION = {
    "cebetracker": (17.4 * B, "扣現金與公司持有的 STRC"),
    "mnav_com": (21.1 * B, "毛額但漏掉 STRE"),
    "company": (22.0 * B, "毛額含 STRE:$6.754B 債 + $15.239B 優先股"),
}

# §7.3 對照表的正確答案
IMPLIED_PRICE_ANSWERS_2026_08_13 = {
    "net": {1.0: 92.11, 1.25: 115.14, 1.5: 138.17, 2.0: 184.22, 3.0: 276.33},
    "basic": {1.0: 137.0, 1.5: 206.0, 2.0: 274.0},   # 約值
}

# §1.3 已驗證的核心對數分解
LOG_DECOMPOSITION_ANCHOR = {
    "start": date(2024, 11, 21), "end": date(2026, 8, 13),
    "mnav_start": 3.67, "mnav_end": 0.71,
    "mstr_price": (543.0, 97.33),
    "btc_price": (98_000.0, 64_279.0),
    "bps_ratio": 1.367,          # BTC/share 上升 → 稀釋
    "expected_net_effect": 0.20,
}

# §8.10 已知的具名引述 —— 除此之外不編故事
NAMED_QUOTES = (
    ("Phong Le", "What Bitcoin Did", "2025-11-29 前後",
     "在 mNAV 低於 1 且融資管道斷絕時,會賣 BTC 支付股利;「我不想當那個賣比特幣的公司」"),
    ("Phong Le", "X", "2026-07-28",
     "升級後的指標「為 MSTR 的增值性增發建立 1.0x 門檻」"),
)


# ===========================================================================
# 組裝:CapitalStructure 時間軸
# ===========================================================================

def _prefs_from_balance(pb: PreferredBalance,
                        previous: Optional[Dict[str, float]] = None
                        ) -> Tuple[PreferredSeries, ...]:
    """把季末餘額轉成 PreferredSeries。

    None 代表「該系列該期未揭露」(如 2026-03-31 只揭露 STRC),
    此時**沿用上一期餘額**並標記推估 —— 那些餘額不會憑空消失,
    當成 0 會讓堆疊圖出現假的斷崖。
    """
    out: List[PreferredSeries] = []
    previous = previous or {}
    raw = {"STRK": pb.strk, "STRF": pb.strf, "STRD": pb.strd,
           "STRC": pb.strc, "STRE": pb.stre_usd}
    carried = set()
    resolved: Dict[str, float] = {}
    for ticker, amount in raw.items():
        if amount is None:
            prev = previous.get(ticker)
            if prev:
                resolved[ticker] = prev
                carried.add(ticker)
            continue
        resolved[ticker] = amount

    fields = tuple(resolved.items())
    known_sum = sum(v for _, v in fields if v)
    for ticker, amount in fields:
        if not amount:
            continue
        shares = (pb.shares_by_ticker or {}).get(ticker)
        out.append(PreferredSeries(
            ticker=ticker,
            liquidation_preference_usd=amount,
            shares=shares,
            rank=SENIORITY_RANK.get(ticker, 99),
            convertible=(ticker == "STRK"),
            currency="EUR" if ticker == "STRE" else "USD",
            liquidation_preference_native=(pb.stre_eur if ticker == "STRE" else None),
            fx_rate_as_of=(pb.fx_eur_usd if ticker == "STRE" else None),
            is_estimated=pb.is_estimated or ticker in carried,
        ))
    # 若申報總計高於分系列加總(如 2026-03-31 只知 STRC 且沿用上期後仍有殘差),
    # 補一筆 UNALLOCATED 讓總額精確等於申報值。
    if pb.total and known_sum and pb.total - known_sum > 1 * M:
        out.append(PreferredSeries(
            ticker="UNALLOCATED", liquidation_preference_usd=pb.total - known_sum,
            rank=99, is_estimated=True,
        ))
    return tuple(out)


def _converts_as_of(on: date) -> Tuple[float, bool]:
    """回傳 (可轉債總額, 是否為推估)。

    §5.3 只給三個時點,**沒有 2025 年底之前的季度餘額**。
    對更早的日期採用「由最早已知值向後回填」($8.21B @ 2025-12-31),
    因為債務結構變動不頻繁 —— 這是**明示的假設**,不是查到的數字,故標記推估。
    """
    earliest_date, earliest_value, _ = CONVERTIBLE_TOTALS[0]
    if on < earliest_date:
        return earliest_value, True
    value = earliest_value
    for d, v, _ in CONVERTIBLE_TOTALS:
        if on >= d:
            value = v
    return value, False


def _shares_as_of(on: date) -> ShareCount:
    chosen = SHARE_COUNTS[0]
    for sc in SHARE_COUNTS:
        if on >= sc.as_of:
            chosen = sc
    return chosen


def _cash_as_of(on: date) -> float:
    value = 0.0
    for d, v in BALANCE_SHEET_CASH:
        if on >= d:
            value = v
    return value


def capital_structure_timeline() -> List[CapitalStructure]:
    """把 §5 的分散表格組裝成一條 CapitalStructure 時間軸。

    ⚠️ 每個時點的欄位可靠度不同 —— is_estimated 為 True 表示「至少一個欄位是推估」。
    需要逐欄位追溯時請回頭查 PREFERRED_BALANCES / SHARE_COUNTS。
    """
    out: List[CapitalStructure] = []
    previous: Dict[str, float] = {}
    for pb in sorted(PREFERRED_BALANCES, key=lambda p: p.as_of):
        on = pb.as_of
        sc = _shares_as_of(on)
        obligations, _ = annual_obligations_as_of(on)
        prefs = _prefs_from_balance(pb, previous)
        previous = {p.ticker: p.liquidation_preference_usd for p in prefs
                    if p.ticker != "UNALLOCATED"}
        debt, debt_est = _converts_as_of(on)
        est = pb.is_estimated or sc.is_estimated or debt_est
        out.append(CapitalStructure(
            as_of=on,
            btc_held=btc_held_as_of(on),
            debt_notional_usd=debt,
            preferreds=prefs,
            convertibles=(),          # §5.3 缺口:分系列不完整,不放進求償權計算
            usd_reserve_usd=usd_reserve_as_of(on),
            cash_and_equiv_usd=_cash_as_of(on),
            shares_basic=sc.basic,
            shares_fdso=sc.fdso,
            shares_assumed_diluted=None,
            annual_obligations_usd=obligations or None,
            source_tier=1 if not est else 2,
            source_ref=pb.source,
            is_estimated=est,
            note=(f"preferred source: {pb.source}; shares source: {sc.source}"
                  + ("; converts backward-filled from $8.21B @2025-12-31 (§5.3 無更早季度餘額)"
                     if debt_est else "")),
        ))

    out.append(fwp_snapshot())
    return sorted(out, key=lambda c: c.as_of)


def fwp_snapshot() -> CapitalStructure:
    """2026-08-13 FWP 快照(Tier 1)—— §6 的黃金測試對象。"""
    p = PARAMS_2026_08_13
    # 分系列餘額用 2026-06-30 的比例把 $15.239B 拆開(僅供堆疊圖,不影響總額)
    q2 = next(pb for pb in PREFERRED_BALANCES if pb.as_of == date(2026, 6, 30))
    q2_series = {"STRK": q2.strk, "STRF": q2.strf, "STRD": q2.strd,
                 "STRC": q2.strc, "STRE": q2.stre_usd}
    q2_total = sum(q2_series.values())
    prefs = tuple(
        PreferredSeries(
            ticker=t,
            liquidation_preference_usd=v / q2_total * p["pref_otm_notional"],
            rank=SENIORITY_RANK.get(t, 99),
            convertible=(t == "STRK"),
            currency="EUR" if t == "STRE" else "USD",
            is_estimated=True,
        )
        for t, v in q2_series.items()
    )
    return CapitalStructure(
        as_of=date(2026, 8, 13),
        btc_held=p["btc_held"],
        debt_notional_usd=p["debt_otm_notional"],
        preferreds=prefs,
        convertibles=(),
        usd_reserve_usd=p["usd_reserve"],
        cash_and_equiv_usd=_cash_as_of(date(2026, 8, 13)),
        shares_basic=394_204_253,
        shares_fdso=p["fdso"],
        shares_assumed_diluted=FWP_SHARES_ASSUMED_DILUTED,
        annual_obligations_usd=FWP_ANNUAL_OBLIGATIONS,
        source_tier=1,
        source_ref=f"Form FWP {FWP_2026_08_13_ACCESSION}",
        is_estimated=False,
        note=("Tier 1。分系列優先股按 2026-06-30 比例拆分(推估,僅供堆疊圖);"
              "shares_basic 由市值 $38.368B ÷ $97.33 反解"),
    )
