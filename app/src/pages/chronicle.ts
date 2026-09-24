/** 大事記 —— 每一則是一個「公司在用不同工具」的階段。
 *
 *  敘述是人工撰寫的(mstr_cebe/chronicle.py),但每個數字都由管線在每次更新時
 *  從 daily.json 重算,所以資料一更新這一頁就跟著更新,不會出現文字與圖表打架。 */
import { chronicle, meta } from "../data";
import { drawEraStrip, eraColor } from "../charts/eraStrip";
import { drawPerShare, drawRiverUsd } from "../charts/timeseries";
import { drawRiverBtc } from "../charts/riverBtc";
import { toolBadges } from "../components/toolkit";
import { bn, btc as fmtBtc, mult, usd, usd0 } from "../lib/format";
import { zoomable } from "../lib/zoomable";
import type { Delta, Era } from "../types";
import type { PageFn } from "../router";

const sign = (v: number | null): string =>
  v == null ? "—" : (v >= 0 ? "+" : "") + v.toFixed(1) + "%";

/** 上色的方向性。不是每個指標都「漲了就是好」——
 *  求償權減少對普通股是好事,股數增減則要看增發價格,不該擅自標紅綠。 */
type Polarity = "upGood" | "downGood" | "neutral";

function toneOf(v: number | null, pol: Polarity): string {
  if (v == null || pol === "neutral") return "flat";
  if (Math.abs(v) <= 0.05) return "flat";
  const good = pol === "upGood" ? v > 0 : v < 0;
  return good ? "up" : "down";
}

/** 一列變化:期初 → 期末 + 變化率。 */
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

function metricsTable(e: Era): string {
  const sats = (v: number) => Math.round(v).toLocaleString("en-US");
  const sp = e.split;
  const tot = sp.market + sp.decision;
  const signed = (v: number) => (v >= 0 ? "+" : "") + sats(v);
  return `
    <div class="split-row">
      <div class="split-cell ${sp.decision >= 0 ? "good" : "bad"}">
        <div class="k">決策貢獻</div>
        <div class="v">${signed(sp.decision)}</div>
        <div class="d">sats／股。每筆操作用<b>當下</b>幣價評價,不含後見之明</div>
      </div>
      <div class="split-cell muted">
        <div class="k">行情貢獻</div>
        <div class="v">${signed(sp.market)}</div>
        <div class="d">sats／股。幣價讓固定美元的求償權漲縮,公司無從控制</div>
      </div>
      <div class="split-cell">
        <div class="k">合計 = 實現變化</div>
        <div class="v">${signed(tot)}</div>
        <div class="d">sats／股</div>
      </div>
    </div>`;
}

