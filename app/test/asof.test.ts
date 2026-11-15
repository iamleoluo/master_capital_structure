/** 欄位截至日。持幣走週頻階梯，不再把最舊欄位的天數畫在持幣上。 */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { daily, N } from "../src/data";
import { freshness } from "../src/metrics/asof";
import { metricAt } from "../src/metrics/read";

const last = N - 1;

describe("截至日", () => {
  it("最後一天的可轉債沿用 2026-06-30", () => {
    const f = freshness("claims.debt", last);
    expect(f.method).toBe("carry");
    expect(f.asOf).toBe("2026-06-30");
  });

  it("股數與現金欄停在自己的最後變動日", () => {
    expect(freshness("shares.basic", last)).toMatchObject({ method: "carry", asOf: "2026-08-21" });
    expect(freshness("claims.cash", last)).toMatchObject({ method: "spliced", asOf: "2026-09-28" });
  });

  it("股價與幣價是當日", () => {
    expect(freshness("price.mstr", last).method).toBe("observed");
    expect(freshness("price.btc", last).asOf).toBe(daily.date[last]);
  });

  it("持幣是週頻階梯，最後一天仍是 847,666", () => {
    const i = daily.date.indexOf("2024-11-22");
    expect(metricAt("btc.held", i).value).toBe(331200);
    expect(daily.held[i]).not.toBe(331200);
    expect(metricAt("btc.held", last).value).toBe(847666);
    expect(freshness("btc.held", last)).toMatchObject({ method: "step", asOf: "2026-09-27" });
  });

  it("頁面不再畫最舊欄位的天數徽章", () => {
    const ex = readFileSync("src/components/explorer.ts", "utf8");
    const q = readFileSync("src/pages/board/quantities.ts", "utf8");
    expect(ex).not.toContain("staleBadge");
    expect(ex).not.toContain("daily.stale");
    expect(q).not.toContain("插值");
    expect(q).not.toContain("staleness");
  });
});
