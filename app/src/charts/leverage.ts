/** 槓桿曲線 —— 定價頁的主圖。
 *
 * 核心觀念:求償權的面額固定在美元,普通股拿的是**殘值**。
 * 所以每股含幣量 = (總持幣 − 求償權/BTC價) / 股數,是 BTC 價格的遞增函數:
 *   BTC 跌 → 求償權吃掉更多幣 → 每股含幣縮水
 *   BTC 漲 → 求償權在幣計價下縮小 → 每股含幣自己長回來,一顆都不用多買
 *
 * 曲線的上方漸近線就是「完全沒有求償權」的每股含幣(gross BPS),
 * 曲線與漸近線的落差就是求償權當下吃掉的部分 —— 那個落差會隨 BTC 上漲而收斂。
 */
import { daily, N } from "../data";
import { linear } from "../lib/scale";
import { line, path, svg, text } from "../lib/svg";
import { usd0 } from "../lib/format";

const W = 900, PL = 66, PR = 108, PT = 24, PB = 40;

export interface Basis {
  held: number; claims: number; shares: number; px0: number; date: string;
}

/** 取最新一天的資本結構當基準。 */
export function latestBasis(): Basis {
  const i = N - 1;
  return {
    held: daily.held[i]!,
    claims: (daily.debt[i]! + daily.pref_total[i]! - daily.cash[i]!) * 1e9,
    shares: daily.shares[i]! * 1e6,
    px0: daily.btc[i]!,
    date: daily.date[i]!,
  };
}

export const commonBtc = (b: Basis, px: number) => Math.max(0, b.held - b.claims / px);
export const commonSats = (b: Basis, px: number) => (commonBtc(b, px) / b.shares) * 1e8;
export const grossSats = (b: Basis) => (b.held / b.shares) * 1e8;
export const perShareUsd = (b: Basis, px: number) => Math.max(0, b.held * px - b.claims) / b.shares;
export const breakEven = (b: Basis) => b.claims / b.held;
export const amplification = (b: Basis, px: number) => {
  const nav = b.held * px;
  return nav > b.claims ? nav / (nav - b.claims) : Infinity;
};

// ---------------------------------------------------------------------------
// 情境模擬:槓桿下限再融資 + mNAV 溢價 + 溢價增發的複利效果
//
// 三段機制,依序疊加:
//
// 1. 槓桿下限再融資 —— 固定求償權時,槓桿倍數 A = NAV/(NAV-求償權) 會隨 BTC
//    價格上升而自然下降(分母的比例變小)。若設定不能低於某個下限 L,一旦
//    觸價就假設公司持續增發 STRC 買幣,把 A 精確釘在 L。可以證明(見程式庫
//    README 或對話記錄的推導,已用 20 萬步離散模擬驗證誤差 <0.0001%):
//    在這個機制下,普通股殘值precisely依 (px/觸發價)^L 這個冪次成長 ——
//    跟固定倍數的槓桿 ETF 是同一個數學結構。
//
// 2. mNAV 溢價/折價 —— 市場實際付的股價 = mNAV倍數 × 每股殘值(CEBE 公允值)。
//
// 3. 溢價增發的複利效果 —— 若 mNAV > 1,用市價增發 X% 的股數、募到的錢全部
//    拿去買幣,對「既有股東」是增值的:新股東用溢價買進,多付的部分等於
//    直接分給所有股東。公式(見推導):
//      新每股殘值 = 舊每股殘值 × (1 + X·mNAV) / (1 + X)
//    mNAV=1 時公式=1(增發無感);mNAV>1 時是加值;mNAV<1 時反而稀釋。
// ---------------------------------------------------------------------------

export interface ScenarioParams {
  /** 槓桿下限(放大倍數的下限)。設 1 或以下代表不啟用再融資機制。 */
  leverageFloor: number;
  /** 市場付的 mNAV 倍數(CEBE 基準,1 = 公允值)。 */
  mnav: number;
  /** 假設額外用 ATM 溢價增發的股數比例(0–1)。 */
  atmDilution: number;
}

/** 槓桿下限首次觸發的 BTC 價格。floor<=1 時視為不啟用,回傳 +Infinity。 */
export function triggerPrice(b: Basis, floor: number): number {
  if (floor <= 1) return Infinity;
  const navAtTrigger = (floor * b.claims) / (floor - 1);
  return navAtTrigger / b.held;
}

