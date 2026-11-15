/** 頁面用的指標。求償權與恆等式只在 metrics/read.ts。 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { daily, N } from "../src/data";
import {
  claimsNetB, claimsPartsB, claimsStackB, formatIdentity, metricAt, runwayNow,
} from "../src/metrics/read";

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (p.endsWith(".ts")) out.push(p);
  }
  return out;
}

describe("淨求償權只從指標來", () => {
  it("每一天等於可轉債 + 優先股面額 − 現金", () => {
    for (let i = 0; i < N; i++) {
      const p = claimsPartsB(i);
      expect(metricAt("claims.cebe", i).value).toBeCloseTo(p.debt + p.pref - p.cash, 8);
      expect(claimsNetB(i)).toBeCloseTo(p.net, 8);
      expect(claimsStackB(i).top).toBeCloseTo(claimsNetB(i), 6);
    }
  });

  it("頁面與元件不再自己把債務和優先股相加", () => {
    const roots = ["src/pages", "src/components", "src/charts"];
    const bad: string[] = [];
    for (const root of roots) {
      for (const file of walk(root)) {
        const text = readFileSync(file, "utf8");
        if (/debt\[.*\]!?\s*\+|pref_total\[.*\]!?\s*\+/.test(text)) bad.push(file);
      }
    }
    expect(bad).toEqual([]);
  });
});

describe("三項恆等式", () => {
  it("顯示的三個因數相乘，與顯示股價相差不超過 1 分", () => {
    const misses: string[] = [];
    for (let i = 0; i < N; i++) {
      const f = formatIdentity(i);
      const product = Number(f.mnav) * Number(f.btcPerShare) * Number(f.btcPrice);
      if (Math.abs(product - Number(f.price)) > 0.01) {
        misses.push(`${daily.date[i]} ${product} vs ${f.price}`);
      }
    }
    expect(misses.slice(0, 3)).toEqual([]);
  });
});

describe("跑道", () => {
  it("分子是最新現金欄，分母寫明是 2026-08-24 的常數", () => {
    const r = runwayNow();
    expect(r.assetsB).toBeCloseTo(daily.cash[N - 1]!, 6);
    expect(r.numerator).toContain("美元資產");
    expect(r.numerator).not.toContain("美元儲備");
    expect(r.denominator).toContain("2026-08-24");
    expect(r.years).toBeCloseTo(r.assetsB / r.obligationsB, 8);
  });
});
