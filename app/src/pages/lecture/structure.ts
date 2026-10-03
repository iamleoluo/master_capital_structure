/** 推導 · 〇 · 資本架構 —— 讀後面四節之前要先知道的事。
 *
 *  推導來源:reference/01-architecture.md,主線在 reference/00-purpose.md。
 *  順序不可以換:目的 → 三代工具(風險往外推)→ 條款 → ⚠️ 轉嫁≠不用管
 *  → 槓桿≠每股含幣量 → 上界。
 *
 *  ⚠️ 受 test_lecture_is_formula_only 管:不得出現觀測值。
 *  條款只能放類型,實測數字在總覽與儀表板。 */
import { lectureHead, steps } from "../../components/lecture";
import { symbolTable } from "../../components/symbols";
import { PLACE } from "../../formulas";
import { eqCard, tex, texBlock } from "../../lib/math";
import type { PageFn } from "../../router";

const LADDER: Array<[string, string, string, string]> = [
  ["1", "可轉換無擔保債券", "法律債務 —— 違約觸發破產", "可按溢價轉為普通股"],
  ["2", "高級固定優先股", "累積;未付則調升票息", "無"],
  ["3", "浮動優先股", "累積;欠息計入本金", "無"],
  ["4", "混合型優先股", "累積", "嵌入式買權,可轉普通股"],
  ["5", "次級非累積優先股", "非累積 —— 欠息即永久放棄", "無"],
  ["6", "外幣計價優先股", "累積", "無"],
  ["⊥", "普通股", "無股息;承接全部殘值", "—"],
];

