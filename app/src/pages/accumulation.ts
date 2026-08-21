import {
  accumulationLegend, accumulationStats, accumulationTable, drawAccumulation,
} from "../charts/accumulation";
import { btc as fmtBtc } from "../lib/format";
import { zoomable } from "../lib/zoomable";
import type { PageFn } from "../router";

export const accumulationPage: PageFn = (root) => {
  const s = accumulationStats();
  root.innerHTML = `
    <div class="wrap">
      <div class="page-head">
        <p class="eyebrow">持幣與融資</p>
        <h1>它到底買了多少幣,錢從哪來</h1>
        <p class="lede">資料直接來自每週的 8-K:累計持有量、當週買賣量、平均成交價,
          以及該週動用了哪些 ATM。這裡是原始數字,沒有插值 ——
          持有量畫成階梯線,只在公司實際揭露的那天跳動。</p>
      </div>

      <div class="grid3" style="margin-bottom:22px">
        <div class="tile"><div class="k">目前持有</div><div class="v">${fmtBtc(s.latest)}</div>
          <div class="d">顆 BTC</div></div>
        <div class="tile"><div class="k">累計買入</div>
          <div class="v" style="color:var(--good)">${fmtBtc(s.bought)}</div>
          <div class="d">${s.buyWeeks} 個買入週</div></div>
        <div class="tile"><div class="k">累計賣出</div>
          <div class="v" style="color:var(--bad)">${fmtBtc(s.sold)}</div>
          <div class="d">${s.sellWeeks} 個賣出週,2026 年才開始</div></div>
        <div class="tile"><div class="k">ATM 累計募資</div><div class="v">$${s.raisedB.toFixed(1)}B</div>
          <div class="d">各券種淨募資合計</div></div>
      </div>

      <div class="card flush" style="padding:18px 22px 8px">
        <div class="chart-block">
          <div class="chart-head">
            <div class="chart-label">累計持有量與逐週買賣</div>
            <div class="chart-tools"></div>
          </div>
          <div class="scroller"><div id="accum"></div></div>
        </div>
        <div class="legend" id="accum-legend"></div>
      </div>

      <div class="note key" style="margin-top:20px">
        <b>融資來源涵蓋 ${(s.coveredPct * 100).toFixed(0)}% 的買賣週次。</b>
        ${s.statedWeeks} 週在 8-K 敘述句明確指名(「proceeds from the STRF ATM, STRK ATM and
        MSTR ATM」);另外 ${s.derivedWeeks} 週敘述句只寫「under the ATM」沒指名,
        但同一份文件的「ATM Program Summary」表格已經逐券種列出當週淨募資 ——
        有錢進來的券種就是資金來源,下表標記「推得」與明示者區分。
        ${s.activeWeeks - s.statedWeeks - s.derivedWeeks} 週兩種資料都沒有,仍標為未指名。
      </div>

      <h3 style="margin:26px 0 12px">逐週原始資料</h3>
      <div class="card flush"><div class="scroller tall">${accumulationTable()}</div></div>
      <p style="font-size:.8rem;color:var(--ink-3);margin-top:10px">
        共 ${s.weeks} 週。各券種欄位為該週 ATM 淨募資(百萬美元),「—」代表當週未動用。</p>
    </div>`;

  root.querySelector<HTMLElement>("#accum-legend")!.innerHTML = accumulationLegend();
  const z = zoomable(root.querySelector<HTMLElement>("#accum")!,
    "BTC 累計持有量與逐週買賣(依融資來源上色)",
    (el, h) => { drawAccumulation(el, h); },
    { inlineHeight: 340, zoomHeight: 620 });
  return () => z.destroy();
};
