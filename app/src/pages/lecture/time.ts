/** 推導 · 績效歸因 —— L4 的公式解。
 *
 *  推導來源:reference/02-model.md §7–9。
 *  這一層是整個模型最花力氣的地方:E 的式子裡有幣價,不拆開的話,
 *  幣價上漲會被誤讀成公司做得好。 */
import { lectureHead, steps } from "../../components/lecture";
import { symbolTable } from "../../components/symbols";
import { eqCard, tex, texAlign, texBlock } from "../../lib/math";
import type { PageFn } from "../../router";

export const lectureTimePage: PageFn = (root) => {
  root.innerHTML = `
    <div class="wrap">
      ${lectureHead("四 · 績效歸因", "這段漲幅,有多少是公司做出來的",
        `回到最前面那個問題:<b>長期到底有沒有贏過比特幣?</b>
         公司公布的「比特幣收益率」是一段期間的相對增長率,
         <b>但它不告訴你那段變化裡有多少是幣價漲的、多少是公司做出來的。</b>
         <br>這個分不開就什麼都說不清楚 ——
         因為 <a href="#/lecture/structure">資本架構</a>那一節已經說過,
         <b>幣價上漲讓求償權在幣計價下縮水,本來就是這個結構最主要的回報來源</b>。
         它不是公司的功勞,但它確實發生在股東身上。
         這一節把總報酬拆成四層,<b>而且沒有殘差</b>。`)}

      ${symbolTable(["B", "E", "m", "P"])}

      ${steps([
        {
          q: "可加性的來源:對數報酬",
          body: `
            <p>股價是三個因子相乘(見<a href="#/lecture/quantities">推導 · 每股計量</a>),
            取對數之後變成相加:</p>
            ${eqCard(texBlock(String.raw`\ln\frac{P_{1}}{P_{0}}
              = \underbrace{\ln\frac{p_{1}}{p_{0}}}_{\text{幣價}}
              + \underbrace{\ln\frac{E_{1}}{E_{0}}}_{\text{公司}}
              + \underbrace{\ln\frac{m_{1}}{m_{0}}}_{\text{情緒}}`))}
            <p><b>沒有殘差,也不需要決定誰先算。</b>這是恆等式,不是某種分配法則 ——
            大部分「歸因」方法都要在順序或殘差上做武斷選擇,這裡不用。</p>`,
          check: `${tex("(2.2)")} 三項加總等於 ${tex(String.raw`\ln(P_1/P_0)`)}。
            恆等式,驗不過就是真的錯了。`,
        },
        {
          q: "四層歸因",
          body: `
            <p>把中間那層一分為二,就得到四層:</p>
            ${eqCard(texAlign([
              String.raw`\ln\frac{P_{1}}{P_{0}} = &\;\ln\frac{p_{1}}{p_{0}}
                &&\text{幣價}`,
              String.raw`&+ \sum_t \Delta_{t}^{\text{決策}} &&\text{公司決策}`,
              String.raw`&+ \sum_t \Delta_{t}^{\text{行情}} &&\text{求償權縮放}`,
              String.raw`&+ \ln\frac{m_{1}}{m_{0}} &&\text{市場情緒}`,
            ]))}
            <p>第三層值得解釋:固定美元的求償權在幣價上漲時於幣計價下縮小,
            所以<b>即使公司什麼都不做,實得每股也會隨幣價變動</b>。
            那不是公司的功勞,但它確實發生在股東身上 —— 所以要獨立成一層,
            不要併進「公司決策」,也不要併進「幣價」。</p>`,
        },
        {
          q: "逐日鏈結:為什麼沒有殘差",
          body: `
            <p>沿時間一天一天走,第 ${tex("t")} 天拆成兩步:</p>
            ${eqCard(texAlign([
              String.raw`\Delta_{t}^{\text{行情}} &= E(x_{t-1},\,p_{t}) - E(x_{t-1},\,p_{t-1})`,
              String.raw`\Delta_{t}^{\text{決策}} &= E(x_{t},\,p_{t}) - E(x_{t-1},\,p_{t})`,
            ]), "第一步凍結結構、只讓幣價動;第二步再讓結構動,並用那一天的幣價評價。")}
            <p>兩步相加剛好是當天的實現變化,所以逐日加總會完全消去中間項:</p>
            ${eqCard(texBlock(String.raw`\sum_{t}\left(\Delta_{t}^{\text{行情}}
              + \Delta_{t}^{\text{決策}}\right) = E_{T} - E_{0}`),
              "望遠鏡式相消。這是恆等式,不是近似。")}
            <div class="note key">
              <b>第二步是整個方法的關鍵。</b>每個決策只用它<b>發生當下</b>能知道的價格評價,
              所以不含後見之明 —— 否則「在行情上漲前增發」會永遠被判成減分,
              因為賣出去的股票事後看都賣便宜了。
              <br><br>
              先前被廢棄的方法就是犯了這個錯:用期末幣價回頭重估整段歷史。
              那會把一個當下正確的決策評成錯的。
            </div>`,
          check: `${tex("(3.1)")} 決策 + 行情 ${tex(String.raw`= \Delta E`)}(sats);
            ${tex("(3.2)")} 同一條在對數空間也成立。`,
          edge: `同一個拆法要在 <b>sats 空間</b>與<b>對數空間</b>各做一次:
            sats 回答「每股多拿到幾顆聰」,對數回答「佔報酬幾成」。
            <b>兩者不能互換</b> —— 混用會得到看起來合理但無意義的百分比。`,
        },
        {
          q: "中間層的誤標:它不是「公司決策」",
          body: `
            <div class="note key" style="margin-bottom:14px">
              <b>把中間那層標成「公司」是錯的,而且錯得很重要。</b>
            </div>
            <p>回去看 ${tex("E")} 的式子:分子裡有 ${tex("C/p")}。
            所以 ${tex("E")} 的變化混了兩件事 ——</p>
            <ul class="lec-list">
              <li>公司真的做了什麼(發股、回購、買賣幣、付息 → 動到
                ${tex("H")}、${tex("C")}、${tex("S")})</li>
              <li>幣價自己走了多少(只動到 ${tex("p")},卻一樣讓 ${tex("E")} 變)</li>
            </ul>
            <p>要拆開它,先把結構的三個量寫成一個向量,${tex("E")} 就是結構與幣價的函數:</p>
            ${eqCard(texBlock(String.raw`E(x,\,p) = \frac{H - C/p}{S}\times 10^{8},
              \qquad x = (H,\,C,\,S)`))}`,
        },
        {
          q: "市場溢價層:唯一沒有一手來源的一層",
          body: `
            <p>前三層都有出處:幣價看市場、決策看申報、求償權縮放由前兩者算出來。
            <b>只有 ${tex("m")} 沒有。</b>它是把恆等式配平的那一項 ——
            而且在真實資料裡,它經常是<b>最大的一層</b>。</p>
            <div class="note key">
              <b>拆得開不等於解釋得了。</b>
              恆等式保證四層加起來剛好等於總報酬,殘差是零;
              但那不代表我們知道 ${tex("m")} 為什麼動。
            </div>
            <p style="margin-top:14px">結構上它由<a href="#/lecture/structure">〇 · 資本架構</a>
            那個開環前饋控制器維持。這裡要補的是另一半:<b>什麼時候不該假設它還成立。</b></p>
            <div class="lec-table"><table class="mini">
              <thead><tr><th>失效機制</th><th>症狀</th><th>模型上的後果</th></tr></thead>
              <tbody>
                <tr><td><b>反身性螺旋</b></td>
                  <td>幣價跌 → 普通股跌更兇(它承接放大的波動)→ ${tex("m")} 下滑</td>
                  <td>股權管道在數學上關閉</td></tr>
                <tr><td><b>規模陷阱</b></td>
                  <td>持幣變大,維持同樣成長率需要的增發比例非線性上升</td>
                  <td>增發本身侵蝕 ${tex("m")},<b>上限 ${tex("m-1")} 自己下降</b></td></tr>
                <tr><td><b>受眾分流失敗</b></td>
                  <td>同一套論述在不同群體反向作用</td>
                  <td>${tex("m")} 的波動度本身上升</td></tr>
                <tr><td><b>指標被看穿</b></td>
                  <td>市場改用扣求償權的口徑評價</td>
                  <td>${tex("m")} 的分母換了,水準重設</td></tr>
              </tbody>
            </table></div>
            <p style="margin-top:14px">最後一列有點諷刺:
            <b>這個工具做的事,如果足夠多人做,就會改變 ${tex("m")}。</b></p>`,
          edge: `這一節<b>只給機制,不給預測</b>。
            上面四條都說得出「會往哪個方向」,說不出「什麼時候、多少」——
            所以它們是讀數字時的警告,不是模型的一部分。
            ${tex("m")} 在歸因裡仍然是觀測量,不是被解釋的量。`,
        },
        {
          q: "佔比的分母選擇",
          body: `
            <div class="note key" style="margin-bottom:14px">
              <b>不要用淨額當分母。</b>四層會互相抵銷 ——
              某一層 ${tex("+30\\%")}、另一層 ${tex("-28\\%")} 時,
              淨額接近零,佔比就會吐出 ${tex("158\\%")}、${tex("-100\\%")} 這種數字。
            </div>
            <p>改用<b>「佔變動量」</b>:分母是四層絕對值的總和,
            分子是該層的絕對值。這樣每一層的佔比都在 0 到 1 之間,
            而且加起來是 1 —— 它回答的是「這段期間的力氣花在哪裡」,
            不是「淨結果怎麼來的」。</p>
            <p>兩個問題不同,答案也不同。要回答後者,就直接看四層的數值,
            不要再除一次。</p>`,
          edge: `各層互相抵銷得很厲害的期間,<b>任何佔比都會失去意義</b> ——
            那時候該報告的是四個數字本身,不是比例。`,
        },
      ])}

      <div class="note" style="margin-top:30px">
        <b>推導到這裡結束。</b>從資本架構到四層歸因,公式解已經完整:
        <a href="#/lecture/structure">資本架構</a> →
        <a href="#/lecture/quantities">每股計量</a> →
        <a href="#/lecture/tools">資本操作</a> →
        <a href="#/lecture/pairing">來源與用途</a> → 績效歸因。
        同一套結構代進真實參數,就是<a href="#/board">儀表板</a>。
      </div>
    </div>`;
};
