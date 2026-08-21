"""§7 圖表規格。

配色規則(§7.1 明確要求,不是美學偏好):
  * 優先股各系列 = **同一色系的深淺漸層,依清償順位排序**(最優先最深)。
    順位是真實資訊,顏色必須編碼它。
  * 可轉債 = 另一色系(較深的中性色,因為它在所有優先股之上)。
  * 普通股權益 = 對比色。
  * **不要用彩虹配色。**

§1.2 的核心要求也在這裡執行:情緒溢價收縮與資本結構稀釋**畫成兩條並行軌跡**,
不做成「X% 來自情緒、Y% 來自稀釋」的堆疊圓餅圖。
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np


def _pick_cjk_font() -> Optional[str]:
    """圖上有大量中文標籤,沒有 CJK 字型會全部變成豆腐字。"""
    available = {f.name for f in fm.fontManager.ttflist}
    for name in ("PingFang HK", "PingFang TC", "PingFang SC", "Heiti TC",
                 "Hiragino Sans GB", "Songti SC", "Arial Unicode MS",
                 "Noto Sans CJK TC", "Microsoft JhengHei", "SimHei"):
        if name in available:
            return name
    return None


_CJK_FONT = _pick_cjk_font()
if _CJK_FONT:
    plt.rcParams["font.sans-serif"] = [_CJK_FONT, "DejaVu Sans"]
    plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.unicode_minus"] = False      # 負號用 ASCII,避免缺字

from . import core as C
from . import data as D
from . import db as DB

# ---------------------------------------------------------------------------
# 配色
# ---------------------------------------------------------------------------
# 優先股:單一藍色系,依清償順位由深到淺(STRF 最優先 → STRE 最劣後)
PREF_ORDER = ["STRF", "STRC", "STRK", "STRD", "STRE", "UNALLOCATED"]
PREF_COLORS = {
    "STRF": "#0b2545",
    "STRC": "#13395e",
    "STRK": "#1d5c8a",
    "STRD": "#3d84b8",
    "STRE": "#7fb3d5",
    "UNALLOCATED": "#c5d9e8",
}
CONVERT_COLOR = "#4a3f35"        # 可轉債:另一色系,深(順位最高)
EQUITY_COLOR = "#c1666b"         # 普通股權益:對比色
BTC_COLOR = "#e8963c"
MSTR_COLOR = "#2d6a4f"

MNAV_COLORS = {
    "basic": "#2d6a4f",
    "diluted": "#74a892",
    "enterprise": "#c1666b",
    "cebe": "#1d5c8a",
    "company": "#7d5ba6",
}

GRID = dict(alpha=0.25, linewidth=0.6)


def _style(ax) -> None:
    ax.grid(True, **GRID)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def _mark_events(ax, show_ipos: bool = True, show_breaks: bool = True,
                 label: bool = False) -> None:
    """標註優先股 IPO 日與政策/定義斷點(§7.1 下方註記線)。"""
    if show_ipos:
        for ipo in D.PREFERRED_IPOS:
            ax.axvline(ipo.pricing_date, color=PREF_COLORS.get(ipo.ticker, "#888"),
                       linestyle=":", linewidth=1.1, alpha=0.75, zorder=1)
            if label:
                # 貼在 axes 底端,避免壓到子圖標題
                ax.annotate(ipo.ticker, xy=(ipo.pricing_date, 0.0),
                            xycoords=("data", "axes fraction"),
                            xytext=(0, 4), textcoords="offset points",
                            ha="center", fontsize=7,
                            color=PREF_COLORS.get(ipo.ticker, "#888"))
    if show_breaks:
        for pb in D.POLICY_BREAKS:
            if pb.breaks_timeseries:
                ax.axvline(pb.as_of, color="#7d5ba6", linestyle="--",
                           linewidth=1.4, alpha=0.9, zorder=1)


# ---------------------------------------------------------------------------
# 讀資料
# ---------------------------------------------------------------------------

def _load(conn: sqlite3.Connection, start: dt.date, end: dt.date):
    rows = DB.load_market_daily(conn, start, end)
    dates, btc, mstr = [], [], []
    for r in rows:
        if r["btc_close_usd"] is None or r["mstr_close_usd"] is None:
            continue
        dates.append(dt.date.fromisoformat(r["date"]))
        btc.append(r["btc_close_usd"])
        mstr.append(r["mstr_close_usd"])
    return dates, np.array(btc), np.array(mstr)


def _mnav_series(conn: sqlite3.Connection, variant: str,
                 start: dt.date, end: dt.date
                 ) -> Dict[str, Tuple[List[dt.date], List[float]]]:
    """回傳 {comparable_key: (dates, values)} —— §8.5 的斷點靠 key 分段。"""
    rows = conn.execute(
        "SELECT as_of, comparable_key, value FROM mnav_readings "
        "WHERE variant = ? AND as_of BETWEEN ? AND ? ORDER BY as_of",
        (variant, start.isoformat(), end.isoformat())).fetchall()
    out: Dict[str, Tuple[List[dt.date], List[float]]] = {}
    for r in rows:
        key = r["comparable_key"]
        out.setdefault(key, ([], []))
        out[key][0].append(dt.date.fromisoformat(r["as_of"]))
        out[key][1].append(r["value"])
    return out


# ---------------------------------------------------------------------------
# §7.1 主圖:三軌歷史對照
# ---------------------------------------------------------------------------

def main_chart(conn: sqlite3.Connection,
               start: dt.date = dt.date(2024, 7, 1),
               end: dt.date = dt.date(2026, 12, 31),
               index_date: dt.date = dt.date(2024, 11, 21),
               out_path: str = "chart_main.png") -> str:
    dates, btc, mstr = _load(conn, start, end)
    structures = DB.load_capital_structures(conn)

    fig, axes = plt.subplots(3, 1, figsize=(15, 15), sharex=True,
                             gridspec_kw={"height_ratios": [1, 1, 1.05],
                                          "hspace": 0.13})
    ax1, ax2, ax3 = axes

    # ---- 子圖 1:indexed to 100 @ index_date ----
    try:
        i0 = dates.index(index_date)
    except ValueError:
        i0 = min(range(len(dates)), key=lambda i: abs((dates[i] - index_date).days))
    ax1.plot(dates, btc / btc[i0] * 100, color=BTC_COLOR, linewidth=1.7,
             label=f"BTC (indexed 100 @ {dates[i0]})")
    ax1.plot(dates, mstr / mstr[i0] * 100, color=MSTR_COLOR, linewidth=1.7,
             label="MSTR (same base)")
    ax1.axhline(100, color="#555", linewidth=0.8, linestyle="-", alpha=0.5)
    ax1.set_yscale("log")
    ax1.set_ylabel("Indexed = 100(對數軸)")
    ax1.set_title("① BTC 與 MSTR 的發散 —— 同基期指數化", loc="left",
                  fontsize=12, fontweight="bold")
    ax1.legend(loc="upper right", fontsize=9, framealpha=0.9)
    _style(ax1)
    _mark_events(ax1, label=True)

    # 標出 ATH 的盤中高點 vs 收盤(FINDING_ATH_IS_INTRADAY)
    ax1.annotate(f"2024-11-21 收盤 \\${D.ATH_CLOSE_2024_11_21:.0f}\n"
                 f"(盤中高 \\$543 才是 ATH)",
                 xy=(dates[i0], mstr[i0] / mstr[i0] * 100),
                 xytext=(18, -46), textcoords="offset points", fontsize=7.5,
                 color="#444", arrowprops=dict(arrowstyle="->", lw=0.7, color="#666"))

    # ---- 子圖 2:mNAV 各變體 ----
    for variant in ("basic", "enterprise", "cebe", "diluted", "company"):
        segments = _mnav_series(conn, variant, start, end)
        for j, (key, (ds, vs)) in enumerate(sorted(segments.items())):
            if len(ds) < 2:
                ax2.scatter(ds, vs, s=22, color=MNAV_COLORS[variant],
                            zorder=5, label=f"{variant}(僅 {len(ds)} 點)")
                continue
            ax2.plot(ds, vs, color=MNAV_COLORS[variant], linewidth=1.5,
                     alpha=0.95, label=variant if j == 0 else None)
    ax2.axhline(1.0, color="#111", linewidth=1.2, linestyle="-", alpha=0.8)
    ax2.annotate("1.0x", xy=(0.005, 1.0), xycoords=("axes fraction", "data"),
                 xytext=(2, 4), textcoords="offset points", fontsize=8.5,
                 fontweight="bold")
    ax2.set_yscale("log")
    ax2.set_ylabel("mNAV(對數軸)")
    ax2.set_title("② mNAV 各變體 —— 何時分岔、何時跨越 1.0x", loc="left",
                  fontsize=12, fontweight="bold")
    ax2.legend(loc="upper right", fontsize=8.5, ncol=2, framealpha=0.9)
    _style(ax2)
    _mark_events(ax2)
    for pb in D.POLICY_BREAKS:
        if pb.breaks_timeseries:
            ax2.annotate("公司定義變更\n(前後不可比)", xy=(pb.as_of, 1.0),
                         xycoords=("data", "axes fraction"),
                         xytext=(-64, 8), textcoords="offset points",
                         fontsize=7.5, color="#7d5ba6", fontweight="bold")

    # ---- 子圖 3:資本結構堆疊面積 + Claims % ----
    sdates = [c.as_of for c in structures]
    stacks: Dict[str, List[float]] = {"CONVERTS": []}
    for t in PREF_ORDER:
        stacks[t] = []
    for c in structures:
        stacks["CONVERTS"].append(c.debt_notional_usd / 1e9)
        pref = c.preferred_by_ticker
        for t in PREF_ORDER:
            stacks[t].append(pref.get(t, 0.0) / 1e9)

    labels, values, colors = [], [], []
    for key in ["CONVERTS"] + PREF_ORDER:
        if max(stacks[key]) <= 0:
            continue
        labels.append("可轉債" if key == "CONVERTS" else key)
        values.append(stacks[key])
        colors.append(CONVERT_COLOR if key == "CONVERTS" else PREF_COLORS[key])

    ax3.stackplot(sdates, *values, labels=labels, colors=colors, alpha=0.95,
                  edgecolor="white", linewidth=0.5)
    ax3.set_ylabel("求償權(清算優先權,\\$B)")
    ax3.set_title("③ 資本結構:優先股何時開始吃掉普通股"
                  "(依清償順位深→淺)", loc="left", fontsize=12, fontweight="bold")
    _style(ax3)
    _mark_events(ax3)

    # 右軸:Claims %(用當日實際 BTC 收盤,不用 §5.9 的約值)
    ax3b = ax3.twinx()
    market = {d: b for d, b in zip(dates, btc)}
    cd, cp = [], []
    for c in structures:
        px = market.get(c.as_of)
        if px is None:
            near = [d for d in dates if abs((d - c.as_of).days) <= 5]
            if not near:
                continue
            px = market[min(near, key=lambda d: abs((d - c.as_of).days))]
        cd.append(c.as_of)
        cp.append(C.claims_pct(c, px, C.ClaimsBasis.CEBETRACKER, 0.0) * 100)
    ax3b.plot(cd, cp, color=EQUITY_COLOR, linewidth=2.2, marker="o",
              markersize=4.5, label="Claims %(右軸)")
    ax3b.set_ylabel("Claims %(BTC 計價的求償權 ÷ 持有量)", color=EQUITY_COLOR)
    ax3b.tick_params(axis="y", labelcolor=EQUITY_COLOR)
    ax3b.set_ylim(0, max(cp) * 1.35 if cp else 50)
    ax3b.spines["top"].set_visible(False)

    h1, l1 = ax3.get_legend_handles_labels()
    h2, l2 = ax3b.get_legend_handles_labels()
    ax3.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8.5, ncol=2,
               framealpha=0.9)

    # 申報日刻度(§3:讓讀者知道哪一段是真實觀測)
    for c in structures:
        ax3.plot([c.as_of], [0], marker="^", markersize=6, clip_on=False,
                 color="#111" if not c.is_estimated else "#aaa", zorder=6)
    ax3.annotate("▲ 申報日(灰 = 含推估值)", xy=(0.005, -0.11),
                 xycoords="axes fraction", fontsize=8, color="#444")

    ax3.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.setp(ax3.get_xticklabels(), rotation=45, ha="right")

    fig.suptitle("MSTR × BTC × mNAV × CEBE 歷史對照(§7.1 三軌主圖)",
                 fontsize=15, fontweight="bold", y=0.995)
    fig.text(0.5, 0.005,
             "資料:BTC = Binance 日線 / MSTR = Yahoo 日線(split-adjusted)/ "
             "資本結構 = SEC 申報,事件頻 forward-fill。"
             "虛線 = 優先股 IPO 定價日;紫色虛線 = 2026-07-23 公司 mNAV 定義變更。",
             ha="center", fontsize=8, color="#555")
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
# §7.2.1 Gross BPS vs Net BPS —— 兩線間的面積就是 phantom growth
# §1.2 要求:與情緒軌跡並行呈現,不是堆疊
# ---------------------------------------------------------------------------

def bps_chart(conn: sqlite3.Connection,
              out_path: str = "chart_bps.png") -> str:
    structures = [c for c in DB.load_capital_structures(conn)]
    market = {dt.date.fromisoformat(r["date"]): r
              for r in DB.load_market_daily(conn)}

    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True,
                                  gridspec_kw={"hspace": 0.12})

    ds, gross, net = [], [], []
    for c in structures:
        row = market.get(c.as_of) or _nearest(market, c.as_of)
        if row is None:
            continue
        btc_px, mstr_px = row["btc_close_usd"], row["mstr_close_usd"]
        if btc_px is None or mstr_px is None:
            continue
        shares_gross = c.shares_assumed_diluted or c.shares_basic
        if shares_gross is None:
            continue
        ds.append(c.as_of)
        gross.append(C.gross_bps_sats(c.btc_held, shares_gross))
        # Net 需要 FDSO;沒有就用 CEBE 當替代並註記
        if c.shares_fdso is not None:
            net.append(C.net_bps_sats(
                C.net_reserve_per_share_from(c, btc_px, mstr_px), btc_px))
        else:
            net.append(C.cebe_sats(c, btc_px, C.ClaimsBasis.CEBETRACKER, mstr_px))

    ax.plot(ds, gross, color="#1d5c8a", linewidth=2.2, marker="o", markersize=5,
            label="Gross BPS(不扣求償權)")
    ax.plot(ds, net, color=EQUITY_COLOR, linewidth=2.2, marker="s", markersize=5,
            label="Net / CEBE BPS(扣淨求償權)")
    ax.fill_between(ds, net, gross, color=EQUITY_COLOR, alpha=0.17,
                    label="↑ 這塊面積 = phantom growth")
    ax.set_ylabel("sats / share")
    ax.set_title("§7.2.1 Gross BPS vs Net BPS —— 兩線之間就是 phantom growth",
                 loc="left", fontsize=12, fontweight="bold")
    ax.legend(loc="upper left", fontsize=9.5)
    _style(ax)
    _mark_events(ax, label=True)

    # 官方 2026-08-13 錨點
    ax.scatter([dt.date(2026, 8, 13)], [D.FWP_DERIVED_METRICS["gross_bps_sats"]],
               marker="*", s=190, color="#111", zorder=6,
               label="FWP 官方值")
    ax.scatter([dt.date(2026, 8, 13)], [D.FWP_DERIVED_METRICS["net_bps_sats"]],
               marker="*", s=190, color="#111", zorder=6)

    # 下panel:落差本身(§1.2 的第二條軌跡)
    gap = [g - n for g, n in zip(gross, net)]
    pct = [(g - n) / g * 100 for g, n in zip(gross, net)]
    ax2.bar(ds, gap, width=26, color=EQUITY_COLOR, alpha=0.85,
            label="Gross − Net(sats)")
    ax2.set_ylabel("落差(sats/share)")
    ax2b = ax2.twinx()
    ax2b.plot(ds, pct, color="#0b2545", linewidth=2.0, marker="o", markersize=4,
              label="落差佔 Gross 的 %(右軸)")
    ax2b.set_ylabel("% of Gross BPS", color="#0b2545")
    ax2b.tick_params(axis="y", labelcolor="#0b2545")
    ax2b.spines["top"].set_visible(False)
    ax2.set_title("每股被優先求償權切走的部分 —— 這是「資本結構稀釋」軌跡,"
                  "與情緒溢價正交", loc="left", fontsize=11, fontweight="bold")
    h1, l1 = ax2.get_legend_handles_labels()
    h2, l2 = ax2b.get_legend_handles_labels()
    ax2.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=9)
    _style(ax2)
    _mark_events(ax2)
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.setp(ax2.get_xticklabels(), rotation=45, ha="right")

    fig.text(0.5, 0.02,
             "[注意] 兩條線在 2026-08-13 之前都是替代定義:assumed diluted 與 FDSO 都只有該日有申報值(§5.4),\n"
             "其餘時點 Gross 以 basic 股數、Net 以 CEBE(basic 股數、扣現金)替代。★ = FWP 官方值。\n"
             "折線的鋸齒來自 btc_held 與股數的申報頻率不同(事件頻),不是雜訊 —— 見 data.FINDING_FDSO_COVERAGE。",
             ha="center", fontsize=8, color="#555")
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path


def _nearest(market: Dict[dt.date, object], target: dt.date,
             window: int = 6) -> Optional[object]:
    best, bestd = None, 10 ** 9
    for d, row in market.items():
        gap = abs((d - target).days)
        if gap <= window and gap < bestd and row["btc_close_usd"] is not None:
            best, bestd = row, gap
    return best


# ---------------------------------------------------------------------------
# §7.2.2 Break-even 軌跡(三種定義)+ BTC 實際價格
# ---------------------------------------------------------------------------

def breakeven_chart(conn: sqlite3.Connection,
                    out_path: str = "chart_breakeven.png") -> str:
    structures = DB.load_capital_structures(conn)
    rows = DB.load_market_daily(conn)
    dates = [dt.date.fromisoformat(r["date"]) for r in rows
             if r["btc_close_usd"] is not None]
    btc = [r["btc_close_usd"] for r in rows if r["btc_close_usd"] is not None]

    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True,
                                  gridspec_kw={"height_ratios": [1.5, 1],
                                               "hspace": 0.12})

    ax.plot(dates, btc, color=BTC_COLOR, linewidth=1.5, alpha=0.85,
            label="BTC 實際收盤")

    styles = {
        "company": ("#0b2545", "-", "毛額含 STRE(公司,不扣現金)"),
        "mnav_com": ("#1d5c8a", "-.", "mnav.com(毛額,漏 STRE)"),
        "cebetracker": ("#3d84b8", "--", "cebetracker(扣現金)"),
        "company_net_reserve": ("#c1666b", "-", "Strategy 官方(扣 USD Reserve)"),
    }
    sd = [c.as_of for c in structures]
    for basis, (color, ls, label) in styles.items():
        vals = [C.break_even_btc(c, C.ClaimsBasis(basis), 0.0) for c in structures]
        ax.plot(sd, vals, color=color, linestyle=ls, linewidth=2.0,
                marker="o", markersize=4, label=f"break-even: {label}")

    # §6.3 官方錨點
    for name, spec in D.BREAK_EVEN_ANCHORS.items():
        ax.scatter([dt.date(2026, 8, 13)], [spec["expected"]], marker="*",
                   s=150, color="#111", zorder=6)
    ax.annotate("§6.3 三個錨點\n\\$20,635 / \\$23,270 / \\$25,054",
                xy=(dt.date(2026, 8, 13), 23_000), xytext=(-155, 26),
                textcoords="offset points", fontsize=8, color="#111",
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#666"))

    ax.set_yscale("log")
    # 早期的 break-even 落在 $17K–20K,不設下界會被裁掉看不見
    ax.set_ylim(bottom=min(15_000, min(btc) * 0.9))
    ax.set_ylabel("BTC 價格(\\$,對數軸)")
    ax.set_title("§7.2.2 Break-even 軌跡 —— 三種求償權定義都對,"
                 "緩衝空間怎麼縮小", loc="left", fontsize=12, fontweight="bold")
    ax.legend(loc="upper left", fontsize=8.5, ncol=2, framealpha=0.9)
    _style(ax)
    _mark_events(ax, label=True)

    # 下panel:緩衝倍數 = BTC 價 ÷ break-even
    market = {d: p for d, p in zip(dates, btc)}
    bd, buf = [], []
    for c in structures:
        px = market.get(c.as_of)
        if px is None:
            near = [d for d in dates if abs((d - c.as_of).days) <= 6]
            if not near:
                continue
            px = market[min(near, key=lambda d: abs((d - c.as_of).days))]
        be = C.break_even_btc(c, C.ClaimsBasis.CEBETRACKER, 0.0)
        bd.append(c.as_of)
        buf.append(px / be if be > 0 else np.nan)
    ax2.bar(bd, buf, width=26, color="#3d84b8", alpha=0.85)
    ax2.axhline(1.0, color="#c1666b", linewidth=1.6,
                label="1.0x = 普通股歸零")
    ax2.set_ylabel("緩衝倍數(BTC 價 ÷ break-even)")
    ax2.set_title("緩衝倍數(cebetracker 定義):2025 初約 4.5x → 2026 年中約 2.5x",
                  loc="left", fontsize=11, fontweight="bold")
    ax2.set_yscale("log")
    ax2.legend(loc="upper right", fontsize=9)
    _style(ax2)
    _mark_events(ax2)
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.setp(ax2.get_xticklabels(), rotation=45, ha="right")

    fig.text(0.5, 0.02,
             "[注意] 2025 年之前用的是可轉債面額(且由 2025-12-31 回填)。"
             "cebetracker 排除價內可轉債,其 2024-Q4 淨求償權只有 \\$1.4B,"
             "對應緩衝約 30x —— 差異全在 ITM 判定,見 data.FINDING_ITM_CONVERTS_DOMINATE_2024。",
             ha="center", fontsize=8, color="#555")
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
# §7.2.3 等值線對照圖 —— 回答核心問題的關鍵視覺
# 「同樣的 BTC 價格,優先股讓 mNAV 地圖怎麼位移」
# ---------------------------------------------------------------------------

def contour_chart(conn: sqlite3.Connection,
                  out_path: str = "chart_contour.png",
                  btc_range: Tuple[float, float] = (12_000, 160_000),
                  mstr_range: Tuple[float, float] = (40, 700)) -> str:
    """§7.2.3 —— 最能直接回答核心問題的一張。

    ⚠️ 2024 那一側的求償權有兩個都成立的數字,差一個數量級:
        notional  $8.21B  = 可轉債面額(且是由 2025-12-31 回填的,§5.3 無更早餘額)
        ITM-excl  $1.40B  = cebetracker 的 2024-Q4 淨求償權
      差異來源是**價內可轉債被排除**(見 data.FINDING_ITM_CONVERTS_DOMINATE_2024):
      2024 年底 MSTR 在 $290–543,轉換價 ~$143 ⇒ 幾乎全部價內。
      兩條線都畫出來,否則左圖會把「可轉債面額」誤呈現為 2024 年的真實稀釋。
    """
    structures = {c.as_of: c for c in DB.load_capital_structures(conn)}
    left = structures[dt.date(2024, 12, 31)]     # 優先股 = $0 的時代
    right = structures[dt.date(2026, 8, 13)]     # FWP,優先股 $15.2B

    q4_2024 = next(a for a in D.CEBE_ANCHORS if a.label == "2024-Q4")

    # (structure, 標題, [(claims_usd, 標籤, 線型), ...])
    panels = (
        (0, left, "2024-12-31 資本結構(優先股 = \\$0)", [
            (q4_2024.net_claims_usd, f"CEBE 1.0x\n(ITM 排除後 \\${q4_2024.net_claims_usd/1e9:.1f}B)",
             "--", EQUITY_COLOR),
            (C.net_senior_claims_usd(left, C.ClaimsBasis.CEBETRACKER, 0.0),
             f"(可轉債面額 \\${left.debt_notional_usd/1e9:.1f}B)", ":", "#b08968"),
        ]),
        (1, right, "2026-08-13 資本結構(優先股 = \\$15.2B)", [
            (C.net_senior_claims_usd(right, C.ClaimsBasis.CEBETRACKER, 0.0),
             f"CEBE 1.0x\n(\\${C.net_senior_claims_usd(right, C.ClaimsBasis.CEBETRACKER, 0.0)/1e9:.1f}B)",
             "--", EQUITY_COLOR),
        ]),
    )

    fig, axes = plt.subplots(1, 2, figsize=(16.5, 7.6), sharey=True)
    levels = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0]

    btc_axis = np.linspace(*btc_range, 320)
    mstr_axis = np.linspace(*mstr_range, 320)
    BB, MM = np.meshgrid(btc_axis, mstr_axis)

    for idx, cs, title, claim_lines in panels:
        ax = axes[idx]

        # basic mNAV 地圖:市值 ÷ BTC NAV(看不到優先股,兩圖只差在股數與持幣量)
        Z = (MM * cs.shares_basic) / (cs.btc_held * BB)
        cf = ax.contourf(BB / 1000, MM, Z, levels=levels, cmap="RdYlBu_r",
                         alpha=0.55, extend="both")
        cl = ax.contour(BB / 1000, MM, Z, levels=levels, colors="#333",
                        linewidths=0.7)
        ax.clabel(cl, fmt="%.2gx", fontsize=8.5)

        one = ax.contour(BB / 1000, MM, Z, levels=[1.0], colors="#111",
                         linewidths=2.6)
        ax.clabel(one, fmt="basic 1.0x", fontsize=9.5)

        # CEBE 1.0x:扣淨求償權後的普通股淨值線 —— 這條才看得到優先股
        for claims, label, ls, color in claim_lines:
            per_share = (cs.btc_held * BB - claims) / cs.shares_basic
            Zc = MM / np.where(per_share > 0, per_share, np.nan)
            cc = ax.contour(BB / 1000, MM, Zc, levels=[1.0], colors=color,
                            linewidths=2.4, linestyles=ls)
            ax.clabel(cc, fmt=label, fontsize=8.5)

            be = claims / cs.btc_held
            if btc_range[0] <= be <= btc_range[1]:
                ax.axvline(be / 1000, color=color, linewidth=1.6,
                           linestyle=":", alpha=0.9)
                ax.annotate(f"break-even\n\\${be:,.0f}",
                            xy=(be / 1000, mstr_range[1]),
                            xytext=(4, -36), textcoords="offset points",
                            fontsize=8, color=color, fontweight="bold")

        ax.set_xlabel("BTC 價格(\\$K)")
        ax.set_title(title, fontsize=11.5, fontweight="bold")
        ax.grid(True, **GRID)
        ax.set_xlim(btc_range[0] / 1000, btc_range[1] / 1000)
        ax.set_ylim(*mstr_range)

    axes[0].set_ylabel("MSTR 股價(\\$)")

    # 實際歷史軌跡疊上去
    rows = DB.load_market_daily(conn)
    hb = [r["btc_close_usd"] / 1000 for r in rows
          if r["btc_close_usd"] and r["mstr_close_usd"]]
    hm = [r["mstr_close_usd"] for r in rows
          if r["btc_close_usd"] and r["mstr_close_usd"]]
    for ax in axes:
        ax.plot(hb, hm, color="#111", linewidth=0.9, alpha=0.5,
                label="實際歷史路徑 2024-07→2026-08")
        ax.scatter([hb[-1]], [hm[-1]], s=70, color="#111", zorder=7,
                   marker="X",
                   label=f"最新 (\\${hb[-1]*1000:,.0f}, \\${hm[-1]:.2f})")
        ax.legend(loc="upper left", fontsize=8.5, framealpha=0.92)

    fig.colorbar(cf, ax=axes, label="basic mNAV", fraction=0.028, pad=0.015)
    fig.suptitle("§7.2.3 等值線對照:同樣的 BTC 價格,優先股讓 mNAV 地圖怎麼位移",
                 fontsize=14, fontweight="bold", y=1.0)
    fig.text(0.5, -0.055,
             "黑實線 = basic mNAV 1.0x(看不到優先股,兩張圖只差在持幣量與股數)。"
             "紅虛線 = CEBE 1.0x —— 求償權越大,可分配給普通股的每股 BTC 越少,"
             "這條線就越往下離開黑線;兩線之間的楔形就是資本結構稀釋,"
             "且在 break-even 以左完全消失。\n"
             "左圖畫兩條:2024 年底幾乎所有可轉債都價內(轉換價 ~\\$143 vs 股價 \\$290–543),"
             "所以 ITM 排除後的真實求償權只有 \\$1.4B,而非面額 \\$8.2B。"
             "這也是為什麼 §5.3 的各系列轉換價是最該優先補的缺口。",
             ha="center", fontsize=8.5, color="#444")
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
# §1.2 —— 兩條並行軌跡(明確**不是**堆疊圖)
# ---------------------------------------------------------------------------

def orthogonal_chart(conn: sqlite3.Connection,
                     out_path: str = "chart_orthogonal.png") -> str:
    """§1.2 的核心分析要求:情緒溢價收縮 vs 資本結構稀釋,兩條並行軌跡。

    刻意**不做**堆疊圖 —— 這兩件事活在不同的度量上,不能加總。
    """
    structures = DB.load_capital_structures(conn)
    market = {dt.date.fromisoformat(r["date"]): r
              for r in DB.load_market_daily(conn)}

    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(14, 9.5), sharex=True,
                                  gridspec_kw={"hspace": 0.14})

    # 軌跡 A:情緒溢價 = basic mNAV(數學上完全看不到優先股)
    seg = _mnav_series(conn, "basic", dt.date(2024, 1, 1), dt.date(2027, 1, 1))
    for ds, vs in seg.values():
        ax.plot(ds, vs, color=MSTR_COLOR, linewidth=1.6)
    ax.axhline(1.0, color="#111", linewidth=1.1, alpha=0.7)
    ax.set_ylabel("basic mNAV")
    ax.set_yscale("log")
    ax.set_title("軌跡 A —— 市場情緒溢價(basic mNAV:在數學上看不到優先股)",
                 loc="left", fontsize=11.5, fontweight="bold", color=MSTR_COLOR)
    _style(ax)
    _mark_events(ax, label=True)

    # 軌跡 B:資本結構稀釋 = Claims %
    cd, cp = [], []
    for c in structures:
        row = market.get(c.as_of) or _nearest(market, c.as_of)
        if row is None:
            continue
        cd.append(c.as_of)
        cp.append(C.claims_pct(c, row["btc_close_usd"],
                               C.ClaimsBasis.CEBETRACKER, 0.0) * 100)
    ax2.plot(cd, cp, color=EQUITY_COLOR, linewidth=2.4, marker="o", markersize=5)
    ax2.fill_between(cd, 0, cp, color=EQUITY_COLOR, alpha=0.15)
    ax2.set_ylabel("Claims %(優先求償權佔 BTC 持有量)")
    ax2.set_title("軌跡 B —— 資本結構稀釋(Claims %:完全不出現在上圖)",
                  loc="left", fontsize=11.5, fontweight="bold", color=EQUITY_COLOR)
    _style(ax2)
    _mark_events(ax2)
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.setp(ax2.get_xticklabels(), rotation=45, ha="right")

    fig.suptitle("§1.2 兩件事是正交的 —— 並行軌跡,不是堆疊圖",
                 fontsize=14, fontweight="bold", y=0.98)
    fig.text(0.5, 0.015,
             "[注意] 規格書 §1.2 明確禁止把這兩者畫成「壓縮的 X% 來自情緒、Y% 來自稀釋」的"
             "堆疊圖 —— 它們活在不同的度量上,不能加總。",
             ha="center", fontsize=8.5, color="#555")
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path


def build_all(conn: sqlite3.Connection, prefix: str = "") -> List[str]:
    return [
        main_chart(conn, out_path=f"{prefix}chart_main.png"),
        bps_chart(conn, out_path=f"{prefix}chart_bps.png"),
        breakeven_chart(conn, out_path=f"{prefix}chart_breakeven.png"),
        contour_chart(conn, out_path=f"{prefix}chart_contour.png"),
        orthogonal_chart(conn, out_path=f"{prefix}chart_orthogonal.png"),
    ]
