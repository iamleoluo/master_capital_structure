/** 策略分析 —— 一次比特幣行情裡,股東拿到的報酬各有多少來自哪一層。
 *
 *  兩層拆解,都在 Python 算好(mstr_cebe/attribution.py,有加總恆等的測試):
 *    1. 股價 = 幣價 × 每股含幣量 × 市場溢價   → 對數拆解,三層各佔多少
 *    2. 每股含幣量本身 = 持幣 / 求償權 / 幣價 / 股數 四個因子 → Shapley
 *
 *  最重要的一塊是「反事實」:如果公司從那天起什麼都不做,光靠幣價上漲,
 *  每股含幣量會走到哪裡?實際值減掉它,才是資本操作真正的淨貢獻。 */
import { daily, indexOfDate, N, strategy } from "../data";
import { drawPerShare } from "../charts/timeseries";
import { btc as fmtBtc } from "../lib/format";
import { zoomable } from "../lib/zoomable";
import type { StrategyRow } from "../types";
import type { PageFn } from "../router";

const sats = (v: number) => Math.round(v).toLocaleString("en-US");
const signed = (v: number) => (v >= 0 ? "+" : "") + sats(v);
const pct1 = (v: number) => (v >= 0 ? "+" : "") + v.toFixed(1) + "%";

const LAYER_LABEL: Record<string, string> = {
  btc: "比特幣價格", cebe: "每股含幣量", mnav: "市場溢價(mNAV)",
};
const LAYER_NOTE: Record<string, string> = {
  btc: "底層資產本身漲跌,跟公司做了什麼無關",
  cebe: "公司的資本操作 + 求償權在幣計價下的縮放",
  mnav: "市場願意付的倍數,情緒與流動性",
};
const LAYER_COLOR: Record<string, string> = {
  btc: "var(--btc)", cebe: "var(--equity)", mnav: "var(--senti)",
};

const FACTOR_LABEL: Record<string, string> = {
  price: "幣價讓求償權縮水",
  claims: "求償權變動(回購 / 募資進儲備)",
  held: "持幣變動(買幣 / 賣幣)",
  shares: "股數變動(ATM 增發稀釋)",
};

