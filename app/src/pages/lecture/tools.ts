/** 推導 · 資本操作 —— L2 的公式解。
 *
 *  推導來源:reference/03-operations.md §1–3。
 *  主軸是四個位置:因為位置只有四個,動作就是可窮舉的。 */
import { atoms, PLACE, type Formula } from "../../formulas";
import { lectureHead, steps } from "../../components/lecture";
import { placeMap } from "../../components/placeMap";
import { symbolTable } from "../../components/symbols";
import { eqCard, tex, texAlign, texBlock } from "../../lib/math";
import type { PageFn } from "../../router";

const TONE: Record<string, string> = {
  "中性": "neutral", "稀釋": "bad", "減分": "bad",
  "加分": "good", "折價買回 = 加分": "good",
};
const tone = (v: string) => TONE[v] ?? "warn";

/** 一把工具的卡片:箭頭 + 兩欄代數 + 判準。 */
function card(t: Formula): string {
  const [a, b] = [t.moves[0]!, t.moves[t.moves.length - 1]!];
  return `
    <div class="tool-eq">
      <div class="tool-eq-head">
        <b>${t.label}</b>
        <span class="tool-path">${PLACE[a]} <span class="arr">→</span> ${PLACE[b]}</span>
        <span class="tool-tag ${tone(t.cebe)}">${t.cebe}</span>
      </div>
      <div class="tool-eq-cols">
        <div class="tool-eq-col">
          <div class="tool-eq-lab">對帳面每股 <span>${tex("B = H/S")}</span></div>
          ${texBlock(t.bps)}
        </div>
        <div class="tool-eq-col key">
          <div class="tool-eq-lab">對實得每股 <span>${tex("E = (H - C/p)/S")}</span></div>
          ${texBlock(t.eq)}
        </div>
      </div>
      <p class="tool-note">${t.note}</p>
    </div>`;
}