export const lectureStructurePage: PageFn = (root) => {
  root.innerHTML = `
    <div class="wrap">
      ${lectureHead("〇 · 資本架構", "風險的轉嫁路徑與其約束",
        `後面四節從四個原始量開始。但那四個量不是會計事實 ——
         <b>求償權是三代工具堆出來的結果</b>,而溢價能大於一是因為有人全職在維持它。
         這一節講公司在蓋什麼、為什麼非得這樣蓋,四節的符號才有意義。`)}

      ${symbolTable(["H", "S", "C", "p", "m"])}

      ${steps([
        {
          q: "目的:贏法只有一種",
          body: `
            <p>如果只是想要比特幣的曝險,買幣或買現貨 ETF 就好。
            <b>一家上市公司值得存在的理由,是它能做到比單純持有更好。</b></p>
            <p>而比特幣是<b>有限</b>的,所以「更好」只有一種定義:</p>
            ${eqCard(texBlock(String.raw`\text{每一股背後含有的比特幣要變多}`))}
            <div class="note key">
              這是整個資本結構的目的。<b>後面所有的工具、操作、指標,全部服務於這一件事。</b>
              任何一段推導如果指不回這裡,它就是細節,不是主線。
            </div>`,
          edge: `「每股含幣量」有兩種算法 —— 扣不扣求償權。
            這一節講的是<b>扣掉之後</b>那一種。兩者的差別是下一節的全部內容。`,
        },
        {
          q: "三代工具:風險一步步推給市場",
          body: `
            <p>公司自己沒有錢一直買幣,必須向資本市場要。
            而<b>用什麼名義要,決定了風險留在誰身上</b>。</p>
            <div class="lec-table"><table class="mini">
              <thead><tr><th>工具</th><th>風險在誰</th><th>代價</th></tr></thead>
              <tbody>
                <tr><td><b>抵押借錢</b></td><td><b>公司</b></td>
                    <td>幣價跌破線就被強制清算 —— 而那正是最不想賣幣的時候</td></tr>
                <tr><td><b>可轉換公司債</b></td><td>公司,但小得多</td>
                    <td>無擔保、到期日長,沒有保證金追繳;<b>發出去就不用再管</b></td></tr>
                <tr><td><b>永續優先股</b></td><td><b>市場</b></td>
                    <td>風險賣掉了,但換來一個新問題 —— 第四節</td></tr>
              </tbody>
            </table></div>
            <p style="margin-top:14px"><b>這條線的主題不是「成本越來越低」,
            是「風險越來越不在公司身上」。</b>
            跟銀行借錢風險很高<b>而且在自己身上</b>;用證券發售出去,<b>風險在市場</b>。
            前提是市場規模要夠大 —— 規模夠大才有議價權,有議價權才轉嫁得掉。</p>
            <div class="lec-table" style="margin-top:16px"><table class="mini">
              <caption style="caption-side:top;text-align:left;font-size:.82rem;color:var(--ink-3);padding-bottom:6px">
                公司自己把資產負債表分成三層。<b>那三層就是後面「資本操作」那一節的位置</b> ——
                每一筆操作都是在這幾個位置之間搬錢。</caption>
              <thead><tr><th>公司的說法</th><th>位置</th><th>它承接什麼</th><th>誰來買</th></tr></thead>
              <tbody>
                <tr><td><b>數位資本</b></td><td>${PLACE["H"]} ${tex("H")}</td>
                    <td>原始波動;不產生現金流</td><td>誰都可以</td></tr>
                <tr><td><b>數位股權</b></td><td>${PLACE["S"]} ${tex("S")}</td>
                    <td><b>放大</b>的波動;剩餘索償權</td><td>要槓桿的資金</td></tr>
                <tr><td><b>數位信貸</b></td><td>${PLACE["DL"]}</td>
                    <td>波動被剝掉;錨定約定面額</td><td>要固定收益、不能承受回撤的資金</td></tr>
                <tr><td>(沒有單獨命名)</td><td>${PLACE["U"]}</td>
                    <td>—— 見下</td><td>——</td></tr>
              </tbody>
            </table></div>
            <div class="note" style="margin-top:14px">
              <b>${tex("C")} 就是第三列的面額總和,再扣掉第四列。</b>
              公司手上的美元流動性可以直接抵掉一部分求償權 ——
              那筆錢本來就是準備拿去付利息與股息的。完整的式子在下一節。
              <div style="margin-top:10px">
                ⚠️ 第四列<b>不是第四種資本</b> —— 公司不拿它去賣任何東西。
                它是<b>管道</b>加上一個償債緩衝,所以後面的圖上用虛線畫。
              </div>
            </div>
            <div class="note" style="margin-top:14px">
              <b>兩代的賣法剛好相反。</b>
              可轉債是把波動<b>打包</b>賣給專門要波動的人(套利基金想買那個嵌入選擇權,
              所以票息可以壓到極低 —— <b>最優先的一層票息最低,不是因為信用好,
              是因為波動被貨幣化了</b>);
              優先股是把波動<b>剝掉</b>賣給不能承受回撤的資金。
              <div style="margin-top:10px">
                兩側合起來才完整:同一個波動,一邊打包、一邊剝離,
                <b>普通股拿到的是兩次切割之後剩下的全部</b>。
              </div>
            </div>`,
          edge: `可轉債那一側依賴<b>市場願意為波動付錢</b>。
            隱含波動率收斂時,近零票息的條件就不再成立 —— 那不是信用問題,是需求問題。`,
        },
        {
          q: "清償順位,以及三條改變結論的條款",
          body: `
            <p>三代工具堆起來就是一座階梯。${tex("C")} 把它壓縮成單一數值:</p>
            <div class="lec-table"><table class="mini">
              <thead><tr><th>順位</th><th>工具</th><th>股息的累積機制</th><th>轉換權</th></tr></thead>
              <tbody>${LADDER.map(([r, name, cum, conv]) =>
                `<tr><td class="n"><b>${r}</b></td><td>${name}</td>
                 <td>${cum}</td><td>${conv}</td></tr>`).join("")}</tbody>
            </table></div>
            <p style="font-size:.8rem;color:var(--ink-3);margin-top:8px">
              票息率與各層金額屬於數值解,在<a href="#/board/quantities">儀表板</a>。</p>

            <p style="margin-top:16px"><b>順位本身是常識。真正改變結論的是三條條款:</b></p>
            <p><b>一 · 股息水壩。</b>高階優先股的股息沒付足,公司在法律上<b>不得</b>
            向次級優先股發股息,更不得對普通股分紅或回購 ——
            這解釋了為什麼普通股回購在真實資料裡幾乎看不到。</p>

            <div class="note key" style="margin:16px 0">
              <b>二 · 沒有一層以比特幣設質。</b>
              各級持有人只對公司的<b>一般資產</b>享有優先受償權;底下那堆幣是信用背書,
              不是質押物。<b>所以第一代那個清算機制在這裡不存在</b> —— 沒有保證金追繳。
              <div style="margin-top:12px">
                後果是第四節那個交點要改讀法:
                ${eqCard(texBlock(String.raw`E(p_{0}) = 0 \quad\iff\quad p_{0} = \frac{C}{H}`))}
                <b>${tex("p_{0}")} 是帳面歸零點,不是清算觸發點。</b>
                跌破它只代表帳面殘值為負,公司照樣運作。
                真正會致命的是<b>付不出股息與利息</b> —— 那是流動性問題。
              </div>
            </div>

            <p><b>三 · 累積與非累積不是同一種負債。</b>多數層是累積型,欠的息會滾;
            最劣後那一層是非累積型 —— <b>那一期沒發就永久消失</b>。</p>`,
          edge: `我們的 ${tex("C")} 用清算優先權計價,<b>對第三條不敏感</b> ——
            面額一樣就算一樣。方向是<b>高估</b>非累積那一層的實質負擔,
            寫在<a href="#/provenance">出處</a>頁。`,
        },
        {
          q: "⚠️ 轉嫁出去,不等於不用管",
          body: `
            <p>可轉債發出去就不用再碰。<b>優先股不一樣 —— 優先股是市場機制,它需要被管理。</b></p>
            <p>風險確實轉移到市場身上了。但<b>風險產生的結果,還是會回到公司這邊</b>:</p>
            <div class="note key">
              優先股跌破面額,<b>跟公司的盈虧沒有關係</b> —— 公司照常付息,帳上一毛都不會少。
              <b>但公司要繼續買幣擴張,就得把它帶回面額。</b>
              <div style="margin-top:12px">
                所以優先股的市價相對面額是一道<b>閘門</b>:
                <b>開著</b>才能再發行、募到美元、買幣、加槓桿;<b>關著</b>就發不出去,
                就算發得出去條件也差到不值得做。
              </div>
              <div style="margin-top:12px">
                <b>風險是市場的,約束是公司的。</b>
                公司幫市場管理那個風險不是出於責任,<b>是因為它需要市場再借一次</b>。
              </div>
            </div>
            <p style="margin-top:14px">所以才有後面那些資本操作,而它們構成一個環:</p>
            <div class="lec-table"><pre style="font-size:.82rem;line-height:1.7;margin:0;color:var(--ink-2)">
優先股深度折價 ── 閘門關上
      │  折價回購 · 調高股息率 · 動用美元儲備 · 必要時賣幣
      ▼
價格拉回面額 ── 閘門打開
      │  重新發行 / ATM
      ▼
募到美元 → 買進比特幣 → 槓桿加大</pre></div>
            <div class="note" style="margin-top:14px">
              <b>⚠️ 折價回購不是為了賺那個價差。</b>
              折價買回面額確實是一筆帳面利得,但那個價差其實沒有到很多。
              <b>真正的優勢是它把閘門重新打開了</b> —— 公司因此可以重新發行、
              重新買幣、重新加槓桿。
              <div style="margin-top:10px">
                <b>只看當下損益,每一筆操作都會判錯。</b>
                這是後面三節全部要處理的事。
              </div>
            </div>`,
          edge: `維持閘門的手段有代價,而且彼此衝突:調高股息率會增加硬性現金義務;
            回購要花現金;賣幣減少持幣。<b>這些取捨在代數上看不出來</b> ——
            要看現金跑道撐多久,而那還沒進模型。`,
        },
        {
          q: "⚠️ 但槓桿加大,不等於每股含幣量上升",
          body: `
            <p>這是整條鏈最容易被跳過的一步,而它決定了後面要量什麼。</p>
            <p><b>單位不一樣:</b>求償權是<b>美元計價</b>的一筆固定金額;
            每股含幣量是<b>比特幣計價</b>的,幾顆幣。</p>
            ${eqCard(texBlock(String.raw`p \uparrow
              \;\Longrightarrow\; \underbrace{C/p}_{\text{求償權換算成幣}} \downarrow
              \;\Longrightarrow\; \underbrace{H - C/p}_{\text{普通股分到的幣}} \uparrow`),
              `而<b>普通股的股數並沒有新增發行</b> —— 公司發的是優先股。`)}
            <p>所以每股含幣量上升,靠的不是多買了多少幣,
            <b>是那筆美元債在幣計價下變小了</b>。</p>
            <div class="note key">
              <b>反過來說:發優先股買幣的當下,對每股含幣量其實是負的。</b>
              募到的錢通常低於掛上的面額,所以當下是扣分。
              <b>它的回報來自之後 —— 幣價上漲時求償權的縮水。</b>
            </div>
            ${eqCard(texBlock(String.raw`\text{槓桿加大} \;\neq\; \text{每股含幣量上升}
              \qquad \text{槓桿加大} \;=\; \text{對幣價的曝險被放大}`))}
            <p>公司的本事不在於加了多少槓桿,
            <b>在於把閘門維持打開,好一直下這個注</b>。</p>`,
          edge: `這也是為什麼<b>不能把幣價上漲算成公司的功勞</b> ——
            那一塊恰恰是這個結構最主要的回報來源,所以更要分開。
            拆法在<a href="#/lecture/time">績效歸因</a>。`,
        },
        {
          q: "這套做法的上界",
          body: `
            <p>下一節會推出溢價增發的判準:溢價大於一時增發必然增厚。
            那回答的是<b>方向</b>。接下來的問題是<b>幅度能到多少</b> —— 它有上界。</p>
            <p>增發 ${tex("X")} 比例的股數、募到的錢全部買幣,每股含幣量的成長率是:</p>
            ${eqCard(texBlock(String.raw`y \;=\; \frac{1 + Xm}{1 + X} - 1
              \;=\; \frac{X(m-1)}{1+X}`),
              `對 ${tex("X")} 單調遞增 —— 但 ${tex(String.raw`X \to \infty`)} 時會收斂。`)}
            ${eqCard(texBlock(String.raw`X = \frac{y}{\,m - 1 - y\,}
              \qquad\Longrightarrow\qquad \boxed{\,y < m - 1\,}`),
              `<b>年度成長率的硬上限就是 ${tex("m-1")}。</b>`)}
            <div class="note key">
              這不是「很難」,是<b>不可能</b>。而且兩件事同時發生:
              持幣變大 → 需要的增發比例上升 → <b>增發本身壓低市價、侵蝕 ${tex("m")}</b>
              → 上限跟著往下走。
              <b>增厚不只是逐輪變難,其上界本身也在下移。</b>
            </div>
            <p style="margin-top:14px">折價時上限是零 —— 不是「成長變慢」,
            是<b>任何正的目標都不可達</b>,股權管道在數學上關閉。
            <b>兩道閘門會同時關上</b>:信貸端折價發不出去,股權端折價發了也是稀釋。</p>`,
          check: `公式與情境模擬器的實作逐點對齊(兩個實作算同一件事就會各自漂移);
            反解 round-trip;<b>超過上限時回傳「不可達」而不是一個很大的數字</b>。`,
          edge: `這條界用的 ${tex("m")} 是本站的 ${tex("m")}(分母是殘值),
            不是一般講的 mNAV。推導從股價恆等式來,換一個 ${tex("m")} 就不成立。`,
        },
      ])}

      <div class="note" style="margin-top:30px">
        <b>接下來:</b>知道形狀之後再去量它。
        <a href="#/lecture/quantities">推導 · 每股計量</a>從公司公布的指標講起,
        一路定義到股價的恆等式。
      </div>
    </div>`;
};