export const strategyPage: PageFn = (root) => {
  let idx = indexOfDate("2026-06-29");   // 預設起點:框架公布日

  root.innerHTML = `
    <div class="wrap">
      <div class="page-head">
        <p class="eyebrow">策略分析</p>
        <h1>這波漲幅,有多少是公司做出來的</h1>
        <p class="lede">選一個起點,看到今天為止股東拿到的報酬怎麼分層:
          哪些來自比特幣本身、哪些來自市場願意付的溢價、哪些真的來自公司的資本操作。
          最後一項用<b>反事實</b>回答 —— 如果從那天起什麼都不做,今天會在哪裡。</p>
      </div>

      <div class="card" style="margin-bottom:24px">
        <div class="preset-row" id="presets"></div>
        <div style="margin-top:14px">
          <input type="range" class="date-scrub" id="start-scrub"
                 min="0" max="${N - 1}" value="${idx}" aria-label="選擇起始日" />
          <div class="scrub-ends">
            <span class="mono">${daily.date[0]}</span>
            <span class="mono" id="start-label"></span>
            <span class="mono">${strategy.end}</span>
          </div>
        </div>
      </div>

      <div id="headline"></div>

      <h2 style="margin:34px 0 6px">第一層:報酬來自哪裡</h2>
      <p class="lede" style="margin-bottom:16px">
        股價可以精確拆成三個相乘的因子 ——
        <span class="mono" style="font-size:.86rem">股價 = 市場溢價 × 每股含幣量 × 幣價</span>。
        取對數之後就變成相加,所以下面的貢獻度沒有殘差、也不需要決定誰先算。
      </p>
      <div id="layers"></div>

      <h2 style="margin:34px 0 6px">第二層:每股含幣量是怎麼變的</h2>
      <p class="lede" style="margin-bottom:16px">
        中間那一層才是公司能控制的部分。它由四個因子決定,
        用 Shapley 值拆解(對全部 24 種先後順序取平均,所以與順序無關,
        四項加總精確等於實際變化)。
      </p>
      <div id="factors"></div>

      <div class="chart-block" style="margin-top:26px">
        <div class="chart-head">
          <div class="chart-label">區間內的每股含幣量:帳面(basic 股數)vs 實際(CEBE)</div>
          <div class="chart-tools"></div>
        </div>
        <div id="chart"></div>
      </div>

      <div class="note warn" id="method-gap" style="margin-top:22px"></div>

      <div class="note" style="margin-top:26px">
        <b>解讀時務必把「增發」與「回購」綁在一起看。</b>
        這段期間買回求償權的錢,就是普通股 ATM 增發募來的 ——
        所以「求償權變動」的正貢獻與「股數變動」的負貢獻是同一件事的兩面。
        單獨挑其中一項當結論,會得到相反的答案。上面的「主動操作合計」
        之所以擺在細項前面,就是這個原因。
      </div>

      <p style="font-size:.8rem;color:var(--ink-3);margin-top:22px">
        求償權採 CEBE 定義(可轉債 + 優先股清算優先權 − USD 流動性)。
        USD 流動性以 8-K 每週揭露的 USD Reserve + USD Cash 為主、季度 XBRL 為輔 ——
        2026 下半年靠 ATM 募資進入儲備的約 $44 億,只看季度資料會完全漏掉,
        歸因也會跟著反向。詳見<a href="#/data-quality">資料品質</a>。
      </p>
    </div>`;

  const el = (id: string) => root.querySelector<HTMLElement>("#" + id)!;

  // ---- 起點預設鈕 ----
  el("presets").innerHTML = strategy.presets.map((p) =>
    `<button type="button" class="range-btn" data-preset="${p.date}">${p.label}</button>`
  ).join("");

  function row(): StrategyRow | null {
    return strategy.rows[idx] ?? null;
  }

  function paintHeadline(r: StrategyRow): void {
    const good = r.vsCf >= 0;
    el("headline").innerHTML = `
      <div class="grid3" style="margin-bottom:12px">
        <div class="tile"><div class="k">MSTR 報酬</div>
          <div class="v">${pct1(r.mstrRet)}</div>
          <div class="d">同期 BTC ${pct1(r.btcRet)}</div></div>
        <div class="tile"><div class="k">每股含幣量</div>
          <div class="v">${sats(r.cebe0)} → ${sats(strategy.cebeNow)}</div>
          <div class="d">sats,扣掉求償權後真正屬於股東的</div></div>
        <div class="tile" style="border-left:3px solid ${good ? "var(--good)" : "var(--bad)"}">
          <div class="k">資本操作淨貢獻</div>
          <div class="v" style="color:${good ? "var(--good)" : "var(--bad)"}">${signed(r.vsCf)}</div>
          <div class="d">sats／股,實際 ${sats(strategy.cebeNow)} − 反事實 ${sats(r.cf)}</div></div>
      </div>

      <div class="note key">
        <b>反事實:如果從 ${daily.date[idx]} 起什麼都不做</b> ——
        不買幣、不賣幣、不增發、不回購,結構整個凍結,只讓比特幣價格走到今天,
        每股含幣量會是 <b>${sats(r.cf)} sats</b>。
        實際是 ${sats(strategy.cebeNow)} sats,
        所以這段期間全部資本操作的淨效果是 <b>${signed(r.vsCf)} sats／股</b>
        (${good ? "加分" : "減分"})。
        ${r.sold || r.bought ? `期間實際買入 ${fmtBtc(r.bought)} 顆、賣出 ${fmtBtc(r.sold)} 顆。` : ""}
      </div>`;
  }

  function paintLayers(r: StrategyRow): void {
    const total = r.layers.btc + r.layers.cebe + r.layers.mnav;
    const order = (["btc", "cebe", "mnav"] as const);
    const max = Math.max(...order.map((k) => Math.abs(r.layers[k])), 1e-9);

    el("layers").innerHTML = `
      ${r.stable ? "" : `<div class="note warn" style="margin-top:0">
        這個區間的總報酬太接近零(${pct1(r.mstrRet)}),
        再去算「各層佔百分之幾」會被分母放大成沒有意義的數字 ——
        所以下面只顯示每一層自己的漲跌幅,不給佔比。</div>`}
      <div class="layer-list">
        ${order.map((k) => {
          const v = r.layers[k];
          const own = (Math.exp(v) - 1) * 100;
          const share = total !== 0 ? (v / total) * 100 : 0;
          const w = (Math.abs(v) / max) * 100;
          return `
            <div class="layer">
              <div class="layer-head">
                <span class="layer-name"><i class="swatch" style="background:${LAYER_COLOR[k]}"></i>${LAYER_LABEL[k]}</span>
                <span class="layer-vals">
                  <b class="${own >= 0 ? "up" : "down"}">${pct1(own)}</b>
                  ${r.stable ? `<span class="layer-share">佔 ${share.toFixed(0)}%</span>` : ""}
                </span>
              </div>
              <div class="layer-bar"><i style="width:${w.toFixed(1)}%;background:${LAYER_COLOR[k]};
                ${v < 0 ? "opacity:.45" : ""}"></i></div>
              <div class="layer-note">${LAYER_NOTE[k]}</div>
            </div>`;
        }).join("")}
      </div>`;
  }

  function paintFactors(r: StrategyRow): void {
    const delta = strategy.cebeNow - r.cebe0;
    const items = (["price", "claims", "held", "shares"] as const);
    const max = Math.max(...items.map((k) => Math.abs(r.f[k])), 1e-9);

    el("factors").innerHTML = `
      <div class="grid2" style="margin-bottom:16px">
        <div class="tile" style="border-left:3px solid var(--ink-3)">
          <div class="k">被動 — 不需要任何作為</div>
          <div class="v">${signed(r.passive)}</div>
          <div class="d">sats。求償權面額固定在美元,幣價一漲它在幣計價下就自己縮小</div></div>
        <div class="tile" style="border-left:3px solid ${r.active >= 0 ? "var(--good)" : "var(--bad)"}">
          <div class="k">主動 — 公司的資本操作合計</div>
          <div class="v" style="color:${r.active >= 0 ? "var(--good)" : "var(--bad)"}">${signed(r.active)}</div>
          <div class="d">sats。買賣幣 + 求償權變動 + 股數變動三者的淨和</div></div>
      </div>
      <div class="layer-list">
        ${items.map((k) => {
          const v = r.f[k];
          const w = (Math.abs(v) / max) * 100;
          return `
            <div class="layer">
              <div class="layer-head">
                <span class="layer-name">${FACTOR_LABEL[k]}${k === "price" ? ' <span class="passive-tag">被動</span>' : ""}</span>
                <span class="layer-vals"><b class="${v >= 0 ? "up" : "down"}">${signed(v)}</b>
                  <span class="layer-share">sats</span></span>
              </div>
              <div class="layer-bar"><i style="width:${w.toFixed(1)}%;
                background:${v >= 0 ? "var(--good)" : "var(--bad)"}"></i></div>
            </div>`;
        }).join("")}
        <div class="layer total">
          <div class="layer-head">
            <span class="layer-name">四項加總 = 實際變化</span>
            <span class="layer-vals"><b>${signed(delta)}</b><span class="layer-share">sats</span></span>
          </div>
        </div>
      </div>`;
  }

  /** 兩種口徑會給出不同(有時相反)的答案,不解釋清楚頁面等於自相矛盾。 */
  function paintMethodGap(r: StrategyRow): void {
    const gap = r.active - r.vsCf;
    if (Math.abs(gap) < 200) { el("method-gap").innerHTML = ""; return; }
    el("method-gap").innerHTML = `
      <b>為什麼上面兩個「資本操作貢獻」數字不一樣?</b>
      Shapley 的主動合計是 <b>${signed(r.active)}</b>,反事實卻是 <b>${signed(r.vsCf)}</b>,
      差 ${signed(gap)} sats。兩者沒有誰對誰錯,是在回答不同的問題:
      <br><br>
      <b>反事實</b>問「如果完全不動作,今天會在哪裡」——
      把幣價與結構變動之間的<b>交互作用</b>整包算給「不動作」那條基準線。
      這是你設定情境時最直覺的比較方式。
      <br><br>
      <b>Shapley</b> 問「已經發生的變化裡,每個因子各該分到多少」——
      交互作用由四個因子對稱分攤,所以不會因為先算誰而改變答案。
      <br><br>
      交互作用之所以存在,是因為求償權換算成幣要除以幣價:
      同樣減少一塊錢的求償權,在幣價高的時候省下的幣比較少。
      幣價漲了 ${pct1(r.btcRet)}、求償權同時在變,兩件事的效果沒辦法完全切乾淨。`;
  }

  let zoom: { destroy(): void } | null = null;

  function paintChart(): void {
    const host = el("chart");
    const range: [number, number] = [idx, N - 1];
    zoom?.destroy();
    host.innerHTML = "";
    zoom = zoomable(host, "區間內的每股含幣量",
      (e, h) => drawPerShare(e, h, range),
      { inlineHeight: 220, zoomHeight: 520 });
  }

  function paint(): void {
    const r = row();
    el("start-label").textContent = `起點 ${daily.date[idx]}`;
    scrub.value = String(idx);
    root.querySelectorAll<HTMLButtonElement>("[data-preset]").forEach((b) =>
      b.classList.toggle("active", b.dataset.preset === daily.date[idx]));
    if (!r) return;
    paintHeadline(r);
    paintLayers(r);
    paintFactors(r);
    paintMethodGap(r);
    paintChart();
  }

  const scrub = root.querySelector<HTMLInputElement>("#start-scrub")!;
  const onScrub = () => {
    // 起點不能貼到終點,否則區間長度為零、拆解沒有意義
    idx = Math.min(+scrub.value, N - 5);
    paint();
  };
  scrub.addEventListener("input", onScrub);

  const onPreset = (ev: Event) => {
    const d = (ev.target as HTMLElement)?.getAttribute?.("data-preset");
    if (!d) return;
    idx = Math.min(indexOfDate(d), N - 5);
    paint();
  };
  el("presets").addEventListener("click", onPreset);

  paint();

  return () => {
    scrub.removeEventListener("input", onScrub);
    el("presets").removeEventListener("click", onPreset);
    zoom?.destroy();
  };
};
