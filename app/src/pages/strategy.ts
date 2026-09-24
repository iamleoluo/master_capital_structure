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
import { bn, btc as fmtBtc, usd0 } from "../lib/format";
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

      <h2 style="margin:34px 0 6px">三個度量,先講清楚差在哪</h2>
      <p class="lede" style="margin-bottom:16px">
        「每股含幣量」不只一種算法,而且選錯會讓結論反過來。
        三個式子的差別只在<b>有沒有把求償權扣掉</b>、以及<b>式子裡有沒有幣價</b>:
      </p>

      <div class="card formulas" style="margin-bottom:16px">
        <div class="formula">
          <div class="formula-tag">A</div>
          <div>
            <div class="formula-name">Gross BPS(公司自己的 BTC Yield)</div>
            <div class="formula-eq">BPS = 總持幣 H ÷ 股數 S</div>
            <div class="formula-note">
              <b>式子裡沒有幣價,也沒有求償權。</b>幣價怎麼波動都不影響它 ——
              這正是為什麼公司拿它當 KPI。缺點是它看不見求償權:
              用發優先股的錢買幣會讓它上升,但股東一顆也沒多拿到(phantom growth)。
            </div>
          </div>
        </div>
        <div class="formula">
          <div class="formula-tag">B</div>
          <div>
            <div class="formula-name">CEBE(扣掉求償權後真正屬於普通股的)</div>
            <div class="formula-eq">CEBE = ( H − C ÷ p ) ÷ S</div>
            <div class="formula-note">
              C 是求償權(可轉債 + 優先股清算優先權 − USD 流動性),面額固定在美元,
              所以要<b>除以當下幣價 p</b> 才能換算成「幾顆幣」。
              代價就是<b>幣價跑進式子裡了</b> —— 公司什麼都不做,幣價一漲 CEBE 也會上升。
            </div>
          </div>
        </div>
        <div class="formula">
          <div class="formula-tag key">C</div>
          <div>
            <div class="formula-name">CEBE @ 固定幣價 — 衡量操作績效用這個</div>
            <div class="formula-eq">CEBE<sub>固定</sub> = ( H − C ÷ p* ) ÷ S &nbsp;&nbsp;(起點與終點都代入同一個 p*)</div>
            <div class="formula-note">
              把 p 釘死成同一個數,幣價效果就<b>整項消失</b>,但求償權還留著。
              兩者兼顧。數學上這與「實際值 − 反事實(結構凍結、只讓幣價走)」完全等價,
              也就是上面那個「資本操作淨貢獻」。
            </div>
          </div>
        </div>
      </div>

      <div id="measures"></div>

      <h2 style="margin:34px 0 6px">第一層:報酬來自哪裡</h2>
      <p class="lede" style="margin-bottom:16px">
        股價可以精確拆成三個相乘的因子 ——
        <span class="mono" style="font-size:.86rem">股價 = 市場溢價 × 每股含幣量 × 幣價</span>。
        取對數之後就變成相加,所以下面的貢獻度沒有殘差、也不需要決定誰先算。
      </p>
      <div id="layers"></div>

      <h2 style="margin:34px 0 6px">第二層:是哪一筆操作做的</h2>
      <p class="lede" style="margin-bottom:16px">
        這裡拆的是<b>公司的決策</b>,不是會計科目。差別很重要:一筆 ATM 增發同時動到
        「股數」與「求償權」(募到的現金抵減求償權),所以把「股數」單獨拿出來看,
        不對應任何真實決策,還會得到「增發是壞事」這種錯誤結論。
        每一種操作對每股含幣量的效果都有明確的代數,下面按操作拆。
      </p>
      <div id="ops"></div>

      <h2 style="margin:34px 0 6px">附:按會計科目拆</h2>
      <p class="lede" style="margin-bottom:16px">
        同一段變化改用四個會計因子(持幣 / 求償權 / 幣價 / 股數)來看。
        這組數字本身沒錯,但<b>不要照著它下決策結論</b> —— 理由就是上面說的:
        科目不是操作。
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
        <div class="tile">
          <div class="k">Gross BPS(公司的 BTC Yield)</div>
          <div class="v ${strategy.bpsNow >= r.bps0 ? "up" : "down"}">${
            pct1((strategy.bpsNow / r.bps0 - 1) * 100)}</div>
          <div class="d">${sats(r.bps0)} → ${sats(strategy.bpsNow)} sats。看不見求償權</div></div>
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
      </div>

      <div class="note">
        <b>反事實(度量 C)是另一種切法,內含後見之明,擺在這裡對照。</b>
        把期初的持幣、求償權、股數原封不動代進去,但幣價用<b>今天的</b> ——
        也就是「公司從 ${daily.date[idx]} 起什麼都不做,只有行情在走」的世界。
        <div class="formula-eq" style="margin:10px 0">
          反事實 = ( H₀ − C₀ ÷ p₁ ) ÷ S₀ = ${sats(r.cf)} sats<br>
          實際　 = ( H₁ − C₁ ÷ p₁ ) ÷ S₁ = ${sats(strategy.cebeNow)} sats
        </div>
        兩邊的幣價都是 p₁,所以相減時幣價效果整項消掉。
        但代價是它用<b>今天的</b>價格回頭評價所有過去的決策 ——
        「在行情上漲前增發」用這個口徑永遠會被判成減分,因為賣出去的股票
        事後看都賣便宜了。想知道「決策當下對不對」,要看上面的決策貢獻
        (${signed(r.split.decision)});這裡的 ${signed(r.vsCf)} 回答的是
        「用今天的價格回頭看划不划算」。
        實際是 ${sats(strategy.cebeNow)} sats,
        所以這段期間全部資本操作的淨效果是 <b>${signed(r.vsCf)} sats／股</b>
        (${good ? "加分" : "減分"})。這個數字等同於下面的度量 C
        —— 把幣價釘死之後的 CEBE 變化。
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

  /** 三個度量並排 —— 讓「選錯度量會結論相反」這件事直接看得到。 */
  function paintMeasures(r: StrategyRow): void {
    const bpsPct = (strategy.bpsNow / r.bps0 - 1) * 100;
    const cebePct = (strategy.cebeNow / r.cebe0 - 1) * 100;
    const fixedPct = (strategy.cebeNow / r.cf - 1) * 100;
    const gap = fixedPct - bpsPct;
    const cell = (tag: string, name: string, from: number, to: number,
                  pct: number, note: string, key = false) => `
      <div class="tile${key ? " key" : ""}">
        <div class="k"><span class="formula-tag${key ? " key" : ""}">${tag}</span> ${name}</div>
        <div class="v ${pct >= 0 ? "up" : "down"}">${pct1(pct)}</div>
        <div class="d">${sats(from)} → ${sats(to)} sats<br>${note}</div>
      </div>`;

    el("measures").innerHTML = `
      <div class="grid3" style="margin-bottom:14px">
        ${cell("A", "Gross BPS", r.bps0, strategy.bpsNow, bpsPct,
               "無幣價,但看不見求償權")}
        ${cell("B", "CEBE", r.cebe0, strategy.cebeNow, cebePct,
               "看得見求償權,但被幣價污染")}
        ${cell("C", "CEBE @ 固定幣價", r.cf, strategy.cebeNow, fixedPct,
               `同代入 ${usd0(strategy.priceNow)} —— 純操作`, true)}
      </div>
      <div class="note key">
        <b>A 與 C 的差距就是去槓桿的價值。</b>
        公司自己的 BTC Yield(A)說每股含幣量 ${pct1(bpsPct)},
        但它看不見那些增發的錢換掉了多少求償權。
        把幣價釘死、同時保留求償權之後(C)是 ${pct1(fixedPct)} ——
        中間 <b>${Math.abs(gap).toFixed(1)} 個百分點</b>就是消滅求償權創造出來、
        而 BTC Yield 這個指標結構上看不到的部分。
        <br><br>
        反過來,B 的 ${pct1(cebePct)} 看起來最漂亮,但那主要是幣價
        ${pct1(r.btcRet)} 推的 —— 不該拿來當操作績效。
      </div>

      <div class="note">
        <b>A 的拆解特別乾淨:式子裡沒有幣價,所以只有兩個驅動因子,取對數後精確可加。</b>
        <span class="mono" style="font-size:.84rem">
          log(BPS₁/BPS₀) = log(H₁/H₀) − log(S₁/S₀)</span>
        <br>
        持幣效果 <b class="${r.bpsLayers.held >= 0 ? "up" : "down"}">${
          pct1((Math.exp(r.bpsLayers.held) - 1) * 100)}</b>、
        股數效果 <b class="${r.bpsLayers.shares >= 0 ? "up" : "down"}">${
          pct1((Math.exp(r.bpsLayers.shares) - 1) * 100)}</b>
        —— 完全不需要 Shapley,因為沒有交互作用項可以分。
      </div>`;
  }

  /** 操作層級 —— 這一段才回答「哪一筆操作是加分、哪一筆是減分」。 */
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
          把起點拉到 <b>2026-06</b> 之後就會顯示。上面的三層拆解與反事實不依賴資金流資料,
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
    paintMeasures(r);
    paintLayers(r);
    paintOps(r);
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
