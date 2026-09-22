/** 階段時間軸條 —— 橫跨完整資料範圍,把四個階段畫成連續色塊。
 *
 *  目的是讓人一眼看出「現在在第幾段、每段有多長」,並且點一下就能跳到該則。
 *  底下疊一條 CEBE 走勢(同一個時間軸),讓分期與實際後果對得起來 ——
 *  光看色塊看不出哪一段對股東是好的。 */
import { chronicle, daily, N } from "../data";
import { CW, PAD_L, PAD_R } from "../lib/frame";
import { linear, extent } from "../lib/scale";
import { path, svg, text } from "../lib/svg";

const H = 86;
const BAND_TOP = 18;
const BAND_H = 26;
const LINE_TOP = BAND_TOP + BAND_H + 6;
const LINE_H = 30;

/** 四段用不同色相,語意上對應「對普通股是好是壞」。 */
const ERA_FILL = ["var(--c3)", "var(--c1)", "var(--bad)", "var(--good)"];

export function eraColor(i: number): string {
  return ERA_FILL[i % ERA_FILL.length]!;
}

export function drawEraStrip(el: HTMLElement): void {
  const plotW = CW - PAD_L - PAD_R;
  const x = (i: number) => PAD_L + (plotW * i) / Math.max(1, N - 1);

  const cebe = daily.date.map((_, i) =>
    (daily.common_btc[i]! / (daily.shares[i]! * 1e6)) * 1e8);
  const [lo, hi] = extent(cebe, 0.9, 1.1);
  const y = linear([lo, hi], [LINE_TOP + LINE_H, LINE_TOP]);

  const parts: string[] = [];

  chronicle.forEach((e, idx) => {
    const [a, b] = e.range;
    const x0 = x(a), x1 = x(b);
    const w = Math.max(1, x1 - x0);
    parts.push(
      `<rect x="${x0.toFixed(1)}" y="${BAND_TOP}" width="${w.toFixed(1)}" height="${BAND_H}" `
      + `fill="${eraColor(idx)}" opacity="${e.ongoing ? 0.85 : 0.55}" `
      + `data-era="${e.id}" class="era-block"><title>${e.title}(${e.start} → `
      + `${e.ongoing ? "進行中" : e.end})</title></rect>`);
    // 夠寬才放標籤,否則會疊在一起
    if (w > 62) {
      parts.push(text(x0 + w / 2, BAND_TOP + BAND_H / 2 + 4, e.title,
        { size: 10.5, anchor: "middle", fill: "var(--paper)", weight: 600 }));
    }
    if (idx > 0) {
      parts.push(`<line x1="${x0.toFixed(1)}" y1="${BAND_TOP}" x2="${x0.toFixed(1)}" `
        + `y2="${LINE_TOP + LINE_H}" stroke="var(--line-2)" stroke-width="1"/>`);
    }
  });

  const pts: Array<[number, number]> = [];
  for (let i = 0; i < N; i++) pts.push([x(i), y(cebe[i]!)]);
  parts.push(`<path d="${path(pts)}" fill="none" stroke="var(--equity)" stroke-width="1.5"/>`);
  parts.push(text(PAD_L, LINE_TOP - 3, "CEBE 每股含幣量",
    { size: 9, fill: "var(--ink-3)" }));

  parts.push(text(PAD_L, H - 3, daily.date[0]!, { size: 9, fill: "var(--ink-3)", mono: true }));
  parts.push(text(CW - PAD_R, H - 3, daily.date[N - 1]!,
    { size: 9, anchor: "end", fill: "var(--ink-3)", mono: true }));

  el.innerHTML = svg(CW, H, parts.join(""),
    "資本結構分期時間軸,色塊為各階段,下方折線是同期的 CEBE 每股含幣量");
}
