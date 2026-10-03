/** 講義 · 配對 —— L3 的公式解。
 *
 *  推導來源:reference/02-operations.md §4。
 *  注意這一層講的是**組合的公式**,不是實際配對出來的結果 ——
 *  後者是數值解,在儀表板。 */
import { combos, PLACE, type Formula } from "../../formulas";
import { lectureHead, steps } from "../../components/lecture";
import { eqCard, tex, texBlock } from "../../lib/math";
import type { PageFn } from "../../router";

const TONE: Record<string, string> = { "稀釋": "bad", "折價買回 = 加分": "good" };

function card(t: Formula): string {
  return `
    <div class="tool-eq">
      <div class="tool-eq-head">
        <b>${t.label}</b>
        <span class="tool-path">${t.moves.map((m) => PLACE[m]).join(" → ")}</span>
        <span class="tool-tag ${TONE[t.cebe] ?? "warn"}">${t.cebe}</span>
      </div>
      <div class="tool-eq-cols">
        <div class="tool-eq-col">
          <div class="tool-eq-lab">對帳面每股 <span>${tex("B")}</span></div>
          ${texBlock(t.bps)}
        </div>
        <div class="tool-eq-col key">
          <div class="tool-eq-lab">對實得每股 <span>${tex("E")}</span></div>
          ${texBlock(t.eq)}
        </div>
      </div>
      <p class="tool-note">${t.note}</p>
    </div>`;
}

export const lecturePairingPage: PageFn = (root) => {
  root.innerHTML = `
    <div class="wrap">
      ${lectureHead("三 · 配對", "錢要先從某處來,才能往某處去",
        `單一工具拆開看是為了把代數講乾淨,但公司幾乎不會只做一個動作。
         真實世界的操作是<b>兩條箭頭串起來</b> —— 而串起來的地方,
         每一次都是同一個位置。`)}

      ${steps([
        {
          q: "為什麼每個組合的中間都是美元流動性",
          body: `
            <p>四個組合的路徑:</p>
            <div class="lec-table"><table class="mini">
              <thead><tr><th>組合</th><th>路徑</th></tr></thead>
              <tbody>
                ${combos.map((c) => `<tr><td>${c.label}</td>
                  <td class="num">${c.moves.join(" → ")}</td></tr>`).join("")}
              </tbody></table></div>
            <p><b>中間那一點全部都是 ${tex("U")}。</b>這不是巧合 ——
            募資先變成現金,現金再去部署。</p>
            <div class="note key">
              而公司當週募資、當週部署,所以那筆過路現金在週頻揭露上幾乎看不見。
              <b>它被藏在操作裡面,但結構上一定存在</b> ——
              這也是為什麼「把募到的錢放進儲備」不需要另外當成一個動作:
              那就是融資工具本身在做的事。
            </div>`,
          check: `路徑由各步驟的位置串出來,不手寫,而且要求首尾相接 ——
            前一步的終點必須是後一步的起點,否則那兩步根本不是同一筆錢。`,
        },
        {
          q: "哪些看起來像組合、其實不是",
          body: `
            <div class="note" style="margin-bottom:14px">
              <b>「賣幣 → 增加美元儲備」不是組合,是單一工具。</b>
              ${tex("U")} 本來就是賣幣的終點,不需要第二步。
              早期版本把它列成組合,那是把<b>「錢停在哪裡」誤當成「又做了一個動作」</b>。
            </div>
            <p><b>「可轉債轉股」也不是組合。</b>債主行使轉換權,債消失、換成股票,
            <b>完全沒有現金移動</b> —— 它是唯一不經過 ${tex("U")} 的工具。</p>
            <p>要區分的是另一件事:<b>發新股募資去回購可轉債</b>。
            那才是組合(${tex("S \\to U \\to DL")}),中間有現金。
            兩者的結果看起來都是「債變少、股變多」,但一個是債主的決定、
            一個是公司的操作。</p>`,
        },
        {
          q: "配對能不能成立,看兩件事",
          body: `
            <ol class="lec-list">
              <li><b>證據的強弱。</b>最強的是文件明寫用途 ——
                申報直接寫「某筆賣幣所得用於回購某檔優先股」,那是事實不是推論。
                其次是<b>金額</b>:一個來源對一個用途而且金額吻合,
                或多個來源的<b>加總</b>等於用途 —— 後者不是「不知道是哪一個」,
                是<b>兩個都是</b>,加總對得上就證明了分配。
                <br><br>
                <b>文件寫不寫是揭露的編輯決定,錢怎麼流不會因為沒寫就不一樣。</b>
                所以金額算證據,只是比明寫弱一級。</li>
              <li><b>你看的時間尺度。</b>同一組關係在週尺度可能對不上、
                在季尺度就收斂 —— 因為中間隔了一個緩衝,而緩衝的餘額是整數揭露的。
                窗口比可用粒度還短的時候,對帳<b>不會錯,它只是不成立</b>。</li>
            </ol>
            <div class="note key">
              這兩條合起來是一條設計原則:<b>配對是推論,不是事實</b>。
              所以每一個配對都要帶信心度上去,而且介面要看得出來 ——
              寧可顯示「這兩筆可能是一組」,也不要悄悄把它算成事實。
              <br><br>
              真正配不起來的,是<b>加總也對不上</b>的時候。那個落差本身是資訊
              (錢進了儲備、或某個來源那時還沒逐週揭露),不該被硬湊掉。
            </div>`,
          edge: `文件沒寫用途時,這一層就<b>不配對</b>,兩邊各自記成單一操作。
            不配對不是失敗,猜錯才是。`,
        },
        {
          q: "為什麼組合的求償權欄不再有問號",
          body: `
            <p>單一工具裡,募資與償還會讓 ${tex("DL")} 與 ${tex("U")} 同方向移動,
            所以淨效果說不出來(見<a href="#/lecture/tools">上一頁</a>)。</p>
            <p>組合把兩步串起來之後,<b>中間的 ${tex("U")} 一正一負抵銷掉</b>,
            剩下的就是頭尾兩個位置的淨變化:</p>
            ${eqCard(texBlock(String.raw`\underbrace{S \to U}_{+S,\,+U}
              \;+\;\underbrace{U \to H}_{-U,\,+H}
              \;=\; \underbrace{S \to H}_{+S,\,+H}`),
              "ATM 增發買幣:股數增加、持幣增加,而美元流動性回到原點 —— 那就是「過路現金看不見」在代數上的樣子。")}
            <p>所以組合的效果是明確的,而且<b>恰好對應到真實申報會揭露的東西</b> ——
            公司報的是「這週賣了多少股、買了多少幣」,不是「現金餘額中途變成多少」。</p>`,
        },
      ])}

      <h2 style="margin:34px 0 8px">四個組合的代數</h2>
      <p class="lede" style="margin-bottom:18px">
        最後一個最重要:單純增發要 ${tex("m > 1")},
        但募到的錢拿去折價 ${tex("d")} 買回求償權,門檻就降到 ${tex("m > 1 - d")} ——
        <b>即使普通股本身在折價交易,增發去買回優先股仍然加分</b>。
        折價越深,這把工具的適用區間越寬。
      </p>
      <div class="tool-algebra">${combos.map(card).join("")}</div>

      <div class="note" style="margin-top:30px">
        <b>接下來:</b>以上都是「做了這個動作會怎樣」。
        <a href="#/lecture/time">講義 · 時間</a>加入時間序,
        回答「觀察到的這段歷史裡,哪些是公司做的、哪些是行情」。
      </div>
    </div>`;
};
