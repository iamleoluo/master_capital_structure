#!/usr/bin/env python3
"""建置資料庫:抓市場日線 → 驗證資料源 → seed §5 資本結構 → 算 mNAV 序列。

    python3 build_db.py [--start 2024-07-01] [--db mstr_cebe.sqlite] [--offline]

--offline 只做 seed 與驗證,不打 API(已有 DB 時可用)。
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

from mstr_cebe import core as C
from mstr_cebe import data as D
from mstr_cebe import db as DB
from mstr_cebe import fetch as F


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-07-01")
    ap.add_argument("--end", default=dt.date.today().isoformat())
    ap.add_argument("--db", default=DB.DEFAULT_DB)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)
    conn = DB.connect(args.db)
    failures = []

    if not args.offline:
        print(f"→ 抓 BTC 日線 (binance) {start} .. {end}")
        try:
            btc = F.fetch_btc_binance(start, end)
        except RuntimeError as exc:
            print(f"  binance 失敗 ({exc}),改用 coinbase 備援")
            btc = F.fetch_btc_coinbase(start, end)
        print(f"  {len(btc)} 根,{btc[0].date} .. {btc[-1].date}")

        print(f"→ 抓 MSTR 日線 (yahoo chart) {start} .. {end}")
        mstr = F.fetch_mstr_yahoo(start, end)
        print(f"  {len(mstr)} 根,{mstr[0].date} .. {mstr[-1].date}")

        # split 檢查要 2024-11-21,若起始日晚於該日則單獨補抓
        split_date = D.SPLIT_CHECK[0]
        split_bars = mstr
        if start > split_date:
            split_bars = F.fetch_mstr_yahoo(split_date - dt.timedelta(days=3),
                                            split_date + dt.timedelta(days=3))

        print("\n=== 資料源驗證(§9 步驟 2)===")
        for rep in (F.verify_mstr_against_fixture(mstr),
                    F.verify_split(split_bars),
                    F.verify_btc_anchors(btc)):
            print(" ", rep.summary())
            for day, exp, got, rel in rep.mismatched[:6]:
                print(f"      MISMATCH {day}: 期望 {exp:,.2f} 實得 {got:,.2f} ({rel*100:.2f}%)")
            for row in rep.advisory[:6]:
                day, exp, got, rel, tier = row
                print(f"      advisory (Tier {tier}) {day}: 規格書 ~{exp:,.0f} "
                      f"實得 {got:,.0f} ({rel*100:+.2f}%)")
            if not rep.ok:
                failures.append(rep.name)

        n = DB.upsert_market_daily(conn, btc=btc, mstr=mstr)
        print(f"\n→ market_daily 寫入 {n} 筆")

    print("→ seed capital_structure(§5)")
    rows = DB.seed_capital_structure(conn)
    print(f"  {rows} 個時點")

    structures = DB.load_capital_structures(conn)
    print(f"  讀回 {len(structures)} 筆,申報日:"
          + ", ".join(c.as_of.isoformat() for c in structures))

    # ---- 算日頻 mNAV 序列 ----
    print("\n→ 計算日頻 mNAV(forward-fill 資本結構)")
    market = DB.load_market_daily(conn)
    first_structure = min(c.as_of for c in structures)
    stored = 0
    for row in market:
        day = dt.date.fromisoformat(row["date"])
        if day < first_structure or row["btc_close_usd"] is None \
                or row["mstr_close_usd"] is None:
            continue
        base = C.as_of_structure(structures, day)
        readings = C.all_mnavs(base, row["btc_close_usd"], row["mstr_close_usd"])
        # as_of_structure 會把 as_of 改成查詢日,readings 因此帶正確日期
        stored += DB.store_mnav_readings(
            conn, readings.values(),
            structure_as_of=day,
            claims_basis=C.ClaimsBasis.CEBETRACKER.value,
            cash_source=C.CashSource.BALANCE_SHEET.value,
            is_forward_fill="forward-filled" in base.note)
    print(f"  寫入 {stored} 筆 mNAV 讀數")

    counts = conn.execute(
        "SELECT variant, COUNT(*) n, MIN(as_of) a, MAX(as_of) b "
        "FROM mnav_readings GROUP BY variant ORDER BY variant").fetchall()
    for c in counts:
        print(f"    {c['variant']:<11} {c['n']:>5} 筆  {c['a']} .. {c['b']}")

    if failures:
        print(f"\n⚠️  驗證未通過:{failures}")
        return 1
    print("\n✅ 建置完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
