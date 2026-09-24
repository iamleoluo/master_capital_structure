/** 績效歸因 —— 一次比特幣行情裡,股東拿到的報酬各有多少來自哪一層。
 *
 *  兩層拆解,都在 Python 算好(mstr_cebe/attribution.py,有加總恆等的測試):
 *    1. 股價 = 幣價 × 實得每股含幣量 × 市場溢價  → 對數拆解,三層各佔多少
 *    2. 實得每股含幣量的變化 = 八種操作各自的貢獻 → Shapley
 *
 *  核心是逐日鏈結:每一天先讓幣價動(行情)、再讓結構動並用當天幣價評價(決策),
 *  所以每個決策只用它發生當下能知道的價格評價,不含後見之明。
 *  定義與公式一律放在「資本結構」頁,這裡只給結論。 */
import { daily, indexOfDate, N, strategy } from "../data";
import { drawPerShare } from "../charts/timeseries";
import { bn, btc as fmtBtc } from "../lib/format";
import { tex } from "../lib/math";
import { zoomable } from "../lib/zoomable";
import type { StrategyRow } from "../types";
import type { PageFn } from "../router";

const sats = (v: number) => Math.round(v).toLocaleString("en-US");
const signed = (v: number) => (v >= 0 ? "+" : "") + sats(v);
const pct1 = (v: number) => (v >= 0 ? "+" : "") + v.toFixed(1) + "%";

const LAYER_LABEL: Record<string, string> = {
  btc: "比特幣價格", cebe: "實得每股含幣量", mnav: "市場溢價(mNAV)",
};
const LAYER_NOTE: Record<string, string> = {
  btc: "底層資產本身漲跌,跟公司做了什麼無關",
  cebe: "公司的資本操作 + 求償權在幣計價下的縮放",
  mnav: "市場願意付的倍數,情緒與流動性",
};
const LAYER_COLOR: Record<string, string> = {
  btc: "var(--btc)", cebe: "var(--equity)", mnav: "var(--senti)",
};

