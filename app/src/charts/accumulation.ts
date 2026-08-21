/** BTC 累積持有量 + 逐週買賣(依融資來源上色)。
 *
 * 這張圖用的是**逐週真實觀測**(90 個 8-K 揭露點),不是插值後的日頻序列 ——
 * 所以持有量畫成階梯線並標出觀測點,不假裝每天都知道。
 * X 軸因此是「日期」而非日頻索引,與其他圖共用時間範圍但不共用索引。
 */
import { daily, meta, weekly } from "../data";
import type { SecurityTicker, Week } from "../types";
import { btc as fmtBtc, mn, usd0 } from "../lib/format";
import { linear } from "../lib/scale";
import { line, path, rect, svg, text } from "../lib/svg";

const CW = 880, PAD_L = 62, PAD_R = 18;

/** 融資來源 → 顏色。沿用清償順位色階,普通股用暖色。 */
export const FUNDING_COLOR: Record<string, string> = {
  MSTR: "var(--equity)",
  STRF: "var(--c1)",
  STRC: "var(--c2)",
  STRK: "var(--c3)",
  STRD: "var(--c4)",
  STRE: "var(--c5)",
  btc_sale: "var(--bad)",
  unspecified: "var(--ink-3)",
};

export const FUNDING_LABEL: Record<string, string> = {
  MSTR: "MSTR 普通股 ATM",
  STRF: "STRF", STRC: "STRC", STRK: "STRK", STRD: "STRD", STRE: "STRE",
  btc_sale: "賣幣",
  unspecified: "8-K 未指名",
};

const rows = (): Week[] => weekly.filter((w) => w.holdings != null);

/** 一週的主要融資來源(用於長條上色)。多來源時取清償順位最劣後那個,
 *  因為那才是實際承擔稀釋的一方;賣幣與未指名各自單獨標色。 */
function primarySource(w: Week): string {
  if (w.source_kind === "btc_sale" || (w.delta ?? 0) < 0) return "btc_sale";
  if (!w.funding.length) return "unspecified";
  const order: SecurityTicker[] = ["MSTR", "STRE", "STRD", "STRK", "STRC", "STRF"];
  for (const o of order) if (w.funding.includes(o)) return o;
  return "unspecified";
}

export interface AccumGeo {
  xOf(date: string): number;
  yHold: ReturnType<typeof linear>;
  rows: Week[];
  h: number;
}

