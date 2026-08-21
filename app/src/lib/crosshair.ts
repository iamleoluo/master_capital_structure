/** 游標標籤引擎。
 *
 * 先前的版本只畫一條線加圓點,讀者看不出哪條線是什麼、當下數值多少。
 * 這裡在游標處為每條序列渲染「名稱 + 數值」標籤,並解決標籤重疊:
 * 兩條線靠得很近時標籤會疊在一起,必須把它們推開。
 */
import { line, rect, text } from "./svg";

export interface SeriesLabel {
  /** 序列名稱,例如「BTC 價格」 */
  label: string;
  /** 已格式化好的數值字串 */
  value: string;
  /** CSS 色票,例如 "var(--btc)" */
  color: string;
  /** 該序列在游標日期的 y 座標(px) */
  y: number;
}

/** 依 y 排序後把重疊的標籤推開,並夾在繪圖區內。
 *
 * 標準做法:先由上往下掃一遍推開,再由下往上回掃一次修正超出下緣的情況。
 * 只跑單向會讓最下面的標籤被擠出圖外。
 */
export function layoutLabels(
  items: SeriesLabel[], plotTop: number, plotBottom: number, minGap = 15,
): SeriesLabel[] {
  const sorted = items.slice().sort((a, b) => a.y - b.y);
  const out = sorted.map((s) => ({ ...s }));

  for (let i = 1; i < out.length; i++) {
    const prev = out[i - 1]!, cur = out[i]!;
    if (cur.y - prev.y < minGap) cur.y = prev.y + minGap;
  }
  // 回掃:若最後一個超出下緣,整串往上擠回來
  const last = out[out.length - 1];
  if (last && last.y > plotBottom) {
    last.y = plotBottom;
    for (let i = out.length - 2; i >= 0; i--) {
      const next = out[i + 1]!, cur = out[i]!;
      if (next.y - cur.y < minGap) cur.y = next.y - minGap;
    }
  }
  const first = out[0];
  if (first && first.y < plotTop) {
    first.y = plotTop;
    for (let i = 1; i < out.length; i++) {
      const prev = out[i - 1]!, cur = out[i]!;
      if (cur.y - prev.y < minGap) cur.y = prev.y + minGap;
    }
  }
  return out;
}

export interface CrosshairOpts {
  x: number;
  plotTop: number;
  plotBottom: number;
  chartWidth: number;
  /** 日期表頭,畫在游標線頂端 */
  header?: string;
  labelWidth?: number;
  minGap?: number;
}

/** 產生完整的游標圖層:垂直線 + 各序列圓點 + 標籤組。 */
export function crosshair(items: SeriesLabel[], o: CrosshairOpts): string {
  const { x, plotTop, plotBottom, chartWidth,
          header, labelWidth = 108, minGap = 15 } = o;
  const parts: string[] = [];

  parts.push(line(x, plotTop, x, plotBottom,
    { stroke: "var(--ink)", opacity: 0.45, width: 1 }));

  for (const s of items) {
    parts.push(`<circle cx="${x.toFixed(1)}" cy="${s.y.toFixed(1)}" r="3.6" `
      + `fill="${s.color}" stroke="var(--surface)" stroke-width="1.5"/>`);
  }

  // 靠近右緣時標籤翻到左側,避免被裁掉
  const flip = x + labelWidth + 14 > chartWidth;
  const boxX = flip ? x - labelWidth - 10 : x + 10;

  const laid = layoutLabels(items, plotTop + 6, plotBottom - 4, minGap);
  for (const s of laid) {
    parts.push(rect(boxX, s.y - 7.5, labelWidth, 15, "var(--surface)",
      { opacity: 0.92, rx: 2 }));
    parts.push(rect(boxX, s.y - 7.5, 2.5, 15, s.color));
    parts.push(text(boxX + 6, s.y + 3.6, s.label, { size: 9.5, opacity: 0.75 }));
    parts.push(text(boxX + labelWidth - 5, s.y + 3.6, s.value,
      { size: 10, anchor: "end", mono: true, weight: 600 }));
  }

  if (header) {
    const hw = 74;
    const hx = Math.max(2, Math.min(chartWidth - hw - 2, x - hw / 2));
    parts.push(rect(hx, plotTop - 15, hw, 14, "var(--ink)", { rx: 2 }));
    parts.push(text(hx + hw / 2, plotTop - 4.5, header,
      { size: 9.5, anchor: "middle", fill: "var(--paper)", mono: true }));
  }

  return `<g class="crosshair" pointer-events="none">${parts.join("")}</g>`;
}