const OP_LABEL: Record<string, string> = {
  price: "幣價讓求償權縮水",
  atm: "普通股 ATM 增發",
  pref_issue: "優先股發行",
  buyback: "優先股折價回購",
  converts: "可轉債變動",
  btc: "買賣比特幣",
  carry: "股息與債息",
  other: "未建模殘差",
};
const OP_NOTE: Record<string, string> = {
  price: "被動 —— 求償權面額固定在美元,幣價一漲它在幣計價下就自己縮小",
  atm: "只有「發行價高於每股淨值」的溢價部分才加分,不是「增發就是壞事」",
  pref_issue: "拿到現金但掛上面額;發行價低於 $100 面額時,淨效果是求償權增加",
  buyback: "進得了分子的只有折價本身,不是整筆回購金額",
  converts: "可轉債餘額變動,回購或轉股為正貢獻",
  btc: "用現金買幣在代數上是中性的 —— 差額只來自成交價與今天幣價的落差",
  carry: "純現金流出,槓桿的持有成本。結構上唯一必然為負的一項",
  other: "債務贖回、營運支出、STRE 匯率、股數插值誤差、ATM 入帳時間差",
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
          拆法見<a href="#/structure">資本結構</a>頁的定義區。</p>
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
        股價可以精確拆成三個相乘的因子 —— ${tex("P = m \\times E/10^{8} \\times p")}。
        取對數之後就變成相加,所以下面的貢獻度沒有殘差、也不需要決定誰先算。
        式子的推導見<a href="#/structure">資本結構</a>頁。
      </p>
      <div id="layers"></div>

      <h2 style="margin:34px 0 6px">第二層:是哪一筆操作做的</h2>
      <p class="lede" style="margin-bottom:16px">
        這裡拆的是<b>公司的決策</b>,不是會計科目。差別很重要:一筆 ATM 增發同時動到
        「股數」與「求償權」(募到的現金抵減求償權),所以把「股數」單獨拿出來看,
        不對應任何真實決策,還會得到「增發是壞事」這種錯誤結論。
        每一種操作對實得每股含幣量的效果都有明確的代數 ——
        例如「用現金買幣」恆等於
        ${tex("\\Delta\\!\\left(H - C/p\\right) = c/p - c/p = 0")},
        而 ATM 增發是否加分完全取決於 ${tex("m > 1")}。
        完整推導見<a href="#/structure">資本結構</a>頁,下面按操作拆。
      </p>
      <div id="ops"></div>

      <div class="chart-block" style="margin-top:34px">
        <div class="chart-head">
          <div class="chart-label">區間內的每股含幣量:帳面 vs 實得</div>
          <div class="chart-tools"></div>
        </div>
        <div id="chart"></div>
      </div>

      <div class="note" style="margin-top:26px">
        <b>解讀時務必把「增發」與「回購」綁在一起看。</b>
        這段期間買回求償權的錢,就是普通股 ATM 增發募來的 ——
        增發的稀釋與回購的折價收益是同一筆決策的兩面。
        單獨挑其中一項當結論,會得到相反的答案 ——
        這也是為什麼頁首先給「決策 / 行情」的合計,再往下拆到細項。
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
    el("headline").innerHTML = `
      <div class="grid3" style="margin-bottom:12px">
        <div class="tile"><div class="k">MSTR 報酬</div>
          <div class="v">${pct1(r.mstrRet)}</div>
          <div class="d">同期 BTC ${pct1(r.btcRet)}</div></div>
        <div class="tile"><div class="k">實得每股含幣量</div>
          <div class="v">${sats(r.cebe0)} → ${sats(strategy.cebeNow)}</div>
          <div class="d">sats,扣掉求償權後真正屬於股東的</div></div>
        <div class="tile">
          <div class="k">帳面每股含幣量</div>
          <div class="v ${strategy.bpsNow >= r.bps0 ? "up" : "down"}">${
            pct1((strategy.bpsNow / r.bps0 - 1) * 100)}</div>
          <div class="d">${sats(r.bps0)} → ${sats(strategy.bpsNow)} sats。不扣求償權,公司的 BTC Yield</div></div>
      </div>

      <div class="split-row">
        <div class="split-cell ${r.split.decision >= 0 ? "good" : "bad"}">
          <div class="k">決策貢獻(無後見之明)</div>
          <div class="v">${signed(r.split.decision)}</div>
          <div class="d">sats／股</div></div>
        <div class="split-cell muted">
          <div class="k">行情貢獻</div>
          <div class="v">${signed(r.split.market)}</div>
          <div class="d">sats／股。公司無從控制</div></div>
        <div class="split-cell">
          <div class="k">合計 = 實現變化</div>
          <div class="v">${signed(r.split.market + r.split.decision)}</div>
          <div class="d">sats／股</div></div>
      </div>

      <div class="note key">
        <b>決策與行情怎麼分開的:逐日走,每天拆兩半。</b>
        先讓當天的幣價動、結構凍結(那是<b>行情</b>),再讓當天的結構動、
        用<b>當天的</b>幣價評價(那是<b>決策</b>)。逐日加總,兩者相加精確等於實現變化,
        而且每個決策只用它<b>發生當下</b>能知道的價格評價 —— 不含後見之明。
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

  function paintOps(r: StrategyRow): void {
    const order = (["price", "atm", "pref_issue", "buyback", "converts",
                    "btc", "carry", "other"] as const);
    const max = Math.max(...order.map((k) => Math.abs(r.ops[k])), 1e-9);
    const delta = strategy.cebeNow - r.cebe0;
    const m = r.opMeta;

    if (!r.opsOk) {
      el("ops").innerHTML = `
        <div class="note warn" style="margin-top:0">
          <b>這個起點太早,資金流資料不足以拆到操作層級。</b>
          按操作拆解需要 8-K 完整揭露每週的 ATM 募資、回購金額與 USD Reserve 餘額 ——
          這些欄位要到 2026 年中才齊全。更早的區間對不起來的部分會全部擠進「殘差」
          (目前 ${sats(Math.abs(r.ops.other))} sats,已超過總變化的四分之一),
          那時候再去讀個別操作的數字沒有意義。
          <br><br>
          把起點拉到 <b>2026-06</b> 之後就會顯示。上面的三層拆解與決策/行情不依賴資金流資料,
          任何區間都有效。
        </div>`;
      return;
    }

    el("ops").innerHTML = `
      <div class="layer-list">
        ${order.map((k) => {
          const v = r.ops[k];
          const w = (Math.abs(v) / max) * 100;
          const passive = k === "price";
          const resid = k === "other";
          return `
            <div class="layer${resid ? " total" : ""}">
              <div class="layer-head">
                <span class="layer-name">${OP_LABEL[k]}${
                  passive ? ' <span class="passive-tag">被動</span>' : ""}</span>
                <span class="layer-vals"><b class="${v >= 0 ? "up" : "down"}">${signed(v)}</b>
                  <span class="layer-share">sats</span></span>
              </div>
              <div class="layer-bar"><i style="width:${w.toFixed(1)}%;
                background:${resid ? "var(--ink-3)" : v >= 0 ? "var(--good)" : "var(--bad)"}"></i></div>
              <div class="layer-note">${OP_NOTE[k]}</div>
            </div>`;
        }).join("")}
        <div class="layer total">
          <div class="layer-head">
            <span class="layer-name">加總 = 實際變化</span>
            <span class="layer-vals"><b>${signed(delta)}</b><span class="layer-share">sats</span></span>
          </div>
        </div>
      </div>

      <div class="note key" style="margin-top:18px">
        <b>唯一結構上必然為負的是股息與債息。</b>
        期間 ATM 募資 ${bn(m.raisedM / 1000)}、回購折價 ${bn(m.discountM / 1000)}、
        股息債息約 ${bn(m.carryM / 1000)}。
        其餘操作的正負完全取決於價格條件 —— 溢價增發加分、折價回購加分、
        用現金買幣中性。所以「資本操作淨貢獻是負的」從來不代表公司做錯了什麼,
        通常只是槓桿的持有成本大過那段期間操作賺到的價差。
      </div>`;
  }

  let zoom: { destroy(): void } | null = null;

  function paintChart(): void {
    const host = el("chart");
    const range: [number, number] = [idx, N - 1];
    zoom?.destroy();
    host.innerHTML = "";
    zoom = zoomable(host, "區間內的每股含幣量:帳面 vs 實得",
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
    paintOps(r);
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
