/** 資本結構 —— 常設的結構解釋,不綁任何時間點。
 *
 *  這一頁只回答「這家公司的資本結構長什麼樣、每股含幣量怎麼算、怎麼從圖上讀出來」。
 *  「某段期間發生了什麼」一律放到大事記,避免頁面隨資料更新而過期 ——
 *  先前這裡的標題是「帳面每股在漲,實得每股在縮」,在 2026-06 之後就不再成立了。
 *
 *  全站的公式都收斂在這一頁,用 MathML 排版(src/lib/math.ts),
 *  其他頁需要時以超連結指回來,不重述。 */
import { chronicle, daily, meta, N } from "../data";
import { explorer } from "../components/explorer";
import { toolkitTable } from "../components/toolkit";
import { bn, pct } from "../lib/format";
import { eqCard, tex, texAlign, texBlock } from "../lib/math";
import type { PageFn } from "../router";

/** 符號表的一列。 */
const sym = (s: string, name: string, unit: string, def: string) => `
  <div class="symbol">${tex(s)}
    <div class="symbol-def"><b>${name}</b><span class="symbol-unit">${unit}</span><br>${def}</div>
  </div>`;

/** 操作代數的一列:左邊是操作名稱,右邊是它對每股含幣量做了什麼。 */
const opRow = (name: string, tag: string, eq: string) => `
  <div class="eq-row">
    <div class="eq-row-name">${name}<span class="tag">${tag}</span></div>
    ${texBlock(eq)}
  </div>`;