function metricsTableRows(e: Era): string {
  const m = e.metrics;
  const sats = (v: number) => Math.round(v).toLocaleString("en-US");
  return `
    <div class="table-wrap"><table class="era-metrics">
      <thead><tr><th>指標</th><th>期初</th><th></th><th>期末</th><th>變化</th></tr></thead>
      <tbody>
        ${row("實現的 CEBE 每股", m.cebe, sats,
          "決策 + 行情的合計結果")}
        ${row("CEBE @ 固定幣價", m.cebeFixed, sats,
          "用期末幣價回頭重估 —— 內含後見之明,僅供對照")}
        ${row("帳面每股(basic 股數)", m.grossBps, sats, "不扣求償權")}
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

/** 每一則配一張最能說明該階段機制的圖,區間限縮到該階段。 */
const CHART_FOR: Record<string, "perShare" | "riverBtc" | "riverUsd"> = {
  "converts-2024": "perShare",
  "preferred-stack-2025": "riverBtc",
  "credit-stress-2026": "riverUsd",
  "deleveraging-2026": "perShare",
};

const CHART_CAPTION: Record<string, string> = {
  perShare: "帳面每股(basic 股數)vs CEBE —— 兩條線的落差就是求償權吃掉的部分",
  riverBtc: "BTC 計價的資本結構 —— 下半部是求償權吃掉的幣,上面那條帶子才是普通股的",
  riverUsd: "美元計價 —— 求償權堆疊加上 MSTR 市值,虛線是 BTC 總市值",
};

/** 全期數字 —— 放在最前面,擋住「用三五個月論斷這套結構」。 */
function programPanel(): string {
  const p = meta.program;
  const m = p.metrics;
  const signed = (v: number) => (v >= 0 ? "+" : "") + Math.round(v).toLocaleString("en-US");
  const cell = (label: string, d: Delta, fmt: (v: number) => string,
                pol: Polarity = "upGood") => `
    <div class="tile">
      <div class="k">${label}</div>
      <div class="v ${toneOf(d.pct, pol)}">${sign(d.pct)}</div>
      <div class="d">${fmt(d.from)} → ${fmt(d.to)}</div>
    </div>`;
  const sats = (v: number) => Math.round(v).toLocaleString("en-US");

  return `
    <div class="program">
      <div class="program-span">全期 ${p.span[0]} → ${p.span[1]}</div>
      <div class="grid3" style="margin-bottom:14px">
        ${cell("純操作(CEBE @ 固定幣價)", m.cebeFixed, sats)}
        ${cell("BTC 價格", m.btcPrice, usd0)}
        ${cell("總持幣", m.held, (v) => fmtBtc(v) + " 顆")}
        ${cell("淨求償權", m.claims, (v) => `$${v.toFixed(2)}B`, "neutral")}
      </div>
      <p class="program-key">
        兩年多下來每股含幣量的變化,拆成決策與行情兩半之後:
        <b>決策貢獻 ${signed(p.split.decision)} sats,行情貢獻只有
        ${signed(p.split.market)} sats</b>。
        也就是說這段期間每股含幣量的成長<b>幾乎全部來自公司的作為</b>,
        比特幣自己的漲跌在兩年尺度上互相抵銷掉了。
        任何單一階段都只是這台機器的某一個轉速 ——
        各階段的決策成績見下方每一則的第一排。
      </p>
      <p class="lede" style="margin:0">${p.lede}</p>
      <div class="grid2" style="margin-top:18px">
        ${p.principles.map((x) => `
          <div class="principle">
            <h3>${x.t}</h3>
            <p>${x.b}</p>
          </div>`).join("")}
      </div>
    </div>`;
}

export const chroniclePage: PageFn = (root) => {
  const eras = [...chronicle].reverse();   // 最新在上,像新聞欄位

  root.innerHTML = `
    <div class="wrap">
      <div class="page-head">
        <p class="eyebrow">大事記</p>
        <h1>一套工具,四種市況</h1>
        <p class="lede">這不是一家被事件推著走的公司。五檔優先股的條款在發行當天就設定好了,
          市況決定的是<b>哪一根槓桿在當下划算</b>,不是公司有哪些槓桿。
          下面把兩年多切成幾個階段,每一段記錄它選了什麼、為什麼是那把工具、
          結構被改成什麼樣子。<b>敘述是人工寫的,但所有數字都在每次資料更新時重算。</b></p>
      </div>

      ${programPanel()}

      <div class="card flush" style="padding:14px 18px 6px;margin:26px 0">
        <div id="era-strip" class="era-strip"></div>
      </div>

      ${eras.map((e, revIdx) => {
        const idx = chronicle.length - 1 - revIdx;   // 原始順序的索引,用來配色
        const kind = CHART_FOR[e.id] ?? "perShare";
        return `
        <article class="era" id="era-${e.id}" style="--era-color:${eraColor(idx)}">
          <div class="era-head">
            <div class="era-when">
              <span class="mono">${e.start}</span>
              <span class="arrow">→</span>
              <span class="mono">${e.ongoing ? "進行中" : e.end}</span>
              <span class="era-days">${e.days} 天</span>
            </div>
            ${e.ongoing ? `<span class="badge live"><i class="dot"></i>進行中</span>` : ""}
          </div>
          <h2>${e.title}</h2>
          <p class="era-sub">${e.subtitle}</p>

          ${toolBadges(e.tools, e.toolsActive)}

          <div class="note" style="margin:14px 0 18px">
            <b>觸發</b> ${e.trigger}
          </div>

          ${metricsTable(e)}
          ${metricsTableRows(e)}
          ${flowsLine(e)}
          ${authorityLine(e)}

          <div class="chart-block" style="margin-top:20px">
            <div class="chart-head">
              <div class="chart-label">${CHART_CAPTION[kind]}</div>
              <div class="chart-tools"></div>
            </div>
            <div id="chart-${e.id}"></div>
          </div>

          ${e.body.map((p) => `<p class="era-body">${p}</p>`).join("")}
          ${e.watch ? `<div class="note key" style="margin-top:14px">
            <b>接下來看什麼</b> ${e.watch}</div>` : ""}
          ${eventsList(e)}
        </article>`;
      }).join("")}

      <p style="font-size:.8rem;color:var(--ink-3);margin-top:28px">
        分期是編輯判斷,不是演算法切出來的。管線每次更新會比對目前狀態與當期起點,
        在求償權變動超過 5%、優先股穿越面額、或出現新的政策斷點時提醒該重新檢視分期
        —— 提醒內容列在<a href="#/data-quality">資料品質</a>頁。</p>
    </div>`;

  drawEraStrip(root.querySelector<HTMLElement>("#era-strip")!);

  const detach: Array<() => void> = [];

  for (const e of chronicle) {
    const host = root.querySelector<HTMLElement>(`#chart-${e.id}`);
    if (!host) continue;
    const kind = CHART_FOR[e.id] ?? "perShare";
    // 區間限縮到該階段 —— 圖表的 y 軸會自動縮放到這段期間,
    // 所以短短四週的「信用壓力」也看得出波動,不會被兩年的尺度壓平
    const draw = (el: HTMLElement, h: number) => {
      if (kind === "riverBtc") drawRiverBtc(el, h, false, e.range);
      else if (kind === "riverUsd") drawRiverUsd(el, h, e.range);
      else drawPerShare(el, h, e.range);
    };
    const handle = zoomable(host, `${e.title} — ${CHART_CAPTION[kind]}`, draw,
      { inlineHeight: 200, zoomHeight: 520 });
    detach.push(() => handle.destroy());
  }

  // 點時間軸的色塊跳到對應的那一則
  const strip = root.querySelector<HTMLElement>("#era-strip")!;
  const onStrip = (ev: Event) => {
    const id = (ev.target as HTMLElement)?.getAttribute?.("data-era");
    if (id) root.querySelector(`#era-${id}`)?.scrollIntoView({ behavior: "smooth" });
  };
  strip.addEventListener("click", onStrip);
  detach.push(() => strip.removeEventListener("click", onStrip));

  return () => detach.forEach((fn) => fn());
};
