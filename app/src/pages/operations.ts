/** 資本操作 —— 公司能對這個結構做什麼,以及每一個動作的代數。
 *
 *  與「資本結構」頁的分工:那一頁回答「這個結構長什麼樣」(靜態,含河流圖),
 *  這一頁回答「公司能對它做什麼」(動作)。符號與兩個每股指標的定義一律
 *  留在資本結構頁,這裡只以超連結指回去,不重述。
 *
 *  編排順序是刻意的:
 *    1. 工具箱表格      —— 有哪些工具(方向)
 *    2. 先推一個給你看  —— ATM 增發的完整推導,示範這些條件怎麼來的
 *    3. 每一把的代數    —— 七把工具,B 與 E 並排
 *    4. 組合操作        —— 真實世界是兩把接在一起用的
 *    5. 怎麼評價        —— 逐日鏈結,接到績效歸因頁 */
import { chronicle } from "../data";
import { toolkitAlgebra, toolkitTable } from "../components/toolkit";
import { perShareDefs, symbolTable } from "../components/symbols";
import { eqCard, tex, texAlign } from "../lib/math";
import type { PageFn } from "../router";

/** 組合操作的一張卡:標題 + 推導 + 白話。 */
const combo = (n: string, title: string, lead: string,
               math: string, note: string) => `
  <div class="combo">
    <div class="combo-head"><span class="combo-n">${n}</span><b>${title}</b></div>
    <p class="combo-lead">${lead}</p>
    ${math}
    <p class="eq-note">${note}</p>
  </div>`;

