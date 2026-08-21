"""查詢工具 —— 回答 §1.1 的核心問題。

    「在 BTC = X 的情況下,mNAV = Y 對應到 MSTR 股價是多少?」

用法:
    python3 -m mstr_cebe.cli price --btc 64279 --mnav 1.0
    python3 -m mstr_cebe.cli table --btc 64279 --date 2026-08-13
    python3 -m mstr_cebe.cli snapshot --date 2026-08-13
    python3 -m mstr_cebe.cli breakeven --date 2026-08-13
    python3 -m mstr_cebe.cli findings
    python3 -m mstr_cebe.cli decompose --from 2024-11-21 --to 2026-08-13

設計原則:**任何 mNAV 數字一律連同 variant 與日期一起印出**(§8.1)。
沒有任何一個指令會印出裸的 mNAV 值。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from typing import List, Optional

from . import core as C
from . import data as D
from . import db as DB

BASIS_HELP = {
    "gross": "BTC NAV ÷ assumed diluted (423.8M) —— 官方 Gross BPS",
    "basic": "BTC NAV ÷ basic shares (394.2M) —— §7.3 對照表基準",
    "net":   "Strategy 官方 Net Reserve/Share(扣 OTM 債與優先股)",
    "cebe":  "cebetracker(扣淨求償權 ÷ basic shares)",
}


def _structure(conn, on: dt.date, quiet: bool = False) -> C.CapitalStructure:
    """取 `on` 當日有效的資本結構。

    查詢日早於最早申報時,**明確降級**成最早的那一筆並印出警告 ——
    §5 的資本結構從 2024-12-31 才開始,更早的日期只能借用,不能假裝有資料。
    """
    timeline = DB.load_capital_structures(conn)
    if not timeline:
        raise SystemExit("capital_structure 是空的 —— 先跑 python3 build_db.py")
    try:
        return C.as_of_structure(timeline, on)
    except ValueError:
        earliest = min(timeline, key=lambda c: c.as_of)
        if not quiet:
            print(f"⚠️  {on} 早於最早的資本結構觀測 {earliest.as_of},"
                  f"以下借用 {earliest.as_of} 的資料(backward-fill,非觀測值)。\n")
        from dataclasses import replace as _replace
        return _replace(earliest, as_of=on,
                        is_estimated=True,
                        note=f"{earliest.note}; backward-filled from {earliest.as_of}")


def _resolve_btc(conn, on: dt.date, btc: Optional[float]) -> float:
    if btc is not None:
        return btc
    row = conn.execute(
        "SELECT btc_close_usd FROM market_daily WHERE date <= ? "
        "AND btc_close_usd IS NOT NULL ORDER BY date DESC LIMIT 1",
        (on.isoformat(),)).fetchone()
    if row is None:
        raise SystemExit("找不到 BTC 價格,請用 --btc 指定")
    return row["btc_close_usd"]


def _banner(cs: C.CapitalStructure, btc: float) -> None:
    print(f"資本結構基準日 : {cs.source_ref or '—'}")
    print(f"BTC 持有       : {cs.btc_held:,.0f}")
    print(f"可轉債面額     : ${cs.debt_notional_usd/1e9:,.3f}B")
    print(f"優先股清算優先權: ${cs.preferred_total_usd/1e9:,.3f}B  "
          + " / ".join(f"{k} ${v/1e9:.2f}B"
                       for k, v in sorted(cs.preferred_by_ticker.items())))
    print(f"USD Reserve    : ${cs.usd_reserve_usd/1e9:,.3f}B   "
          f"(資產負債表現金 ${cs.cash_and_equiv_usd/1e9:,.3f}B —— 兩者不同,§5.5)")
    print(f"股數           : basic {_m(cs.shares_basic)} / "
          f"FDSO {_m(cs.shares_fdso)} / assumed diluted {_m(cs.shares_assumed_diluted)}")
    print(f"BTC 價格       : ${btc:,.2f}")
    if cs.is_estimated:
        print("⚠️  此時點含推估值(is_estimated=True)")
    if "forward-filled" in cs.note:
        print(f"⚠️  {cs.note.split('; ')[-1]}")
    print()


def _m(v: Optional[float]) -> str:
    return "未知" if v is None else f"{v/1e6:,.1f}M"


# ---------------------------------------------------------------------------

def cmd_price(args, conn) -> int:
    on = dt.date.fromisoformat(args.date)
    cs = _structure(conn, on)
    btc = _resolve_btc(conn, on, args.btc)
    _banner(cs, btc)

    print(f"在 BTC = ${btc:,.0f} 之下,達到目標 mNAV 所需的 MSTR 股價:\n")
    print(f"  {'基準':<8} {'每股淨值':>12} {'目標 mNAV':>10} {'隱含股價':>12}   說明")
    print("  " + "-" * 92)
    for basis in C.PriceBasis:
        try:
            per_share = C.implied_mstr_price(cs, btc, 1.0, basis)
            price = C.implied_mstr_price(cs, btc, args.mnav, basis)
        except ValueError as exc:
            print(f"  {basis.value:<8} {'不可用':>12}   —— {exc}")
            continue
        print(f"  {basis.value:<8} ${per_share:>11,.2f} {args.mnav:>9.2f}x "
              f"${price:>11,.2f}   {BASIS_HELP[basis.value]}")
    print("\n⚠️ 這幾個數字都是對的,差別只在分母與求償權定義(§8.1/§8.2/§8.4)。")
    return 0


def cmd_table(args, conn) -> int:
    """§7.3 對照表。"""
    on = dt.date.fromisoformat(args.date)
    cs = _structure(conn, on)
    btc = _resolve_btc(conn, on, args.btc)
    _banner(cs, btc)

    targets = [float(t) for t in args.targets.split(",")]
    bases = [C.PriceBasis(b) for b in args.bases.split(",")]

    header = f"  {'mNAV 目標':>10} " + " ".join(f"{b.value:>14}" for b in bases)
    print(f"§7.3 對照表 @ {on}  (BTC ${btc:,.0f})\n")
    print(header)
    print("  " + "-" * (len(header) - 2))
    for row in C.implied_price_table(cs, btc, targets, bases):
        cells = []
        for b in bases:
            v = row[b.value]
            cells.append(f"{'—':>14}" if v is None else f"${v:>13,.2f}")
        print(f"  {row['target_mnav']:>9.2f}x " + " ".join(cells))
    print()
    for b in bases:
        print(f"  {b.value:<7} = {BASIS_HELP[b.value]}")
    return 0


def cmd_snapshot(args, conn) -> int:
    on = dt.date.fromisoformat(args.date)
    cs = _structure(conn, on)
    btc = _resolve_btc(conn, on, args.btc)
    row = conn.execute(
        "SELECT mstr_close_usd FROM market_daily WHERE date <= ? "
        "AND mstr_close_usd IS NOT NULL ORDER BY date DESC LIMIT 1",
        (on.isoformat(),)).fetchone()
    mstr = args.mstr if args.mstr is not None else (row["mstr_close_usd"] if row else None)
    if mstr is None:
        raise SystemExit("找不到 MSTR 股價,請用 --mstr 指定")
    _banner(cs, btc)
    print(f"MSTR 股價      : ${mstr:,.2f}\n")

    print("五種 mNAV(§4.1 —— 全部都算,不能只看一個):\n")
    readings = C.all_mnavs(cs, btc, mstr)
    for v in C.MNavVariant:
        r = readings.get(v.value)
        if r is None:
            print(f"  {v.value:<11} 不可用(缺 FDSO 等欄位,見 findings/fdso_coverage)")
            continue
        flag = "  ← 跨到 1.0x 另一側" if (r.value - 1) * (
            readings["basic"].value - 1) < 0 else ""
        print(f"  {r}{flag}")
        if r.note:
            print(f"      {r.note}")
    vals = [r.value for r in readings.values()]
    if min(vals) < 1.0 < max(vals):
        print(f"\n  ⚠️ 同一天同一股價,讀數橫跨 1.0x 兩側 "
              f"({min(vals):.2f}x – {max(vals):.2f}x)。引用時務必附上 variant。")

    print("\n每股 BTC(§8.2 —— 三個不同分母):")
    if cs.shares_assumed_diluted:
        g = C.gross_bps_sats(cs.btc_held, cs.shares_assumed_diluted)
        print(f"  Gross BPS        {g:>12,.0f} sats  = ${g/1e8*btc:>10,.2f}  "
              f"(÷ assumed diluted {_m(cs.shares_assumed_diluted)})")
    if cs.shares_fdso:
        nr = C.net_reserve_per_share_from(cs, btc, mstr)
        print(f"  Net BPS          {C.net_bps_sats(nr, btc):>12,.0f} sats  "
              f"= ${nr:>10,.2f}  (÷ FDSO {_m(cs.shares_fdso)})")
        print(f"  phantom growth   {C.phantom_growth_sats(cs, btc, mstr):>12,.0f} sats"
              f"  ← Gross 與 Net 的落差")
        print(f"  amplification    {C.amplification(cs, btc, mstr):>12,.2f}x")
    if cs.shares_basic:
        print(f"  CEBE             {C.cebe_sats(cs, btc, C.ClaimsBasis.CEBETRACKER, mstr):>12,.0f} sats"
              f"  (÷ basic {_m(cs.shares_basic)})")
        print(f"  Claims %         {C.claims_pct(cs, btc, C.ClaimsBasis.CEBETRACKER, mstr)*100:>12,.1f}%")

    if cs.annual_obligations_usd:
        arr = C.btc_arr_breakeven(cs.annual_obligations_usd, cs.btc_nav_usd(btc))
        print(f"\n年度固定義務      ${cs.annual_obligations_usd/1e9:,.3f}B"
              f"  → BTC ARR breakeven {arr*100:.2f}%")
    return 0


def cmd_breakeven(args, conn) -> int:
    on = dt.date.fromisoformat(args.date)
    cs = _structure(conn, on)
    btc = _resolve_btc(conn, on, args.btc)
    _banner(cs, btc)
    print("§6.3 Break-even —— 三種定義都對,只是求償權定義不同:\n")
    labels = {
        "company": "毛額含 STRE(債 + 優先股,不扣現金)",
        "mnav_com": "mnav.com(毛額,漏掉 STRE)",
        "cebetracker": "cebetracker(扣資產負債表現金)",
        "company_net_reserve": "Strategy 官方(扣 USD Reserve)",
    }
    for basis, price in sorted(C.break_even_all_bases(cs, 0.0).items(),
                               key=lambda kv: kv[1]):
        claims = C.net_senior_claims_usd(cs, C.ClaimsBasis(basis), 0.0)
        buffer = btc / price if price > 0 else float("inf")
        print(f"  ${price:>10,.0f}   求償權 ${claims/1e9:>6.2f}B   "
              f"緩衝 {buffer:>5.2f}x   {labels[basis]}")
    print("\n  ⚠️ 系統不能只顯示一個(§6.3)。緩衝 = 目前 BTC 價 ÷ break-even。")
    return 0


def cmd_findings(args, conn) -> int:
    findings = DB.load_findings(conn)
    if not findings:
        raise SystemExit("data_findings 是空的 —— 先跑 python3 build_db.py")
    print("建置期交叉驗證發現的來源資料問題(原值全部保留,未偷改):\n")
    for key, payload in sorted(findings.items()):
        items = payload if isinstance(payload, list) else [payload]
        for it in items:
            print(f"── {key}")
            for field in ("where", "problem", "observation", "explanation",
                          "impact", "implication", "resolution", "confidence"):
                if field in it:
                    print(f"   {field:<12}: {it[field]}")
            print()
    return 0


def cmd_decompose(args, conn) -> int:
    """§1.3 對數分解。"""
    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)

    def market(on: dt.date):
        r = conn.execute(
            "SELECT date, btc_close_usd, mstr_close_usd, mstr_high_usd FROM market_daily "
            "WHERE date <= ? AND mstr_close_usd IS NOT NULL "
            "ORDER BY date DESC LIMIT 1", (on.isoformat(),)).fetchone()
        if r is None:
            raise SystemExit(f"{on} 沒有市場資料")
        return r

    m0, m1 = market(start), market(end)
    cs0, cs1 = _structure(conn, start), _structure(conn, end)

    d = C.decompose_basic_mnav(
        start, end, m0["mstr_close_usd"], m1["mstr_close_usd"],
        m0["btc_close_usd"], m1["btc_close_usd"],
        cs0.btc_held, cs1.btc_held, cs0.shares_basic, cs1.shares_basic)

    print(f"§1.3 basic mNAV 對數分解  {start} → {end}\n")
    print(f"  basic mNAV  {d.mnav_start:.3f}x → {d.mnav_end:.3f}x"
          f"  (×{d.mnav_end/d.mnav_start:.3f})\n")
    print(f"  {'項目':<12} {'倍數':>10} {'log':>10}   說明")
    print("  " + "-" * 66)
    notes = {"MSTR 股價": "溢價收縮(主因)", "BTC 價格": "下跌反而墊高 mNAV",
             "股數稀釋": "BTC/share 上升 → 拖累"}
    for name, ratio, log in d.as_rows():
        print(f"  {name:<12} ×{ratio:>9.4f} {log:>+10.3f}   {notes[name]}")
    print("  " + "-" * 66)
    print(f"  {'淨效果':<12} ×{d.price_ratio*d.btc_ratio*d.shares_ratio:>9.4f} "
          f"{d.log_total:>+10.3f}")
    print(f"\n  還原檢查:{d.mnav_start:.3f} × {d.price_ratio*d.btc_ratio*d.shares_ratio:.4f}"
          f" = {d.reconstructed_mnav:.3f}x  (殘差 {d.residual:+.2e})")

    if start == D.SPLIT_CHECK[0]:
        print(f"\n  ⚠️ 起點用的是**收盤價** ${m0['mstr_close_usd']:,.2f};"
              f"規格書 §1.3 用的 $543 是當日**盤中高點**"
              f"(實際 high ${m0['mstr_high_usd']:,.2f})。")
        print(f"     用盤中高點會把壓縮幅度誇大約 37% —— 見 findings/ath_is_intraday。")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    today = dt.date.today().isoformat()
    ap = argparse.ArgumentParser(prog="mstr_cebe.cli",
                                 description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=DB.DEFAULT_DB)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, need_mnav=False):
        p.add_argument("--date", default=today, help="資本結構基準日(forward-fill)")
        p.add_argument("--btc", type=float, default=None, help="BTC 價格,預設用當日收盤")

    p = sub.add_parser("price", help="在給定 BTC 價與目標 mNAV 下的隱含股價")
    common(p)
    p.add_argument("--mnav", type=float, required=True)
    p.set_defaults(func=cmd_price)

    p = sub.add_parser("table", help="§7.3 對照表")
    common(p)
    p.add_argument("--targets", default="1.0,1.25,1.5,2.0,3.0")
    p.add_argument("--bases", default="basic,gross,net,cebe")
    p.set_defaults(func=cmd_table)

    p = sub.add_parser("snapshot", help="某日的五種 mNAV 與各項每股指標")
    common(p)
    p.add_argument("--mstr", type=float, default=None)
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("breakeven", help="三種 break-even 定義")
    common(p)
    p.set_defaults(func=cmd_breakeven)

    p = sub.add_parser("findings", help="來源資料的已知矛盾")
    p.set_defaults(func=cmd_findings)

    p = sub.add_parser("decompose", help="§1.3 basic mNAV 對數分解")
    p.add_argument("--from", dest="start", default="2024-11-21")
    p.add_argument("--to", dest="end", default=today)
    p.set_defaults(func=cmd_decompose)

    args = ap.parse_args(argv)
    conn = DB.connect(args.db)
    return args.func(args, conn)


if __name__ == "__main__":
    sys.exit(main())
