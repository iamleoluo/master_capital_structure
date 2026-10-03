/** 推導 · 每股計量 —— L1 的公式解。
 *
 *  推導來源:reference/02-model.md §1–6。這一頁是那幾節的網頁版,
 *  不是重寫 —— 改模型時兩邊要一起改,reference/verify.py 會驗同號式子。 */
import { symbolTable } from "../../components/symbols";
import { lectureHead, steps } from "../../components/lecture";
import { eqCard, tex, texAlign, texBlock } from "../../lib/math";
import type { PageFn } from "../../router";

export const lectureQuantitiesPage: PageFn = (root) => {
  root.innerHTML = `
    <div class="wrap">
      ${lectureHead("一 · 每股計量", "公司公布的每股,與股東實得的每股",
        `<b>公司公布的指標叫「每股比特幣含量」</b> —— 持幣除以股數。
         <b>它的分子是總持幣,不扣求償權</b>,所以它回答的是「幣堆相對股數有多大」,
         不是「我這一股實得多少」。
         <b>這一節補上那一段</b>:把求償權扣掉之後的那把尺定義清楚,
         並一路接到股價的恆等式。`)}

      ${symbolTable(["H", "S", "C", "p"])}

      ${steps([
        {
          q: "口徑的源頭:兩種 mNAV",
          body: `
            <p>談這家公司幾乎只會談一個詞:<b>mNAV</b> —— 市值相對於持幣價值的倍數。
            但 mNAV 有兩種,而且<b>差別只有一個:分母算不算優先股與可轉債先拿走的那一塊</b>。</p>
            <p>同一個選擇,把分母從市值換成股數,就變成「每股含幣量」。
            所以<b>兩個 mNAV 與兩把每股的尺,是同一件事的兩種表達</b>:</p>
            <div class="lec-table"><table class="mini">
              <thead><tr><th>分母用什麼</th><th>相對市值</th><th>相對股數</th></tr></thead>
              <tbody>
                <tr><td>全部持幣 ${tex("Hp")}</td>
                    <td>basic mNAV</td>
                    <td><b>帳面每股含幣量 ${tex("B")}</b></td></tr>
                <tr><td>扣求償權後 ${tex("Hp - C")}</td>
                    <td><b>CEBE mNAV</b>(本站的 ${tex("m")})</td>
                    <td><b>實得每股含幣量 ${tex("E")}</b></td></tr>
              </tbody>
            </table></div>
            <div class="note key" style="margin-top:14px">
              <b>先有口徑,才有指標。</b>
              公司公布的「每股比特幣含量 / BTC Yield」是上面那一列 ——
              分子是總持幣,不扣求償權。這個網站整套算的是下面那一列。
              <div style="margin-top:10px">
                不是哪一列比較準,是<b>它們回答不同的問題</b>:
                上一列問「幣堆相對股數有多大」,下一列問「我這一股實得多少」。
                同一天可以一個折價、一個溢價,因為分母差了一整個求償權。
              </div>
            </div>
            <p style="margin-top:14px">整頁剩下的部分,就是把下面那一列定義清楚 ——
            而要定義它,最少需要<b>四個量</b>。前兩個是直覺的:幣要除以股數才是每股。
            真正的內容在第三與第四個 ——
            而<b>第四個之所以出現,完全是因為第三個以美元計價</b>。</p>
            ${eqCard(texBlock(String.raw`\text{每股} = \frac{H - C/p}{S}`),
              "求償權是美元、持幣是幣,兩個單位要靠幣價換算才能相減。這一步決定了後面所有的複雜度,包括為什麼必須把「決策」與「行情」拆開。")}`,
          edge: `這四個量**不包含營運業務**。MSTR 原本的軟體事業有自己的現金流,
            但相對於比特幣部位的規模小到可以忽略 —— 這是一個刻意的簡化,不是疏漏。`,
        },
        {
          q: "兩個每股指標:帳面與實得",
          body: `
            <p>同一堆幣,兩種算法。差別只有一項:<b>要不要把求償權扣掉</b>。</p>
            ${eqCard(texAlign([
              String.raw`B &= \frac{H}{S}\times 10^{8} &&\quad\text{帳面每股含幣量}`,
              String.raw`E &= \frac{H - C/p}{S}\times 10^{8} &&\quad\text{實得每股含幣量}`,
            ]), "單位都是 sats(1 BTC = 1e8 sats),所以兩者可以直接相減。")}
            <p>${tex("B")} 的式子裡<b>沒有 ${tex("C")}、也沒有 ${tex("p")}</b> ——
            所以任何只動到求償權的操作,在 ${tex("B")} 上恆等於零。
            ${tex("E")} 看得見求償權,代價是也看得見幣價。</p>
            ${eqCard(texBlock(String.raw`B - E = \frac{C}{p\,S}\times 10^{8}`),
              "兩把尺的差就是「求償權吃掉的每股幣量」。幣價上漲時固定的美元求償權在幣計價下縮小,這個差自己會收斂。")}
            <p><b>兩欄不一致的地方,就是這家公司最常被誤讀的地方。</b>
            公司的 KPI 用 ${tex("B")},而股東真正拿到的是 ${tex("E")}。</p>`,
          check: `${tex("(1.2)")} 普通股殘量 ${tex(String.raw`= H - C/p`)}`,
        },
        {
          q: "求償權的計算與現金沖抵",
          body: `
            <p>可轉債與優先股在清償順位上排在普通股前面,各自有一筆<b>固定美元面額</b>的
            請求權。公司手上的美元流動性可以直接抵掉其中一部分 ——
            那筆錢本來就是準備拿去付利息與股息的。</p>
            <p>這條式子把<b>一整座階梯壓成一個數</b>。誰排在誰前面、哪些條款會改變
            實質負擔(股息水壩、累積與非累積、沒有一層設質),在
            <a href="#/lecture/structure">〇 · 資本架構</a> ——
            讀過那一節,下面三個選擇才看得出它們各自偏在哪一邊。</p>
            ${eqCard(texBlock(String.raw`C = \underbrace{D}_{\text{可轉債}} + \underbrace{L}_{\text{優先股清算優先權}} - \underbrace{U}_{\text{美元流動性}}`))}
            <p>三個選擇值得記下來:</p>
            <ol class="lec-list">
              <li><b>優先股用清算優先權,不用市價。</b>法律上公司欠的就是那個金額。
                這個選擇有已知的偏差 —— 市場把優先股標在面額以下時,面額口徑會高估求償權。</li>
              <li><b>現金抵在最優先的可轉債層</b>,而不是平均分攤。換一種抵法,
                堆疊圖就不會剛好收斂到 ${tex("H")}。</li>
              <li><b>${tex("C")} 可以是負的</b>(流動性大於求償權),式子照樣成立,不需要特例。</li>
            </ol>
            <div class="note key" style="margin-top:14px">
              <b>${tex("U")} 是全部的美元流動性,不是只有 USD Reserve。</b>
              公司自己把它分成兩塊:USD Reserve 由董事會政策指定,<b>只能付優先股股息與債息</b>,
              由賣幣或資本市場活動補充;其餘是募資到部署之間的過路現金,通常當週就用掉。
              代數不區分這兩塊,因為 ${tex("C")} 問的是「有多少美元可以抵掉求償權」,
              不問那筆錢被指定做什麼用。
            </div>`,
          edge: `可轉債沒有公開市價,所以面額口徑與市價口徑在它身上沒有差別 ——
            也就是說,「面額口徑高估多少」這個估計是一個<b>下限</b>。`,
        },
        {
          q: "股數口徑:三個分母的取捨",
          body: `
            <p>分子是「屬於普通股的幣」,分母就必須是「普通股的股數」—— 聽起來是廢話,但這家公司<b>同時存在三個股數口徑</b>,而且差距不小。</p>
            <div class="lec-table"><table class="mini">
              <thead><tr><th>分母</th><th>包含什麼</th><th>誰在用</th></tr></thead>
              <tbody>
                <tr><td>basic shares</td><td>實際在外的普通股</td><td>本站所有圖表</td></tr>
                <tr><td>FDSO</td><td>再加上已歸屬的員工權益</td><td>公司的 Net BPS</td></tr>
                <tr><td>assumed diluted</td><td>再假設全部可轉債都轉股</td><td>公司的 Gross BPS</td></tr>
              </tbody></table></div>
            <p>三者不可混用。同一個「每股含幣量」用不同分母算出來的數字會差上幾個百分點,
            而那個差距足以讓一段期間的結論反向。</p>`,
          check: `官方 FWP 的敏感度表用的是公司自己的定義。管線拿它當回歸錨點,
            對不上就讓建置失敗 —— 那是確認分母沒有被悄悄換掉的方法。`,
        },
        {
          q: "槓桿:兩個彈性與帳面歸零點",
          body: `
            <p>先看曲線與橫軸的交點。${tex("E = 0")} 時:</p>
            ${eqCard(texBlock(String.raw`H = \frac{C}{p} \quad\Longrightarrow\quad p_{0} = \frac{C}{H}`),
              `也就是平均每顆幣背了多少美元的求償權。幣價跌到這裡,普通股的<b>帳面</b>殘值歸零。`)}
            <div class="note key" style="margin-bottom:14px">
              <b>⚠️ 這不是清算觸發價。</b>沒有一層求償權以比特幣設質
              (<a href="#/lecture/structure">〇 · 資本架構</a>),所以不存在強制平倉機制。
              跌破 ${tex("p_{0}")} 只代表帳面殘值為負,公司照樣運作;
              真正會致命的是付不出股息與利息。
            </div>
            <p>再看放大倍數。每股殘值(美元)是 ${tex(String.raw`(Hp-C)/S`)},對幣價取彈性:</p>
            ${eqCard(texAlign([
              String.raw`A(p) &= \frac{\mathrm{d}\ln\left((Hp-C)/S\right)}{\mathrm{d}\ln p} = \frac{Hp}{Hp - C} = \frac{1}{1 - p_{0}/p}`,
              String.raw`\frac{\mathrm{d}\ln E}{\mathrm{d}\ln p} &= A(p) - 1 = \frac{C}{Hp - C}`,
            ]), "兩個彈性剛好差一個 1。")}
            <p>這解釋了為什麼美元計價與幣計價的兩張圖長得不一樣:差的那 1 倍
            <b>就是幣價本身漲了</b>,不是公司替你多賺到的幣。</p>
            <p>${tex("A")} 會隨幣價上升而自然下降(分母裡求償權的比重變小),
            所以<b>槓桿會自己衰減</b> —— 除非公司持續補倉把它釘住。</p>`,
          edge: `${tex("A - 1")} 是<b>導數</b>,只在小變動下成立。單日大幅波動時
            實測比值與它會有可觀的落差 —— 那不是模型錯了,是導數本來就只描述極限。
            恆等式(下一節)沒有這個問題。`,
        },
        {
          q: "股價恆等式",
          body: `
            <p>到這裡都還在講「公司有多少幣」。要連到股價,需要一座橋 —— 市場願意付幾倍:</p>
            ${eqCard(texBlock(String.raw`m = \frac{P}{\;E/10^{8} \times p\;}
              \qquad\Longrightarrow\qquad \boxed{\;P = m \times \frac{E}{10^{8}} \times p\;}`))}
            <div class="note key">
              <b>注意 ${tex("m")} 的分母是 ${tex("E")},不是 ${tex("H")}。</b>
              這不是隨便選的 —— 恆等式要成立,${tex("m")} 的分母就必須跟 ${tex("E")} 一致。
              代價是這個 ${tex("m")} 跟一般人講的 mNAV<b>不是同一個數</b>:
              一般的 mNAV 分母是總持幣,本站的分母是殘值。
              同一天可以一個折價、一個溢價,因為分母差了一整個求償權。
              <br><br>
              所以看到 ${tex("m")} 偏高不要直接讀成「市場很熱」——
              它主要反映的是<b>槓桿有多高</b>。
            </div>`,
          check: `${tex("(2.1)")} ${tex(String.raw`P = m \times E/10^{8} \times p`)},
            相對誤差小於 ${tex("5\\times10^{-4}")}。這是恆等式,不是近似 ——
            驗不過就是資料或模型真的錯了。`,
        },
      ])}

      <div class="note" style="margin-top:30px">
        <b>接下來:</b>這四個量會怎麼變?
        <a href="#/lecture/tools">推導 · 資本操作</a>把公司能做的動作窮舉出來 ——
        而且因為位置只有四個,動作是<b>可以列完</b>的。
      </div>
    </div>`;
};