export const operationsPage: PageFn = (root) => {
  const latest = chronicle[chronicle.length - 1];

  root.innerHTML = `
    <div class="wrap">
      <div class="page-head">
        <p class="eyebrow">資本操作</p>
        <h1>公司能做的動作是可以列舉的</h1>
        <p class="lede">改變資本結構的方法有限且可窮舉。每一個動作對
          <b>帳面每股 ${tex("B")}</b> 與 <b>實得每股 ${tex("E")}</b> 的效果都有明確的代數,
          而且這兩欄<b>經常是相反的</b> —— 那個相反就是這家公司最常被誤讀的地方。
          符號與兩個指標的定義見<a href="#/structure/model">資本結構</a>頁;
          公司在各個時期實際用了哪幾把,見<a href="#/chronicle">大事記</a>。</p>
      </div>

      <h2 style="margin-bottom:6px">先把符號定好</h2>
      <p class="lede" style="margin-bottom:16px">
        這一頁全部是代數,所以符號放在最前面,不用跳頁去查。
        上排是<b>結構量</b>(這家公司現在長什麼樣),下排是<b>操作量</b>
        (這一筆動作有多大)。完整推導與河流圖見
        <a href="#/structure/model">求償權與殘值</a>。
      </p>
      ${symbolTable(["H", "S", "C", "p", "m", "P"])}
      <p class="lede" style="margin:18px 0 14px">
        底下每一條式子都在問同一件事:這個動作讓這兩個指標往哪邊走?
      </p>
      ${perShareDefs()}
      <p class="lede" style="margin:20px 0 14px">
        操作量則描述單筆動作的大小:
      </p>
      ${symbolTable(["c", "F", "n", "x", "d"])}

      <div class="note key" style="margin:30px 0">
        <b>目前在哪一段?</b>
        <a href="#/chronicle">${latest ? latest.title : "—"}</a>
        ${latest ? `—— ${latest.subtitle}。${latest.ongoing ? "進行中" : ""}` : ""}
      </div>

      <h2 style="margin-bottom:8px">工具箱</h2>
      <p class="lede" style="margin-bottom:16px">
        先看方向。<b>真正會讓 ${tex("E")} 上升的只有標成加分的那幾項</b> ——
        其餘不是中性,就是要看價格條件。
      </p>
      ${toolkitTable()}

      <h2 style="margin:38px 0 8px">先推一個給你看:普通股 ATM 增發</h2>
      <p class="lede" style="margin-bottom:16px">
        底下那些條件不是背出來的,是推出來的。這一個最繞,推完之後其餘六把就好讀了。
      </p>
      ${eqCard(texAlign([
        "\\frac{\\,H - (C - nP)/p\\,}{S + n} &> \\frac{\\,H - C/p\\,}{S}",
        "\\iff\\quad \\frac{P}{p}\\times 10^{8} &> E",
        "\\iff\\quad m &> 1",
      ]), `以每股 ${tex("P")} 發出 ${tex("n")} 股、募到的 ${tex("nP")} 全部拿去抵求償權,
        「增發後的每股含幣量要比增發前高」就是第一行。三行是等價的:
        第二行的意思是<b>發行價換算成幣,要比當下的實得每股多</b>;
        把<a href="#/structure/model">股價恆等式</a>代進去,就化簡成第三行 ——
        <b>增發是否增值,完全等於 mNAV 是否大於 1</b>,跟募到多少、發了幾股都無關。
        可轉債轉股是同一個條件,只是把 ${tex("P")} 換成轉換價。
        <br><br>
        推導有一個前提:${tex("E > 0")}。當求償權大到把普通股吃光時不等式會反向 ——
        那正是<a href="#/chronicle">大事記</a>裡「壓力測試」那一段在講的處境。`)}

      <h2 style="margin:38px 0 8px">每一把工具的代數</h2>
      <p class="lede" style="margin-bottom:16px">
        <b>兩欄請橫著讀</b>:同一個動作對 ${tex("B")} 與 ${tex("E")} 的效果
        常常是相反的,不一致的地方就是這家公司最常被誤讀的地方。
      </p>
      ${toolkitAlgebra()}

      <h2 style="margin:38px 0 8px">組合操作:真實世界是這樣用的</h2>
      <p class="lede" style="margin-bottom:18px">
        上面一把一把拆開是為了把代數講乾淨,但公司幾乎不會只做一個動作 ——
        錢要從某處來,才能往某處去。底下三個是這家公司實際在跑的組合,
        每一個都是<b>兩把工具接在一起</b>。
        三個有一個共同特徵:<b>${tex("B")} 一定下降,而 ${tex("E")} 可以上升。</b>
      </p>

      <div class="combos">
        ${combo("A", "賣幣 → 增加美元儲備",
          `按市價賣掉 ${tex("x")} 顆,換得的 ${tex("xp")} 美元進入 USD 儲備,
           等量抵減求償權。`,
          texAlign([
            "\\Delta E &= \\frac{-x + xp/p}{S}\\times 10^{8} = 0",
            "\\Delta B &= -\\frac{x}{S}\\times 10^{8} < 0",
          ]),
          `<b>對股東實得恰好中性。</b>幣少了,但美元流動性等量抵掉求償權,
           分子一毛沒變。可是公司自己的 KPI 直接少一塊 ——
           所以一家用 ${tex("B")} 當 KPI 的公司,天生就不想做這件事,
           即使它對股東毫無損害。「賣幣求生」的說法也是在這裡失效的:
           賣幣本身不會讓股東變窮,真正決定好壞的是<b>那筆美元接下來拿去做什麼</b>。`)}

        ${combo("B", "賣幣 → 折價回購優先股",
          `承上,再用那筆 ${tex("c = xp")} 買回面額 ${tex("F")} 的優先股,
           且 ${tex("c < F")}(折價)。`,
          texAlign([
            "\\Delta E &= \\frac{F - c}{p\\,S}\\times 10^{8} > 0",
            "\\Delta B &= -\\frac{x}{S}\\times 10^{8} < 0",
          ]),
          `賣幣那一步是中性的(組合 A),回購那一步把折價收進來。所以
           <b>整個組合的加分恰好等於折價本身 ${tex("F - c")}</b>,
           跟賣了多少幣無關 —— 賣越多不會加分越多,只會讓 ${tex("B")} 越難看。
           這也是為什麼「公司賣了幣」這個事實本身不能當結論。`)}

        ${combo("C", "ATM 增發 → 折價回購優先股",
          `不動用持幣:發 ${tex("n")} 股募得 ${tex("c = nP")},
           拿去買回面額 ${tex("F")} 的優先股,折價率 ${tex("d = 1 - c/F")}。`,
          texAlign([
            "\\frac{\\,H - (C - F)/p\\,}{S + n} &> \\frac{\\,H - C/p\\,}{S}",
            "\\iff\\quad \\frac{F/n}{p}\\times 10^{8} &> E",
            "\\iff\\quad m &> 1 - d",
          ]),
          `<b>這是三個裡面最重要的。</b>單純 ATM 增發要 ${tex("m > 1")} 才加分
           (上面推過);但如果募到的錢是拿去<b>折價 ${tex("d")}</b> 買回優先股,
           門檻就降到 ${tex("m > 1 - d")}。
           <br><br>
           這解釋了一件單看 mNAV 會覺得不合理的事:優先股被打到只認
           73% 面額的那段時間,${tex("d = 0.27")},門檻掉到 ${tex("m > 0.73")} ——
           <b>即使普通股本身在折價交易,增發去買回優先股仍然是加分的</b>。
           折價越深,這把工具的適用區間越寬。<a href="#/chronicle">大事記</a>裡
           「信用被打折,折價買回的機會才存在」講的就是這個代數。`)}
      </div>

      <div class="note" style="margin-top:8px">
        <b>三個組合都讓 ${tex("B")} 下降。</b>
        A、B 賣掉了幣,C 增加了股數,而 ${tex("B = H/S")} 只看得到這兩件事。
        但 B、C 對股東是實實在在加分的 —— 加分的來源(折價)整個落在
        ${tex("B")} 測不到的地方,因為它的式子裡根本沒有求償權這一項。
        這個分歧在<a href="#/strategy">績效歸因</a>頁量化過:
        同一段期間兩把尺連正負號都相反。
      </div>

      <h2 style="margin:38px 0 8px">怎麼判斷做得好不好</h2>
      <p class="lede" style="margin-bottom:16px">
        ${tex("E")} 的式子裡有幣價,所以它的變化混了「公司做了什麼」與
        「幣價自己走了多少」。把結構的三個量寫成 ${tex("x = (H,\\,C,\\,S)")},
        沿時間一天一天走,每天拆成兩步:先凍結結構只讓幣價動,
        再讓結構動、並用<b>當天的</b>幣價評價。
      </p>
      ${eqCard(texAlign([
        "\\Delta_{t}^{\\text{行情}} &= E(x_{t-1},\\,p_{t}) - E(x_{t-1},\\,p_{t-1})",
        "\\Delta_{t}^{\\text{決策}} &= E(x_{t},\\,p_{t}) - E(x_{t-1},\\,p_{t})",
      ]), `逐日加總會完全消去中間項,兩者相加<b>精確等於</b>期間的實現變化。
        關鍵在第二步:每個決策只用它<b>發生當下</b>能知道的幣價評價,
        所以不含後見之明 —— 否則「在行情上漲前增發」會永遠被判成減分,
        因為賣出去的股票事後看都賣便宜了。
        <br><br>
        拆解結果與逐筆操作的貢獻,見<a href="#/strategy">績效歸因</a>。`)}
    </div>`;

  return () => {};
};