export function drawAccumulation(el: HTMLElement, h = 340): AccumGeo {
  const data = rows();
  const padT = 18, padB = 120;          // 下方留給買賣長條
  const barTop = h - padB + 14;
  const barBottom = h - 28;
  const plotBottom = h - padB;

  const t0 = new Date(daily.date[0]!).getTime();
  const t1 = new Date(daily.date[daily.date.length - 1]!).getTime();
  const xOf = (d: string) =>
    PAD_L + ((new Date(d).getTime() - t0) / (t1 - t0)) * (CW - PAD_L - PAD_R);

  const maxHold = Math.max(...data.map((w) => w.holdings!)) * 1.08;
  const yHold = linear([0, maxHold], [plotBottom, padT]);

  const deltas = data.map((w) => w.delta ?? 0);
  const maxAbs = Math.max(...deltas.map(Math.abs), 1);
  const yBar = linear([-maxAbs, maxAbs], [barBottom, barTop]);

  const parts: string[] = [];

  for (const v of [0, maxHold / 2, maxHold]) {
    parts.push(line(PAD_L, yHold(v), CW - PAD_R, yHold(v), { opacity: 0.08 }));
    parts.push(text(PAD_L - 7, yHold(v) + 3.5, (v / 1000).toFixed(0) + "K",
      { size: 9, anchor: "end", opacity: 0.55, mono: true }));
  }

  // 年月刻度
  const seen = new Set<string>();
  for (const d of daily.date) {
    const ym = d.slice(0, 7), mm = ym.slice(5, 7);
    if (d.slice(8, 10) !== "01" || seen.has(ym)) continue;
    if (mm !== "01" && mm !== "07") continue;
    seen.add(ym);
    parts.push(line(xOf(d), padT, xOf(d), plotBottom, { opacity: 0.06 }));
    parts.push(text(xOf(d), h - 8, ym,
      { size: 9, anchor: "middle", opacity: 0.5, mono: true }));
  }

  // 階梯線 —— 觀測之間持平,到下一次揭露才跳
  const steps: Array<[number, number]> = [];
  data.forEach((w, i) => {
    const x = xOf(w.week_end), y = yHold(w.holdings!);
    if (i > 0) steps.push([x, yHold(data[i - 1]!.holdings!)]);
    steps.push([x, y]);
  });
  const lastW = data[data.length - 1]!;
  steps.push([xOf(daily.date[daily.date.length - 1]!), yHold(lastW.holdings!)]);

  const area = steps.map((p, i) => (i === 0 ? "M" : "L") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ")
    + ` L ${xOf(daily.date[daily.date.length - 1]!).toFixed(1)},${yHold(0).toFixed(1)}`
    + ` L ${xOf(data[0]!.week_end).toFixed(1)},${yHold(0).toFixed(1)} Z`;
  parts.push(`<path d="${area}" fill="var(--c3)" opacity=".14"/>`);
  parts.push(`<path d="${path(steps)}" fill="none" stroke="var(--c3)" stroke-width="1.8"/>`);

  // 真實觀測點
  for (const w of data) {
    parts.push(`<circle cx="${xOf(w.week_end).toFixed(1)}" cy="${yHold(w.holdings!).toFixed(1)}" `
      + `r="1.9" fill="var(--c3)" opacity=".8"/>`);
  }

  parts.push(text(PAD_L, padT - 4, "累計持有量(90 個 8-K 真實觀測點,階梯線)",
    { size: 9.5, opacity: 0.6 }));

  // 買賣長條
  parts.push(line(PAD_L, yBar(0), CW - PAD_R, yBar(0), { opacity: 0.25 }));
  parts.push(text(PAD_L, barTop - 5, "逐週買賣量(顏色 = 融資來源)",
    { size: 9.5, opacity: 0.6 }));
  const bw = Math.max(2.2, (CW - PAD_L - PAD_R) / data.length - 1.4);
  for (const w of data) {
    const d = w.delta ?? 0;
    if (!d) continue;
    const x = xOf(w.week_end) - bw / 2;
    const yTop = d > 0 ? yBar(d) : yBar(0);
    parts.push(rect(x, yTop, bw, Math.abs(yBar(d) - yBar(0)),
      FUNDING_COLOR[primarySource(w)] ?? "var(--ink-3)", { opacity: 0.9 }));
  }

  el.innerHTML = svg(CW, h, parts.join(""),
    "BTC 累計持有量階梯線與逐週買賣量長條,長條顏色代表融資來源");

  return { xOf, yHold, rows: data, h };
}

/** 圖例(HTML,非 SVG)。 */
export function accumulationLegend(): string {
  const used = new Set(rows().filter((w) => w.delta).map(primarySource));
  const order = ["MSTR", "STRF", "STRC", "STRK", "STRD", "STRE", "btc_sale", "unspecified"];
  return order.filter((k) => used.has(k)).map((k) =>
    `<span><i class="swatch" style="background:${FUNDING_COLOR[k]}"></i>${FUNDING_LABEL[k]}</span>`
  ).join("");
}

/** 原始資料表。 */
export function accumulationTable(): string {
  const data = rows().slice().reverse();
  const secs: SecurityTicker[] = ["MSTR", "STRF", "STRC", "STRK", "STRD"];
  const head = `<tr><th>週結束</th><th class="n">BTC 買賣</th><th class="n">累計持有</th>`
    + `<th class="n">均價</th><th>融資來源</th>`
    + secs.map((s) => `<th class="n">${s}</th>`).join("")
    + `<th class="n">合計募資</th></tr>`;

  const body = data.map((w) => {
    const d = w.delta;
    const dCell = d == null ? "—"
      : `<span style="color:${d > 0 ? "var(--good)" : d < 0 ? "var(--bad)" : "var(--ink-3)"}">`
        + (d > 0 ? "+" : "") + fmtBtc(d) + "</span>";
    // 沒買也沒賣的週次不該顯示「融資來源」—— 那週有募資但錢沒進幣,
    // 標成「募資未買幣」才不會誤導(2026 下半年很多週都是這種)
    const src = w.source_kind === "btc_sale" ? "賣幣"
      : !d ? `<span style="color:var(--ink-3)">募資未買幣</span>`
      : w.funding.length
        ? w.funding.join(" · ") + (w.funding_derived
            ? ` <span style="color:var(--ink-3);font-size:.72rem"`
              + ` title="8-K 敘述句未指名,由同一份文件的 ATM 表格推得">推得</span>`
            : "")
        : `<span style="color:var(--ink-3)">未指名</span>`;
    const cells = secs.map((s) => {
      const v = w.raised_m[s];
      return `<td class="n">${v ? mn(v) : "—"}</td>`;
    }).join("");
    return `<tr><td class="num">${w.week_end}</td><td class="n">${dCell}</td>`
      + `<td class="n">${w.holdings != null ? fmtBtc(w.holdings) : "—"}</td>`
      + `<td class="n">${w.avg_price ? usd0(w.avg_price) : "—"}</td>`
      + `<td style="font-size:.8rem">${src}</td>${cells}`
      + `<td class="n">${w.raised_total_m ? mn(w.raised_total_m) : "—"}</td></tr>`;
  }).join("");

  return `<table class="mini"><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

/** 摘要統計,給頁面上方的 tiles 用。 */
export function accumulationStats() {
  const data = rows();
  const buys = data.filter((w) => (w.delta ?? 0) > 0);
  const sells = data.filter((w) => (w.delta ?? 0) < 0);
  // 只有真的有進出幣的週次才需要「資金來源」,零交易週不列入分母
  const active = data.filter((w) => (w.delta ?? 0) !== 0);
  const stated = active.filter((w) => w.funding.length && !w.funding_derived);
  const derived = active.filter((w) => w.funding.length && w.funding_derived);
  const raised = data.reduce((s, w) => s + (w.raised_total_m ?? 0), 0);
  return {
    weeks: data.length,
    bought: buys.reduce((s, w) => s + w.delta!, 0),
    sold: Math.abs(sells.reduce((s, w) => s + w.delta!, 0)),
    buyWeeks: buys.length,
    sellWeeks: sells.length,
    activeWeeks: active.length,
    statedWeeks: stated.length,
    derivedWeeks: derived.length,
    coveredPct: active.length ? (stated.length + derived.length) / active.length : 0,
    raisedB: raised / 1000,
    latest: data[data.length - 1]?.holdings ?? 0,
    ipoCount: meta.ipos.length,
  };
}