export const lectureToolsPage: PageFn = (root) => {
  root.innerHTML = `
    <div class="wrap">
      ${lectureHead("二 · 資本操作", "每一種操作,對兩把尺各自做了什麼",
        `<b>公司的說法</b>是「動態再平衡的雙向資本工具箱」—— 溢價時發行、折價時回購。
         <b>那個說法說得出用了哪一把,說不出對股東是加分還減分。</b>
         這一節補上那一段:把每一把工具的效果寫成代數,
         而且每一把都問兩次 —— 對帳面每股怎麼樣?對實得每股怎麼樣?`)}

      ${placeMap()}

      ${steps([
        {
          q: "工具清單為什麼是封閉的",
          body: `
            <p>一般談「公司可以做什麼」會列成一張沒有盡頭的清單。這裡不是 ——
            <b>資本只會在四個位置之間移動,而位置只有四個,所以箭頭就是可窮舉的。</b>
            這不是「我們想到這幾個」,是結構上就只有這幾條。</p>
            <div class="note key">
              <b>${tex("U")} 在圖的正中央,但它不是第四種資本。</b>
              公司的三層定位(數位資本 / 數位股權 / 數位信貸)對應的是
              ${tex("H")} / ${tex("S")} / ${tex("DL")} —— ${tex("U")} 不在裡面,
              因為公司不拿它去賣任何東西。
              <div style="margin-top:12px">
                它畫在中間,<b>正是因為它最不值得停留</b>:除了可轉債轉股,
                每一條箭頭都經過它,所以它是<b>管道</b>,不是目的地。
                圖上用虛線畫就是這個意思。
              </div>
              <div style="margin-top:12px">
                而且 ${tex("U")} 其實是兩種東西:一塊是董事會指定、
                <b>只能付股息與利息</b>的償付準備(一個被刻意建起來的水位);
                另一塊是募資到部署之間的<b>過路現金</b>(一個流量的殘影,
                在配對得上的操作裡只存在於當週)。
                代數上兩塊都算進 ${tex("C")},但敘事上它們都不該排在第一排。
              </div>
            </div>
            <p style="margin-top:14px">下一節會看到,<b>配對存在的理由有一半就是讓
            ${tex("U")} 不必被討論</b> —— 把來源與用途配成一組,它在中間抵銷掉。</p>`,
          edge: `四個位置的用途是<b>窮舉動作</b>,不是計算效果。
            下面第四節會看到它說不出淨效果的地方。`,
        },
        {
          q: "每一把工具的雙重判準",
          body: `
            <p>一把工具不是只有一個答案,是兩個 ——
            因為上一節的兩種口徑各自給出一把尺,而<b>同一個動作在兩把尺上常常相反</b>。</p>
            ${eqCard(texBlock(String.raw`B = \frac{H}{S}\times 10^{8}
              \qquad\qquad E = \frac{H - C/p}{S}\times 10^{8}`))}
            <p>${tex("B")} 的式子裡沒有 ${tex("C")},所以<b>任何只動到求償權的操作,
            在 ${tex("B")} 上恆等於零</b>。${tex("E")} 看得見求償權,代價是也看得見幣價。</p>
            <p><b>兩欄常常相反。</b>發優先股買幣讓 ${tex("B")} 上升而 ${tex("E")} 下降 ——
            那個相反就是 phantom growth 在代數上的樣子。
            而公司的 KPI 用的是 ${tex("B")}。</p>`,
        },
        {
          q: "兩類轉移:替換與伸縮",
          body: `
            <p>${PLACE["H"]} 與 ${PLACE["U"]} 是<b>資產</b>,${PLACE["DL"]} 與
            ${PLACE["S"]} 是<b>資金來源</b>。所以同一個箭頭符號在兩種情況下意思不同:</p>
            <div class="lec-table"><table class="mini">
              <thead><tr><th>類型</th><th>規則</th><th>哪幾條</th></tr></thead>
              <tbody>
                <tr><td><b>替換</b>(同類之間)</td>
                    <td>起點減、終點增,<b>資產負債表規模不變</b></td>
                    <td>買幣、賣幣、可轉債轉股</td></tr>
                <tr><td><b>伸縮</b>(跨類)</td>
                    <td>從來源出發 = 募資(兩端都增);指向來源 = 償還(兩端都減)</td>
                    <td>發行、ATM、回購、庫藏、股息</td></tr>
              </tbody></table></div>
            <p><b>九條裡只有三條不改變規模</b>,而且它們都不經過募資市場。</p>`,
          check: `位置是<b>宣告</b>,狀態轉移函數才是真實語意 ——
            所以測試拿轉移函數去反推方向,打臉那個宣告。
            曾經為了讓規則成立而把「可轉債轉股」寫成「發新股去消滅求償權」,
            那是兩回事:轉股沒有現金那一步。<b>為了救規則去改模型是本末倒置。</b>`,
        },
        {
          q: "推導示例:普通股 ATM 增發",
          body: `
            <p>底下那些判準不是背出來的,是推出來的。這一個最繞,
            推完之後其餘八把就好讀了。</p>
            ${eqCard(texAlign([
              String.raw`\frac{\,H - (C - nP)/p\,}{S + n} &> \frac{\,H - C/p\,}{S}`,
              String.raw`\iff\quad \frac{P}{p}\times 10^{8} &> E`,
              String.raw`\iff\quad m &> 1`,
            ]), `以每股 ${tex("P")} 發出 ${tex("n")} 股、募到的 ${tex("nP")} 全部拿去抵求償權,
              「增發後的每股含幣量要比增發前高」就是第一行。三行等價:
              第二行是<b>發行價換算成幣,要比當下的實得每股多</b>;
              把股價恆等式代進去就化簡成第三行 ——
              <b>增發是否增值,完全等於 ${tex("m")} 是否大於 1</b>,
              跟募到多少、發了幾股都無關。`)}
            <p>可轉債轉股是同一個條件,只是把 ${tex("P")} 換成轉換價。</p>`,
          edge: `這個推導有一個前提:${tex("E > 0")}。
            求償權大到把普通股吃光時不等式會反向 —— 那時候增發的判準整個不同,
            而那正是這個模型最不該被外推的地方。`,
        },
        {
          q: "四位置模型的能力邊界",
          body: `
            <p>募資與償還會讓 ${tex("DL")} 與 ${tex("U")} <b>同方向</b>移動 ——
            發優先股募到 ${tex("c")}、同時掛上面額 ${tex("F")}:</p>
            ${eqCard(texBlock(String.raw`\Delta C = F - c`),
              "是升是降取決於面額與價金的大小,不是方向問題。")}
            <p><b>四位置模型說得出錢往哪裡走,說不出淨效果。</b>
            硬填一個箭頭等於假裝模型知道它不知道的事,所以那一欄顯示問號,
            把答案交給右邊的代數與判準。</p>
            <p>組合反而明確 —— 因為 ${tex("U")} 在中間抵銷掉了(見
            <a href="#/lecture/pairing">推導 · 來源與用途</a>)。</p>`,
          edge: `這是四位置模型的真實邊界,不是瑕疵。
            它的用途是<b>窮舉動作</b>,不是計算效果。`,
        },
        {
          q: "為什麼反饋律不列入工具",
          body: `
            <p>九把工具<b>全部是離散事件</b>:某一天發了多少股、買了多少幣、付了多少股息。
            動作有時間點、有大小。</p>
            <p>但公司身上還有一類東西不長這樣 —— <b>反饋律</b>。
            浮動利率優先股的股息率就是:董事會按期依市價與約定面額的偏差校準下一期的利率
            (見<a href="#/lecture/structure">〇 · 資本架構</a>的閉環控制器)。
            它持續運轉、沒有「發生」的那一刻。</p>
            <div class="note key">
              <b>它不列入工具清單。</b>它決定的是「股息與債息」那把工具<b>每一期的大小</b>,
              本身不搬動任何位置。
              <div style="margin-top:12px">
                ${tex("\\Delta B")} 與 ${tex("\\Delta E")} 都是零 ——
                調整利率這個動作本身不移動幣、不移動股數、不移動求償權。
                移動發生在<b>下一次付息</b>,而那已經是另一把工具了。
              </div>
            </div>
            <p style="margin-top:14px">把它算成工具會有一個具體的壞處:
            <b>對帳時同一筆現金會被算兩次</b> ——
            一次記成「調息」,一次記成「付息」。</p>
            <div class="note">
              <b>所以工具的定義要收緊:工具是搬動位置的動作,不是決定動作大小的規則。</b>
              這條界線讓清單可以是封閉的 —— 位置只有四個,
              <b>搬動位置的動作才列得完</b>;決定大小的規則列不完。
            </div>`,
          edge: `反饋律本身不在這一層,但它的<b>參數</b>會進來:
            利率調高之後,下一期「股息與債息」那把工具的 ${tex("c")} 就變大。
            所以模型看得見它的後果,看不見它的決策過程。`,
        },
      ])}

      <h2 style="margin:34px 0 8px">九把工具的代數</h2>
      <p class="lede" style="margin-bottom:18px">
        符號沿用<a href="#/lecture/quantities">上一頁</a>,再加上描述單筆動作大小的五個量。
        <b>這五個都是「量」,方向由式子裡的正負號承擔</b> ——
        ${tex("F")} 就是面額,發行是掛上它、回購是消滅它,不需要兩個符號。
      </p>
      ${symbolTable(["c", "F", "n", "x", "d"])}

      <div class="tool-algebra" style="margin-top:22px">
        ${atoms.map(card).join("")}
      </div>

      <div class="note" style="margin-top:30px">
        <b>接下來:</b>公司幾乎不會只做一個動作 —— 錢要先從某處來,才能往某處去。
        <a href="#/lecture/pairing">推導 · 來源與用途</a>把兩條箭頭串起來,
        而那正是真實世界的樣子。
      </div>
    </div>`;
};