/** 套用槓桿下限機制後的普通股殘值(美元)。價格未觸發下限前等同原本的殘值。 */
export function leveredResidualUsd(b: Basis, px: number, floor: number): number {
  const pxStar = triggerPrice(b, floor);
  if (!Number.isFinite(pxStar) || px <= pxStar) return perShareUsd(b, px) * b.shares;
  const navStar = b.held * pxStar;
  const residualStar = navStar / floor;
  return residualStar * Math.pow(px / pxStar, floor);
}

/** 套用溢價增發的複利效果後的(殘值, 股數)。dilution<=0 時原樣返回。 */
export function applyAtmAccretion(
  residualUsd: number, shares: number, mnav: number, dilution: number,
): { residual: number; shares: number } {
  if (dilution <= 0) return { residual: residualUsd, shares };
  const factor = (1 + dilution * mnav) / (1 + dilution);
  const newShares = shares * (1 + dilution);
  // 反推:新殘值 = 新每股殘值 × 新股數 = (舊每股殘值×factor) × 新股數
  const newPerShare = (residualUsd / shares) * factor;
  return { residual: newPerShare * newShares, shares: newShares };
}

export interface ScenarioResult {
  residualUsd: number; shares: number; perShareUsd: number; perShareSats: number;
  marketPrice: number; triggeredReleverage: boolean; triggerPx: number;
  amp: number;
}

/** 完整情境:給定目標 BTC 價與三個參數,算出市場股價與每股數字。 */
export function runScenario(b: Basis, px: number, p: ScenarioParams): ScenarioResult {
  const pxStar = triggerPrice(b, p.leverageFloor);
  const residual0 = leveredResidualUsd(b, px, p.leverageFloor);
  const { residual, shares } = applyAtmAccretion(residual0, b.shares, p.mnav, p.atmDilution);
  const perShare = shares > 0 ? residual / shares : 0;
  return {
    residualUsd: residual, shares, perShareUsd: perShare,
    perShareSats: (perShare / px) * 1e8,
    marketPrice: p.mnav * perShare,
    triggeredReleverage: px > pxStar,
    triggerPx: pxStar,
    amp: px <= pxStar ? amplification(b, px) : p.leverageFloor,
  };
}

export interface LeverageOpts {
  scenarioPx: number; loPx?: number; hiPx?: number; params: ScenarioParams;
}

