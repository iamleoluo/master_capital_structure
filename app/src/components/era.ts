/** 階段骨架 —— 一則大事記的數字部分。
 *
 *  **散文在 posts/,數字在這裡。** 文章寫的是「這一段發生了什麼」,
 *  指標、資金流、事件、圖表全部由管線算,所以它們不會隨文章一起過期。
 *
 *  由 pages/chronicle.ts 抽出來 —— 那一頁把散文與數字綁死在同一個檔案裡,
 *  要加一則就得改程式。現在散文是 posts/*.md,骨架是這個元件。 */
import type { Delta, Era } from "../types";
import { bn, btc as fmtBtc, mult, usd, usd0 } from "../lib/format";
import { drawPerShare, drawRiverUsd } from "../charts/timeseries";
import { drawRiverBtc } from "../charts/riverBtc";
import { zoomable } from "../lib/zoomable";

const sign = (v: number | null): string =>
  v == null ? "—" : (v >= 0 ? "+" : "") + v.toFixed(1) + "%";

type Polarity = "upGood" | "downGood" | "neutral";

function toneOf(v: number | null, pol: Polarity): string {
  if (v == null || pol === "neutral") return "flat";
  if (Math.abs(v) <= 0.05) return "flat";
  const good = pol === "upGood" ? v > 0 : v < 0;
  return good ? "up" : "down";
}

function row(label: string, d: Delta | null, fmt: (v: number) => string,
             hint = "", pol: Polarity = "upGood"): string {
  if (!d) return "";
  return `
    <tr>
      <td>${label}${hint ? `<span class="row-hint">${hint}</span>` : ""}</td>
      <td class="mono">${fmt(d.from)}</td>
      <td class="mono arrow">→</td>
      <td class="mono">${fmt(d.to)}</td>
      <td class="mono chg ${toneOf(d.pct, pol)}">${sign(d.pct)}</td>
    </tr>`;
}

function metricsTableRows(e: Era): string {
  const m = e.metrics;
  const sats = (v: number) => Math.round(v).toLocaleString("en-US");
  return `
    <div class="table-wrap"><table class="era-metrics">
      <thead><tr><th>指標</th><th>期初</th><th></th><th>期末</th><th>變化</th></tr></thead>
      <tbody>
        ${row("實現的 實得每股", m.cebe, sats,
          "決策 + 行情的合計結果")}
        ${row("帳面每股", m.grossBps, sats, "不扣求償權")}
        ${row("淨求償權", m.claims, (v) => `$${v.toFixed(2)}B`,
          "可轉債 + 優先股 − 現金。減少對普通股是好事", "downGood")}
        ${row("其中:優先股", m.pref, (v) => `$${v.toFixed(2)}B`, "", "downGood")}
        ${row("總持幣", m.held, (v) => fmtBtc(v) + " 顆")}
        ${row("在外股數", m.shares, (v) => v.toFixed(0) + "M",
          "增發是好是壞要看價格,不標紅綠", "neutral")}
        ${row("CEBE mNAV", m.mnavCebe, mult, "市場願付的倍數", "neutral")}
        ${row("BTC 價格", m.btcPrice, usd0)}
        ${row("MSTR 股價", m.mstrPrice, usd)}
        ${m.strcPrice ? row("STRC 價格", m.strcPrice, usd,
          `期間最低 $${m.strcPrice.low.toFixed(2)}(${m.strcPrice.lowDate})`) : ""}
      </tbody>
    </table></div>`;
}

