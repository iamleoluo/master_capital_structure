import { meta } from "../data";
import {
  amplification, breakEven, commonSats, drawLeverage,
  grossSats, latestBasis, perShareUsd, runScenario,
  type ScenarioParams,
} from "../charts/leverage";
import { btc as fmtBtc, mult, usd, usd0 } from "../lib/format";
import { zoomable } from "../lib/zoomable";
import type { PageFn } from "../router";

const SCENARIOS = [45_000, 63_044, 100_000, 150_000, 200_000, 300_000];

export const pricingPage: PageFn = (root) => {
  const b = latestBasis();
  const gross = grossSats(b);
  const be = breakEven(b);
  const nowSats = commonSats(b, b.px0);
  const nowVal = perShareUsd(b, b.px0);
  const nowAmp = amplification(b, b.px0);

  const beLab: Record<string, string> = {
    company_net_reserve: "官方(扣 USD Reserve)", cebetracker: "cebetracker(扣現金)",
    mnav_com: "mnav.com(毛額,漏 STRE)", company: "毛額含 STRE(不扣現金)",
  };

  root.innerHTML = `
    <div class="wrap">
      <div class="page-head">
        <p class="eyebrow">槓桿與定價</p>
        <h1>每股含幣量會自己長回來</h1>
        <p class="lede">上一頁看到的是壞消息:一年下來公司買了二十幾萬顆幣,普通股每股分到的量卻幾乎沒動。
          但那不代表這些幣白買了 —— 它換來的是<b>槓桿</b>。求償權的面額鎖死在美元,
          BTC 一漲,同樣的求償權在幣計價下就縮小,普通股的每股含幣量不用多買一顆就會自己長回來。
          下面三個開關把這件事接下來可能怎麼發展模擬出來:公司會不會補倉槓桿、
          市場願付多少溢價、溢價增發又會怎麼反過來墊高每股含幣量。</p>
      </div>

      <div class="card" style="margin-bottom:26px">
        <h3 style="margin-bottom:14px">情境參數</h3>
        <div class="grid3">
          <div class="ctl">
            <div class="ctl-top"><span class="ctl-lab">槓桿下限</span><span class="ctl-val" id="v-floor"></span></div>
            <input type="range" id="s-floor" min="1.0" max="2.0" step="0.01" value="1.30" />
            <div style="font-size:.74rem;color:var(--ink-3)">
              今天實際槓桿 ${mult(nowAmp)}。價格漲到低於這個下限時,假設公司持續發 STRC 買幣補回來。設 1.00 = 不補倉。</div>
          </div>
          <div class="ctl">
            <div class="ctl-top"><span class="ctl-lab">市場 mNAV 溢價</span><span class="ctl-val" id="v-mnav"></span></div>
            <input type="range" id="s-mnav" min="0.5" max="2.5" step="0.01" value="1.00" />
            <div style="font-size:.74rem;color:var(--ink-3)">
              市場願意付多少倍 CEBE 公允值。1.0 = 不折不扣;高於 1.0 代表市場一直在給溢價。</div>
          </div>
          <div class="ctl">
            <div class="ctl-top"><span class="ctl-lab">ATM 溢價增發</span><span class="ctl-val" id="v-atm"></span></div>
            <input type="range" id="s-atm" min="0" max="50" step="1" value="0" />
            <div style="font-size:.74rem;color:var(--ink-3)">
              在上面的 mNAV 溢價下,額外多發行這麼多百分比的股數、錢全部拿去買幣。
              溢價 &gt;1 時這對既有股東是加分的。</div>
          </div>
        </div>
        <p style="font-size:.78rem;color:var(--ink-3);margin:14px 0 0">
          參考:普通股殘值歸零的 BTC 價格是 ${usd0(be)}(不含槓桿下限的再融資效果)。</p>
      </div>

      <div class="card flush" style="padding:20px 22px 10px;margin-bottom:8px">
        <div class="chart-block">
          <div class="chart-head">
            <div class="chart-label">普通股每股含幣量 vs BTC 價格</div>
            <div class="chart-tools"></div>
          </div>
          <div class="scroller"><div id="lev"></div></div>
        </div>
      </div>
      <figcaption style="margin-bottom:26px">
        灰虛線是「完全沒有求償權」的上限(${Math.round(gross).toLocaleString()} sats)。
        淺色虛線是「公司什麼都不做」的自然衰減曲線;橘線是套用上面三個參數後的情境曲線 ——
        兩者只在你把槓桿下限或 ATM 增發打開時才會分岔。藍色豎線是槓桿下限觸發價,紅色是歸零價。
      </figcaption>

      <div class="grid3" style="margin-bottom:12px" id="tiles"></div>
      <div class="note key" id="verdict" style="margin-bottom:36px"></div>

      <h2 style="margin-bottom:8px">情境對照</h2>
      <p class="lede" style="margin-bottom:16px">同一組參數,不同 BTC 價格下的結果。
        「不補倉」欄是完全不做任何事的基準;右邊三欄套用你設定的槓桿下限、mNAV 與 ATM 增發。</p>
      <div class="card flush"><div class="scroller"><table class="mini">
        <thead><tr>
          <th>BTC 價格</th><th class="n">不補倉每股 sats</th>
          <th class="n">情境每股 sats</th><th class="n">情境股價</th>
          <th class="n">股價報酬</th><th class="n">槓桿</th>
        </tr></thead>
        <tbody id="scen-tbl"></tbody>
      </table></div></div>
      <p style="font-size:.8rem;color:var(--ink-3);margin-top:10px" id="scen-note"></p>

      <div class="note warn" style="margin-top:26px">
        <b>這個模型假設市場願付的 mNAV 倍數在整段期間維持不變。</b>
        現實中 mNAV 本身會隨情緒漲跌(見<a href="#/">總覽</a>頁的歷史軌跡,兩年內在 0.68x 到 3.4x 之間都出現過),
        不是一個常數。這裡把它當參數讓你自己設,是因為沒有人能預測情緒,
        但至少可以把「情緒不變、只有 BTC 價格移動」的效果先算清楚。
        另外槓桿下限的再融資假設公司能持續用 STRC 募到錢 —— 實際上募資能力會受市場胃納與利率影響。
      </div>

      <h2 style="margin:40px 0 8px">官方錨點</h2>
      <p class="lede" style="margin-bottom:16px">公司自己在 2026-08-13 的 Form FWP 給了一張敏感度表,
        是本專案唯一能拿來對答案的一手資料。</p>
      <div class="grid2">
        <div>
          <h3 style="margin-bottom:10px">敏感度表(已完整重現)</h3>
          <div class="card flush"><div class="scroller"><table class="mini">
            <thead><tr><th>BTC 價格</th><th class="n">官方每股淨值</th><th class="n">本系統</th><th class="n">誤差</th></tr></thead>
            <tbody>${meta.sens.map((s) => {
              const err = ((s.got - s.off) / s.off) * 1e4;
              return `<tr><td class="num">${usd0(s.btc)}</td><td class="n">$${s.off.toFixed(2)}</td>
                <td class="n">$${s.got.toFixed(4)}</td>
                <td class="n" style="color:var(--ink-3)">${err >= 0 ? "+" : ""}${err.toFixed(2)}bp</td></tr>`;
            }).join("")}</tbody></table></div></div>
          <p style="font-size:.8rem;color:var(--ink-3);margin-top:10px">
            六列全部落在 1 個基點內。FWP 揭露的輸入只到 $1M 精度,無法逐分吻合是資料的極限,不是公式錯誤。</p>
        </div>
        <div>
          <h3 style="margin-bottom:10px">歸零價有三個都對的答案</h3>
          <div class="card flush"><div class="scroller"><table class="mini">
            <thead><tr><th>定義</th><th class="n">歸零 BTC 價</th><th class="n">緩衝</th></tr></thead>
            <tbody>${meta.be.map((x) =>
              `<tr><td>${beLab[x.k] ?? x.k}</td><td class="n">${usd0(x.v)}</td>
               <td class="n">${(meta.fwp.btc / x.v).toFixed(2)}x</td></tr>`).join("")}</tbody>
          </table></div></div>
          <p style="font-size:.8rem;color:var(--ink-3);margin-top:10px">
            差異全在「求償權」怎麼定義:扣不扣現金、扣的是資產負債表現金還是 USD Reserve、
            算不算歐元計價的 STRE。本頁的曲線用 cebetracker 定義。</p>
        </div>
      </div>
    </div>`;

  const q = (s: string) => root.querySelector<HTMLElement>(s)!;
  const host = q("#lev");
  const sliderPx = document.createElement("input"); // 情境 BTC 價格,插在參數卡片與圖表之間更合理位置由下方補
  void sliderPx;

  // 情境 BTC 價格滑桿(放在圖表上方,和三個參數分開,因為它是「看哪一點」而非模型假設)
  const pxRow = document.createElement("div");
  pxRow.style.cssText = "display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin-bottom:18px";
  pxRow.innerHTML = `<span style="font-size:.82rem;color:var(--ink-2)">情境 BTC 價格</span>
    <input type="range" id="s-px" min="25000" max="300000" step="1000" value="150000" style="flex:1;min-width:220px" />
    <span class="ctl-val" id="v-px" style="min-width:96px;text-align:right"></span>`;
  q("#lev").closest(".card")!.insertAdjacentElement("afterend", pxRow);

  const slider = pxRow.querySelector<HTMLInputElement>("#s-px")!;
  const floorSlider = root.querySelector<HTMLInputElement>("#s-floor")!;
  const mnavSlider = root.querySelector<HTMLInputElement>("#s-mnav")!;
  const atmSlider = root.querySelector<HTMLInputElement>("#s-atm")!;

  function params(): ScenarioParams {
    return {
      leverageFloor: +floorSlider.value,
      mnav: +mnavSlider.value,
      atmDilution: +atmSlider.value / 100,
    };
  }

  let zoomEl: HTMLElement | null = null;
  const drawInto = (el: HTMLElement, h: number) =>
    drawLeverage(el, b, { scenarioPx: +slider.value, params: params() }, h);

  function paintTable(): void {
    const p = params();
    const rows = SCENARIOS.map((px) => {
      const r = runScenario(b, px, p);
      const rP = (r.marketPrice / (p.mnav * nowVal) - 1) * 100;
      const isNow = Math.abs(px - b.px0) < 1500;
      const col = (v: number) => (v >= 0 ? "var(--good)" : "var(--bad)");
      return `<tr${isNow ? ' style="background:var(--surface-2)"' : ""}>
        <td class="num">${usd0(px)}${isNow ? " ←今天" : ""}</td>
        <td class="n">${Math.round(commonSats(b, px)).toLocaleString()}</td>
        <td class="n" style="color:${r.triggeredReleverage ? "var(--equity)" : "inherit"}">
          ${Math.round(r.perShareSats).toLocaleString()}${r.triggeredReleverage ? " ⚡" : ""}</td>
        <td class="n">${usd(r.marketPrice)}</td>
        <td class="n" style="color:${col(rP)}">${rP >= 0 ? "+" : ""}${rP.toFixed(0)}%</td>
        <td class="n">${mult(r.amp)}</td></tr>`;
    }).join("");
    q("#scen-tbl").innerHTML = rows;
    q("#scen-note").innerHTML =
      `基準為 ${b.date}:持有 ${fmtBtc(b.held)} 顆、求償權 $${(b.claims / 1e9).toFixed(2)}B、`
      + `股數 ${(b.shares / 1e6).toFixed(1)}M。⚡ = 該價位已觸發槓桿下限的再融資機制。`;
  }

  function paint(): void {
    const px = +slider.value;
    const p = params();
    q("#v-px").textContent = usd0(px);
    q("#v-floor").textContent = p.leverageFloor.toFixed(2) + "x";
    q("#v-mnav").textContent = p.mnav.toFixed(2) + "x";
    q("#v-atm").textContent = atmSlider.value + "%";

    drawInto(host, 330);
    if (zoomEl) drawInto(zoomEl, 620);
    paintTable();

    const r = runScenario(b, px, p);
    const dSats = (r.perShareSats / nowSats - 1) * 100;
    const rB = (px / b.px0 - 1) * 100;
    const rMkt = (r.marketPrice / (p.mnav * nowVal) - 1) * 100;

    q("#tiles").innerHTML = `
      <div class="tile"><div class="k">每股含幣量(情境)</div>
        <div class="v" style="color:var(--equity)">${Math.round(r.perShareSats).toLocaleString()}</div>
        <div class="d">sats,今天是 ${Math.round(nowSats).toLocaleString()}
          (${dSats >= 0 ? "+" : ""}${dSats.toFixed(0)}%)</div></div>
      <div class="tile"><div class="k">情境股價</div>
        <div class="v">${usd(r.marketPrice)}</div>
        <div class="d">= ${p.mnav.toFixed(2)}x × 每股殘值 ${usd(r.perShareUsd)}</div></div>
      <div class="tile"><div class="k">目前槓桿</div>
        <div class="v">${mult(r.amp)}</div>
        <div class="d">${r.triggeredReleverage
          ? `已觸發下限,鎖定在 ${p.leverageFloor.toFixed(2)}x`
          : `下限 ${p.leverageFloor.toFixed(2)}x 尚未觸發(觸發價 ${Number.isFinite(r.triggerPx) ? usd0(r.triggerPx) : "—"})`}</div></div>`;

    const parts: string[] = [];
    if (px > b.px0) {
      parts.push(`BTC 從 ${usd0(b.px0)} 漲到 ${usd0(px)}(<b>+${rB.toFixed(0)}%</b>)。`);
    } else if (px < b.px0) {
      parts.push(`BTC 從 ${usd0(b.px0)} 跌到 ${usd0(px)}(<b>${rB.toFixed(0)}%</b>)。`);
    } else {
      parts.push(`這是今天的價位。`);
    }
    parts.push(`在槓桿下限 ${p.leverageFloor.toFixed(2)}x、mNAV ${p.mnav.toFixed(2)}x、`
      + `ATM 增發 ${atmSlider.value}% 的假設下,每股含幣量會是 `
      + `<b>${Math.round(r.perShareSats).toLocaleString()} sats</b>(${dSats >= 0 ? "+" : ""}${dSats.toFixed(0)}%)。`);
    if (r.triggeredReleverage) {
      parts.push(`這個價位已經高過 ${usd0(r.triggerPx)} 的觸發價 —— 模型假設公司從那裡開始持續發 STRC `
        + `買幣、把槓桿釘在 ${p.leverageFloor.toFixed(2)}x,所以每股含幣量在觸發價之後會沿著 `
        + `<b>price^${p.leverageFloor.toFixed(2)}</b> 的冪次曲線成長,比自然衰減曲線更快回升。`);
    }
    if (p.atmDilution > 0 && p.mnav !== 1) {
      const dir = p.mnav > 1 ? "加值" : "稀釋";
      parts.push(`額外用 ATM 溢價增發 ${atmSlider.value}% 股數(在 ${p.mnav.toFixed(2)}x 的市價賣出、`
        + `錢全部買幣),對既有股東是<b>${dir}</b>的 —— mNAV ${p.mnav > 1 ? "高於" : "低於"} 1 時,`
        + `新股東付的價格${p.mnav > 1 ? "高於" : "低於"}每股實際含幣的公允值。`);
    }
    parts.push(`情境股價 <b>${usd(r.marketPrice)}</b>(${rMkt >= 0 ? "+" : ""}${rMkt.toFixed(0)}% vs 今天在同一個 mNAV 倍數下的股價)。`);
    q("#verdict").innerHTML = parts.join(" ");
  }

  [slider, floorSlider, mnavSlider, atmSlider].forEach((s) => s.addEventListener("input", paint));
  paint();

  const z = zoomable(host, "普通股每股含幣量 vs BTC 價格(情境模擬)", (el, h) => {
    if (h > 400) zoomEl = el;
    drawInto(el, h);
  }, { inlineHeight: 330, zoomHeight: 620 });
  return () => { zoomEl = null; z.destroy(); pxRow.remove(); };
};
