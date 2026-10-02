/** 定價頁情境模擬:TS 的實作必須與 Python 逐筆相同。
 *
 *  CLAUDE.md 第一條規則說金融計算一律在 Python 端,理由是
 *  **「同一條公式有兩個實作就會各自漂移,而 TS 那側沒有測試守著」**。
 *
 *  定價頁是互動模擬器(四個連續滑桿 ≈ 2.85 億種組合),不可能把結果
 *  預先算好塞進 JSON,所以 TS 這邊必須保留一份實作。這個檔案就是那個
 *  「守著」:公式的來源與推導在 `mstr_cebe/scenario.py`,這裡逐筆比對
 *  它產生的 360 筆黃金樣本(`python3 web/build_data.py` 產生)。
 *
 *  改了任一側的公式而沒有改另一側,這裡會紅。
 */
import { describe, expect, it } from "vitest";
import golden from "./scenario-golden.json";
import {
  amplification, grossSats, perShareUsd, runScenario, triggerPrice,
  type Basis,
} from "../src/charts/leverage";

const b: Basis = { ...golden.basis, date: golden.as_of };

describe("情境模擬與 Python 的 scenario.py 一致", () => {
  it(`逐筆比對 ${golden.cases.length} 筆黃金樣本`, () => {
    const bad: string[] = [];
    for (const c of golden.cases) {
      const r = runScenario(b, c.px, {
        leverageFloor: c.floor, mnav: c.mnav, atmDilution: c.dilution,
      });
      const near = (a: number, want: number, tol = 1e-6) =>
        Math.abs(a - want) <= Math.max(tol, Math.abs(want) * 1e-9);
      const tag = `px=${c.px} L=${c.floor} m=${c.mnav} d=${c.dilution}`;
      if (!near(r.perShareUsd, c.per_share_usd)) {
        bad.push(`${tag} 每股 ${r.perShareUsd} ≠ ${c.per_share_usd}`);
      }
      if (!near(r.perShareSats, c.per_share_sats, 1e-3)) {
        bad.push(`${tag} sats ${r.perShareSats} ≠ ${c.per_share_sats}`);
      }
      if (!near(r.marketPrice, c.market_price)) {
        bad.push(`${tag} 股價 ${r.marketPrice} ≠ ${c.market_price}`);
      }
      const wantTrigger = c.trigger_px ?? Infinity;
      if (Number.isFinite(wantTrigger) !== Number.isFinite(r.triggerPx)
          || (Number.isFinite(wantTrigger) && !near(r.triggerPx, wantTrigger, 1e-4))) {
        bad.push(`${tag} 觸發價 ${r.triggerPx} ≠ ${wantTrigger}`);
      }
      const wantAmp = c.amp ?? Infinity;
      if (Number.isFinite(wantAmp) !== Number.isFinite(r.amp)
          || (Number.isFinite(wantAmp) && !near(r.amp, wantAmp))) {
        bad.push(`${tag} 槓桿 ${r.amp} ≠ ${wantAmp}`);
      }
    }
    expect(bad.slice(0, 8)).toEqual([]);
  });

  it("樣本要跨過觸發價兩側 —— 否則釘不住冪次那一段", () => {
    const triggered = golden.cases.filter(
      (c) => c.trigger_px !== null && c.px > c.trigger_px);
    expect(triggered.length).toBeGreaterThan(50);
  });
});

describe("基準量與 Python 同源", () => {
  it("黃金樣本的基準就是 app/data 最新一天的資本結構", () => {
    expect(b.held).toBeGreaterThan(0);
    expect(b.claims).toBeGreaterThan(0);
    expect(triggerPrice(b, 1)).toBe(Infinity);          // 下限 ≤1 不是機制
    expect(amplification(b, b.px0)).toBeGreaterThan(1); // A 恆大於 1
  });

  it("沒有求償權時,每股殘值就是帳面每股", () => {
    const free: Basis = { ...b, claims: 0 };
    expect(perShareUsd(free, 100_000) / 100_000 * 1e8)
      .toBeCloseTo(grossSats(free), 6);
  });
});