function flowsLine(e: Era): string {
  const f = e.flows;
  const bits: string[] = [];
  if (f.btcBought) bits.push(`買入 ${fmtBtc(f.btcBought)} 顆`);
  if (f.btcSold) bits.push(`賣出 ${fmtBtc(f.btcSold)} 顆`);
  if (f.prefRaisedM) bits.push(`優先股募資 ${bn(f.prefRaisedM / 1000)}`);
  if (f.commonRaisedM) bits.push(`普通股 ATM 募資 ${bn(f.commonRaisedM / 1000)}`);
  if (f.prefRepurchasedShares) {
    const avg = f.prefRepurchasedM * 1e6 / f.prefRepurchasedShares;
    bits.push(`回購優先股 ${Math.round(f.prefRepurchasedShares).toLocaleString("en-US")} 股`
      + `／${bn(f.prefRepurchasedM / 1000)}(均價 ${usd(avg)})`);
  }
  if (!bits.length) return "";
  return `<div class="era-flows"><span class="k">期間資金流</span>${
    bits.map((b) => `<span class="flow-chip">${b}</span>`).join("")}</div>`;
}

function authorityLine(e: Era): string {
  const a = e.remainingAuthorityM;
  if (!a) return "";
  const bits: string[] = [];
  if (a.preferred != null) bits.push(`優先股回購剩餘授權 ${bn(a.preferred / 1000)}`);
  if (a.mstr != null) bits.push(`普通股回購剩餘授權 ${bn(a.mstr / 1000)}`);
  if (!bits.length) return "";
  return `<div class="era-flows"><span class="k">最新授權餘額</span>${
    bits.map((b) => `<span class="flow-chip">${b}</span>`).join("")}</div>`;
}

function eventsList(e: Era): string {
  if (!e.events.length) return "";
  return `
    <div class="era-events">
      <div class="k">期間內的事件</div>
      <ul>${e.events.map((ev) =>
        `<li><span class="mono">${ev.d}</span> ${ev.label}</li>`).join("")}</ul>
    </div>`;
}

const CHART_CAPTION: Record<string, string> = {
  perShare: "帳面每股vs CEBE —— 兩條線的落差就是求償權吃掉的部分",
  riverBtc: "BTC 計價的資本結構 —— 下半部是求償權吃掉的幣,上面那條帶子才是普通股的",
  riverUsd: "美元計價 —— 求償權堆疊加上 MSTR 市值,虛線是 BTC 總市值",
};

const CHART_FOR: Record<string, "perShare" | "riverBtc" | "riverUsd"> = {
  "converts-2024": "perShare",
  "preferred-stack-2025": "riverBtc",
  "credit-stress-2026": "riverUsd",
  "deleveraging-2026": "perShare",
};


/** 一則的數字區塊:指標表 + 資金流 + 授權餘額 + 期間事件。 */
export function eraSkeleton(e: Era): string {
  return metricsTableRows(e) + flowsLine(e) + authorityLine(e) + eventsList(e);
}

/** 圖表的掛載點。區間限縮到該階段 —— y 軸會自動縮放,
 *  所以短短四週的那一段也看得出波動,不會被兩年的尺度壓平。 */
export function eraChartSlot(e: Era): string {
  const kind = CHART_FOR[e.id] ?? "perShare";
  return `
    <div class="chart-block" style="margin:22px 0">
      <div class="chart-head"><div class="chart-label">${CHART_CAPTION[kind]}</div>
        <div class="chart-tools"></div></div>
      <div class="scroller"><div id="era-chart-${e.id}"></div></div>
    </div>`;
}

export function mountEraChart(root: HTMLElement, e: Era): (() => void) | null {
  const host = root.querySelector<HTMLElement>(`#era-chart-${e.id}`);
  if (!host) return null;
  const kind = CHART_FOR[e.id] ?? "perShare";
  const draw = (el: HTMLElement, h: number) => {
    if (kind === "riverBtc") drawRiverBtc(el, h, false, e.range);
    else if (kind === "riverUsd") drawRiverUsd(el, h, e.range);
    else drawPerShare(el, h, e.range);
  };
  const handle = zoomable(host, `${e.title} — ${CHART_CAPTION[kind]}`, draw,
    { inlineHeight: 220, zoomHeight: 540 });
  return () => handle.destroy();
}
