/** 講義 · 時間 —— L4 的公式解。
 *
 *  推導來源:reference/01-model.md §7–9。
 *  這一層是整個模型最花力氣的地方:E 的式子裡有幣價,不拆開的話,
 *  幣價上漲會被誤讀成公司做得好。 */
import { lectureHead, steps } from "../../components/lecture";
import { eqCard, tex, texAlign, texBlock } from "../../lib/math";
import type { PageFn } from "../../router";

export const lectureTimePage: PageFn = (root) => {
  root.innerHTML = `
    <div class="wrap">
      ${lectureHead("四 · 時間", "哪些是公司做的,哪些只是行情",
        `前三頁都在講「做了這個動作會怎樣」。這一頁加入時間序,回答
         <b>「觀察到的這段歷史裡,每一塊變化分別來自哪裡」</b> ——
         而這件事比它看起來難,因為實得每股的式子裡本來就有幣價。`)}

      ${steps([
        {
          q: "取對數,報酬就可加",
          body: `
            <p>股價是三個因子相乘(見<a href="#/lecture/quantities">講義 · 量</a>),
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
          q: "但中間那一層不是「公司」",
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
          q: "逐日鏈結:一天拆成兩步",
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
          q: "四層",
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
          q: "佔比要用什麼當分母",
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
        <b>講義到這裡結束。</b>四層的公式解已經完整:
        <a href="#/lecture/quantities">量</a> →
        <a href="#/lecture/tools">工具</a> →
        <a href="#/lecture/pairing">配對</a> → 時間。
        同一套結構代進真實參數,就是數值解 —— 見<a href="#/">總覽</a>。
      </div>
    </div>`;
};