export const structurePage: PageFn = (root) => {
  const i = N - 1;
  const perShareOf = (k: number) =>
    (daily.common_btc[k]! / (daily.shares[k]! * 1e6)) * 1e8;

  const grossNow = daily.bps[i]!;
  const cebeNow = perShareOf(i);
  const eatenNow = grossNow - cebeNow;
  const claimsNow = daily.debt[i]! + daily.pref_total[i]! - daily.cash[i]!;

  const latest = chronicle[chronicle.length - 1];

  root.innerHTML = `
    <div class="wrap">
      <div class="page-head">
        <p class="eyebrow">資本結構</p>
        <h1>誰排在誰前面</h1>
        <p class="lede">MSTR 的比特幣不是全部屬於普通股股東的。可轉債與優先股排在前面,
          各自有一筆<b>鎖死在美元的固定請求權</b>;普通股拿的是把那些扣掉之後剩下的殘值。
          這一頁解釋這個結構怎麼運作、怎麼量化,以及公司能用哪些工具去改變它。</p>
      </div>

      <div class="grid3" style="margin-bottom:10px">
        <div class="tile"><div class="k">帳面每股</div>
          <div class="v">${Math.round(grossNow).toLocaleString()}</div>
          <div class="d">sats。總持幣 ÷ basic 股數,不含可轉債稀釋</div></div>
        <div class="tile"><div class="k">求償權吃掉</div>
          <div class="v" style="color:var(--bad)">−${Math.round(eatenNow).toLocaleString()}</div>
          <div class="d">sats,佔帳面的 ${pct(eatenNow / grossNow)}<br>
            對應 ${bn(claimsNow)} 的固定美元請求權</div></div>
        <div class="tile" style="border-left:3px solid var(--equity)">
          <div class="k">實得每股含幣量</div>
          <div class="v" style="color:var(--equity)">${Math.round(cebeNow).toLocaleString()}</div>
          <div class="d">sats。這才是股東手上真正的量</div></div>
      </div>

      <div class="note" style="margin-bottom:30px">
        <b>公司官方揭露的 Gross BPS 其實更低。</b>
        上面「帳面每股」用的是 basic 股數,沒算進可轉債假設轉股的稀釋。
        公司最新一期 FWP 用「假設稀釋股數」(${(meta.fwp.assumed / 1e6).toFixed(1)}M,
        比 basic 多 ${((meta.fwp.assumed - meta.fwp.basic) / 1e6).toFixed(1)}M 股)算出來的官方 Gross BPS 是
        <b>${meta.fwp.gross_bps.toLocaleString()} sats</b> —— 比上面 basic 口徑的
        ${Math.round(grossNow).toLocaleString()} sats 低 ${pct(1 - meta.fwp.gross_bps / grossNow)}。
        這個「假設稀釋股數」只有官方在敏感度表裡揭露這一個數字,沒有歷史序列,
        所以「每股持幣」圖上只標成單點,不畫成整條線。</div>

      <h2 style="margin-bottom:6px">符號</h2>
      <p class="lede" style="margin-bottom:18px">
        底下所有式子都用這幾個符號,全站一致。
      </p>
      <div class="symbols">
        ${sym("H", "總持幣", "BTC", "公司帳上全部的比特幣,8-K 逐週揭露")}
        ${sym("S", "在外股數", "股", "普通股 basic 股數,不含可轉債假設轉股")}
        ${sym("C", "求償權", "USD", "排在普通股前面、面額鎖死在美元的部分")}
        ${sym("p", "比特幣價格", "USD", "當下的幣價")}
        ${sym("B", "帳面每股含幣量", "sats", "Gross BPS,也就是公司的 BTC Yield")}
        ${sym("E", "實得每股含幣量", "sats", "CEBE,扣掉求償權後每股真正對應到的幣")}
        ${sym("m", "市場溢價", "倍", "mNAV,市場願意付幾倍的每股公允值")}
        ${sym("P", "MSTR 股價", "USD", "普通股的市場價格")}
      </div>

      <h2 style="margin-bottom:8px">求償權是什麼</h2>
      <p class="lede" style="margin-bottom:16px">
        可轉債與優先股排在普通股前面,各自有一筆固定美元面額的請求權;
        公司手上的美元流動性可以直接抵掉其中一部分。三項加總就是 ${tex("C")}:
      </p>
      ${eqCard(
        texBlock("C = D_{\\text{可轉債}} + L_{\\text{優先股清算優先權}} - U_{\\text{USD 流動性}}"),
        `現金抵在最優先的可轉債層,與 CEBETRACKER 的定義一致 ——
         這樣堆疊起來才會剛好收斂到總持幣,不會多算或少算一塊。`)}

      <h2 style="margin-bottom:8px">兩個每股指標,差別在扣不扣求償權</h2>
      <p class="lede" style="margin-bottom:16px">
        全站只用這兩個名字。技術文獻裡的 Gross BPS、BTC Yield、CEBE
        分別對應下面哪一個,在這裡說明一次,其他頁不再重複。
      </p>

      <div class="card formulas" style="margin-bottom:22px">
        <div class="formula">
          <div class="formula-tag">1</div>
          <div>
            <div class="formula-name">帳面每股含幣量 <span class="formula-alias">Gross BPS / 公司的 BTC Yield</span></div>
            <div class="formula-eq">${texBlock("B = \\frac{H}{S}\\times 10^{8}")}</div>
            <div class="formula-note">
              <b>式子裡沒有 ${tex("p")},也沒有 ${tex("C")}。</b>幣價怎麼波動都不影響它 ——
              這正是公司拿它當 KPI 的原因。缺點是它看不見求償權:
              用發優先股的錢買幣會讓 ${tex("H")} 上升、${tex("B")} 跟著上升,
              但股東一顆也沒多拿到(phantom growth)。
            </div>
          </div>
        </div>
        <div class="formula">
          <div class="formula-tag key">2</div>
          <div>
            <div class="formula-name">實得每股含幣量 <span class="formula-alias">CEBE</span></div>
            <div class="formula-eq">${texBlock("E = \\frac{\\,H - C/p\\,}{S}\\times 10^{8}")}</div>
            <div class="formula-note">
              ${tex("C")} 的面額固定在美元,所以要<b>除以當下幣價 ${tex("p")}</b>
              才能換算成「幾顆幣」。這是股東真正分到的量,代價是
              <b>幣價跑進式子裡了</b> —— 公司什麼都不做,幣價一漲 ${tex("E")} 也會上升。
            </div>
          </div>
        </div>
      </div>

      ${eqCard(
        texBlock("B - E = \\frac{C}{p\\,S}\\times 10^{8}"),
        `兩者相減就是<b>求償權當下吃掉的每股含幣量</b>,目前是
         ${Math.round(eatenNow).toLocaleString()} sats。
         分母有 ${tex("p")}:幣價漲,同一筆求償權吃掉的幣就變少,
         普通股不用多買一顆,${tex("E")} 就會自己往 ${tex("B")} 靠 —— 這就是槓桿。
         反過來幣價跌的時候,它也會把跌幅放大。`)}

      <h2 style="margin-bottom:8px">怎麼把「決策」跟「行情」分開</h2>
      <p class="lede" style="margin-bottom:16px">
        ${tex("E")} 的式子裡有 ${tex("p")},所以它的變化混了兩件事:公司做了什麼、
        以及幣價自己走了多少。<a href="#/strategy">績效歸因</a>頁用<b>逐日鏈結</b>把兩者拆開。
        先把結構的三個量寫成一個向量,${tex("E")} 就是結構與幣價的函數:
      </p>
      ${eqCard(texBlock(
        "E(x,\\,p) = \\frac{\\,H - C/p\\,}{S}\\times 10^{8}"
        + ",\\qquad x = (H,\\,C,\\,S)"))}
      <p class="lede" style="margin-bottom:16px">
        接著沿時間一天一天走。第 ${tex("t")} 天拆成兩步:先凍結結構只讓幣價動,
        再讓結構動、並用<b>當天的</b>幣價評價。
      </p>
      ${eqCard(texAlign([
        "\\Delta_{t}^{\\text{行情}} &= E(x_{t-1},\\,p_{t}) - E(x_{t-1},\\,p_{t-1})",
        "\\Delta_{t}^{\\text{決策}} &= E(x_{t},\\,p_{t}) - E(x_{t-1},\\,p_{t})",
      ]), `第二步是關鍵:每個決策只用它<b>發生當下</b>能知道的幣價評價,
           所以不含後見之明 —— 否則「在行情上漲前增發」會永遠被判成減分,
           因為賣出去的股票事後看都賣便宜了。`)}
      <p class="lede" style="margin-bottom:16px">
        兩步相加剛好是當天的實現變化,所以逐日加總會<b>完全消去中間項</b>,不留殘差:
      </p>
      ${eqCard(texAlign([
        "\\sum_{t=1}^{T}\\left(\\Delta_{t}^{\\text{行情}} + \\Delta_{t}^{\\text{決策}}\\right)"
        + " &= \\sum_{t=1}^{T}\\left(E(x_{t},\\,p_{t}) - E(x_{t-1},\\,p_{t-1})\\right)",
        "&= E_{T} - E_{0}",
      ]), `「行情」與「決策」兩個數字相加<b>精確等於</b>期間的實現變化,
           這是恆等式而不是近似 —— 不需要決定誰先算,也沒有分配殘差的問題。`)}

      <h2 style="margin-bottom:8px">股價的恆等式</h2>
      <p class="lede" style="margin-bottom:16px">
        股價可以精確寫成三個因子相乘,沒有剩下的部分:
      </p>
      ${eqCard(texBlock("P = m \\times \\frac{E}{10^{8}} \\times p"))}
      <p class="lede" style="margin-bottom:16px">
        取對數之後相乘變成相加,報酬就能<b>無殘差地</b>拆成三層:
      </p>
      ${eqCard(texBlock(
        "\\ln\\frac{P_{1}}{P_{0}} ="
        + " \\underbrace{\\ln\\frac{p_{1}}{p_{0}}}_{\\text{幣價}}"
        + " + \\underbrace{\\ln\\frac{E_{1}}{E_{0}}}_{\\text{公司}}"
        + " + \\underbrace{\\ln\\frac{m_{1}}{m_{0}}}_{\\text{情緒}}"),
        `中間那一項就是上面拆成「決策 + 行情」的對象。
         拆解結果見<a href="#/strategy">績效歸因</a>。`)}

      <h2 style="margin-bottom:8px">公司能動用的工具</h2>
      <p class="lede" style="margin-bottom:16px">
        改變這個結構的方法是有限且可列舉的。每一項對求償權、股數、持幣的作用不同,
        對 ${tex("E")} 的淨效果也不同 —— <b>真正會讓 ${tex("E")} 上升的只有右邊標成加分的那幾項</b>。
        公司在不同時期用的是不同組合,那就是<a href="#/chronicle">大事記</a>在記錄的事。
      </p>
      ${toolkitTable()}

      <h3 style="margin:30px 0 6px">每一種操作的代數</h3>
      <p class="lede" style="margin-bottom:14px">
        上表的「加分／減分」不是判斷,是算出來的。以下用 ${tex("c")} 表示這筆操作
        動用的美元金額,${tex("F")} 表示買回標的的面額。
      </p>
      <div class="eq-rows">
        ${opRow("用現金買幣", "淨效果恰好是零",
          "\\Delta\\!\\left(H - \\frac{C}{p}\\right) = \\frac{c}{p} - \\frac{c}{p} = 0")}
        ${opRow("折價回購求償權", "只有折價的部分進得來",
          "\\Delta E = \\frac{F - c}{p\\,S}\\times 10^{8} > 0 \\quad (c < F)")}
        ${opRow("股息與債息", "結構上必然為負",
          "\\Delta E = -\\frac{c}{p\\,S}\\times 10^{8} < 0")}
      </div>

      <div class="eq-card" style="border-left:3px solid var(--equity)">
        <p class="eq-note" style="border-top:0;padding-top:0;margin:0 0 14px">
          <b>普通股 ATM 增發比較繞,值得單獨推一次。</b>
          以每股 ${tex("P")} 發出 ${tex("n")} 股、募到的 ${tex("nP")} 全部拿去抵求償權,
          「增發後的每股含幣量要比增發前高」這個條件可以一路化簡:
        </p>
        ${texAlign([
          "\\frac{\\,H - (C - nP)/p\\,}{S + n} &> \\frac{\\,H - C/p\\,}{S}",
          "\\iff\\quad \\frac{P}{p}\\times 10^{8} &> E",
          "\\iff\\quad m &> 1",
        ])}
        <p class="eq-note">
          三行是等價的。第二行的意思是<b>發行價換算成幣,要比當下的每股含幣量多</b>;
          把股價恆等式代進去,它就化簡成第三行 ——
          <b>增發是否增值,完全等於 mNAV 是否大於 1</b>,跟募到多少、發了幾股都無關。
          可轉債轉股是同一個條件,只是把 ${tex("P")} 換成轉換價。
          <br><br>
          推導有一個前提:${tex("E > 0")}。當求償權大到把普通股吃光時不等式會反向 ——
          那正是<a href="#/chronicle">大事記</a>裡「壓力測試」那一段在講的處境。
        </p>
      </div>

      <div class="note key" style="margin:26px 0 30px">
        <b>目前在哪一段?</b>
        <a href="#/chronicle">${latest ? latest.title : "—"}</a>
        ${latest ? `—— ${latest.subtitle}。${latest.ongoing ? "進行中" : ""}` : ""}
      </div>

      <h2 style="margin-bottom:12px">從圖上讀出來</h2>
      <div id="explorer"></div>

      <div class="note" style="margin-top:24px">
        <b>怎麼從圖上讀出每股含幣量。</b>
        BTC 計價那張圖的下緣是求償權(依清償順位堆疊),上緣的黑線是總持幣 ${tex("H")},
        中間那條橘色帶子就是普通股。帶子越薄代表 ${tex("E")} 越小。
        切到「每股」模式後,縱軸變成 sats／股,帶子的厚度直接就是 ${tex("E")} 的數值 ——
        游標標籤會同時顯示「帳面每股」與「實得每股」,兩者相減就是上面
        ${tex("B - E")} 那一項。
        下面那張美元計價的圖完全看不出這件事,因為求償權與資產同時以美元計價,
        比例變化被價格漲跌蓋掉了。
      </div>

      <div class="grid2" style="margin-top:30px">
        <div>
          <h3 style="margin-bottom:8px">為什麼「多買幣」不一定對股東有利</h3>
          <p style="font-size:.9rem;color:var(--ink-2);margin:0">
            用發優先股募到的錢買幣,${tex("H")} 上升,${tex("B")} 也跟著上升,
            看起來像在替股東累積比特幣。但同一筆交易等量增加了 ${tex("C")},
            扣掉之後普通股一顆都沒多拿到 —— 就是上面「用現金買幣」那一行算出來的零。
            真正會讓 ${tex("E")} 上升的只有三種:mNAV 大於 1 時增發普通股、
            以折價回購優先股或可轉債、或可轉債轉股讓求償權直接消失。</p>
        </div>
        <div>
          <h3 style="margin-bottom:8px">為什麼求償權會自己縮小</h3>
          <p style="font-size:.9rem;color:var(--ink-2);margin:0">
            ${tex("C")} 的面額固定在美元,所以幣價一漲,${tex("C/p")} 就縮小,
            ${tex("E")} 不用多買一顆就會自己長回來。這個效果有多大、在什麼價位會反轉,
            <a href="#/pricing">槓桿與定價</a>那一頁把彈性算給你看。</p>
        </div>
      </div>

      <p style="font-size:.8rem;color:var(--ink-3);margin-top:22px">
        堆疊方式:現金抵減最優先的可轉債層,其餘各優先股系列依清償順位往上疊,
        頂端是普通股殘量,總和精確等於當日總持有量(黑線)。</p>
    </div>`;

  return explorer(root.querySelector<HTMLElement>("#explorer")!, {
    charts: ["perShare", "riverBtc", "riverUsd"], showIdentity: false,
  });
};