export function drawLeverage(el: HTMLElement, b: Basis, o: LeverageOpts,
                             H = 330): void {
  const lo = o.loPx ?? 20_000, hi = o.hiPx ?? 300_000;
  const p = o.params;
  const gross = grossSats(b);

  const scenSats = (px: number) => runScenario(b, px, p).perShareSats;
  const maxY = Math.max(gross, scenSats(hi)) * 1.06;
  const x = linear([lo, hi], [PL, W - PR]);
  const y = linear([0, maxY], [H - PB, PT]);

  const natPts: Array<[number, number]> = [];
  const scenPts: Array<[number, number]> = [];
  for (let i = 0; i <= 220; i++) {
    const px = lo + ((hi - lo) * i) / 220;
    natPts.push([x(px), y(commonSats(b, px))]);
    scenPts.push([x(px), y(scenSats(px))]);
  }

  const parts: string[] = [];

  parts.push(line(PL, y(gross), W - PR, y(gross),
    { stroke: "var(--ink-3)", dash: "3,3", opacity: 0.75 }));
  parts.push(text(W - PR + 6, y(gross) + 3.5,
    `${Math.round(gross).toLocaleString()} sats`, { size: 10, fill: "var(--ink-3)", mono: true }));
  parts.push(text(W - PR + 6, y(gross) - 9, "無求償權上限", { size: 9.5, fill: "var(--ink-3)" }));

  for (let g = 0; g <= 4; g++) {
    const v = (maxY * g) / 4;
    parts.push(line(PL, y(v), W - PR, y(v), { opacity: 0.07 }));
    parts.push(text(PL - 8, y(v) + 3.5, (v / 1000).toFixed(0) + "K",
      { size: 9, anchor: "end", opacity: 0.55, mono: true }));
  }
  for (const px of [50_000, 100_000, 150_000, 200_000, 250_000, 300_000]) {
    if (px < lo || px > hi) continue;
    parts.push(line(x(px), PT, x(px), H - PB, { opacity: 0.06 }));
    parts.push(text(x(px), H - PB + 15, "$" + px / 1000 + "K",
      { size: 9.5, anchor: "middle", opacity: 0.55, mono: true }));
  }

  const hasScenario = p.leverageFloor > 1 || p.atmDilution > 0;

  // 自然衰減曲線(不再融資、不增發)—— 有情境模型時當灰色參考線
  const gap = natPts.map(([px]) => [px, y(gross)] as [number, number]);
  parts.push(`<path d="${path(natPts)} ${gap.slice().reverse().map((pt) => "L" + pt[0].toFixed(1) + "," + pt[1].toFixed(1)).join(" ")} Z" `
    + `fill="var(--c2)" opacity=".14"/>`);
  parts.push(`<path d="${path(natPts)}" fill="none" stroke="${hasScenario ? "var(--ink-3)" : "var(--equity)"}" `
    + `stroke-width="${hasScenario ? 1.6 : 2.6}" stroke-dasharray="${hasScenario ? "3,3" : "none"}" opacity="${hasScenario ? 0.7 : 1}"/>`);
  if (hasScenario) {
    parts.push(text(x(hi) - 4, y(commonSats(b, hi)) - 8, "不做任何事",
      { size: 9.5, anchor: "end", fill: "var(--ink-3)" }));
  }

  // 情境曲線(槓桿下限 + mNAV + ATM 增值)
  if (hasScenario) {
    parts.push(`<path d="${path(scenPts)}" fill="none" stroke="var(--equity)" stroke-width="2.6"/>`);
    parts.push(text(x(hi) - 4, y(scenSats(hi)) + 14, "情境模擬",
      { size: 9.5, anchor: "end", fill: "var(--equity)", weight: 600 }));
  }

  // 觸發槓桿下限的價格
  const pxStar = triggerPrice(b, p.leverageFloor);
  if (Number.isFinite(pxStar) && pxStar >= lo && pxStar <= hi) {
    parts.push(line(x(pxStar), PT, x(pxStar), H - PB, { stroke: "var(--c3)", dash: "2,3", width: 1.2 }));
    parts.push(text(x(pxStar) - 5, PT + 11, `${p.leverageFloor.toFixed(2)}x 觸發 ${usd0(pxStar)}`,
      { size: 9.5, anchor: "end", fill: "var(--c3)", weight: 600 }));
  }

  const be = breakEven(b);
  if (be >= lo && be <= hi) {
    parts.push(line(x(be), PT, x(be), H - PB, { stroke: "var(--bad)", dash: "2,3", width: 1.2 }));
    parts.push(text(x(be) + 5, PT + 24, `歸零 ${usd0(be)}`, { size: 9.5, fill: "var(--bad)", weight: 600 }));
  }

  const todayY = hasScenario ? y(runScenario(b, b.px0, p).perShareSats) : y(commonSats(b, b.px0));
  parts.push(`<circle cx="${x(b.px0).toFixed(1)}" cy="${todayY.toFixed(1)}" `
    + `r="4.5" fill="var(--ink)" stroke="var(--surface)" stroke-width="2"/>`);
  parts.push(text(x(b.px0), todayY + 19, "今天", { size: 9.5, anchor: "middle", opacity: 0.7 }));

  const sp = Math.min(hi, Math.max(lo, o.scenarioPx));
  const spSats = hasScenario ? runScenario(b, sp, p).perShareSats : commonSats(b, sp);
  parts.push(`<circle cx="${x(sp).toFixed(1)}" cy="${y(spSats).toFixed(1)}" `
    + `r="5.5" fill="var(--equity)" stroke="var(--surface)" stroke-width="2"/>`);
  parts.push(line(x(sp), y(spSats), x(sp), H - PB, { stroke: "var(--equity)", dash: "2,2", opacity: 0.5 }));
  parts.push(text(x(sp), y(spSats) - 12, `${Math.round(spSats).toLocaleString()} sats`,
    { size: 11, anchor: "middle", fill: "var(--equity)", weight: 700, mono: true }));

  parts.push(text(PL, PT - 8, "普通股每股含幣量(sats)", { size: 10, opacity: 0.65 }));
  parts.push(text(W - PR, H - 6, "BTC 價格", { size: 10, anchor: "end", opacity: 0.6 }));

  el.innerHTML = svg(W, H, parts.join(""),
    "普通股每股含幣量隨 BTC 價格上升的曲線,含槓桿下限再融資與 mNAV 增發情境模擬");
}
