/** 儀表板 · 配對 —— L3 的數值解。
 *
 *  講義講組合的代數;這一頁講「文件實際寫了哪幾筆配對、信心度多少」。
 *  配對是**推論**不是事實,所以信心度與文件原句都要看得見。 */
import { operations } from "../../data";
import { byId, combos } from "../../formulas";
import { boardHead, tile } from "../../components/board";
import { edgarUrl } from "../../lib/format";
import type { Operation } from "../../types";
import type { PageFn } from "../../router";

const RULE: Record<string, string> = {
  unpaired: "沒有配對 —— 文件沒寫用途,就不猜",
  stated_sale_use: "文件明寫用途,金額也對得上 → 合併成一個組合操作",
  partly_funded: "文件明寫用途,但只支應了一部分 → 兩邊維持獨立,說法掛在來源上",
};

function card(o: Operation): string {
  const f = byId[o.tool];
  return `
    <div class="pair-card">
      <div class="pair-head">
        <b>${f?.label ?? o.tool}</b>
        <span class="tool-path">${o.lo} → ${o.hi}</span>
        <span class="tool-tag ${o.conf >= 0.9 ? "good" : "warn"}">信心 ${o.conf}</span>
      </div>
      ${o.quote ? `<blockquote class="pair-quote">${o.quote}</blockquote>` : ""}
      <p class="pair-rule">${RULE[o.rule] ?? o.rule}</p>
      ${o.acc.length ? `<p class="pair-src">${o.acc.map((a) =>
        `<a class="src" href="${edgarUrl(a)}" target="_blank" rel="noopener">${a}</a>`
        ).join(" · ")}</p>` : ""}
    </div>`;
}

export const boardPairingPage: PageFn = (root) => {
  const paired = operations.filter((o) => o.rule !== "unpaired");
  const asCombo = operations.filter((o) => o.kind === "combo");
  const last = operations[operations.length - 1]?.hi ?? "";

  root.innerHTML = `
    <div class="wrap">
      ${boardHead("三 · 配對", "哪幾筆錢的去向是文件說的",
        `${"講義列出四個組合的代數。這一頁問的是另一件事:"
        }<b>真實資料裡,哪幾筆配得起來?</b>
         答案比預期少 —— 因為規則是「看文件寫的用途,不看金額相似度」。`,
        "#/lecture/pairing", last)}

      <div class="grid3" style="margin-bottom:26px">
        ${tile("有配對證據的", String(paired.length),
          `共 ${operations.length} 個操作`, { tone: "var(--equity)" })}
        ${tile("合併成組合的", String(asCombo.length),
          "金額差 < 5% 才合併,否則兩邊維持獨立")}
        ${tile("講義列的組合", String(combos.length),
          "代數上存在,不代表資料裡配得出來")}
      </div>

      <div class="note key" style="margin-bottom:26px">
        <b>為什麼這麼少。</b>現金是可替代的 —— 一週裡多個來源同時供給多個用途,
        金額對得上可能只是巧合。所以這一層的規則是
        <b>看文件寫的用途,不看金額相似度</b>:申報沒寫就不配,
        寧可少記一個關係,也不要生出一個不存在的。
        <br><br>
        另一個原因是<b>時間尺度</b>:同一組關係在週尺度可能對不上、
        在季尺度就收斂,因為中間隔了一個緩衝。窗口比可用粒度還短的時候,
        對帳不會錯 —— 它只是不成立。
      </div>

      <h2 style="margin-bottom:12px">配得起來的那些</h2>
      ${paired.length
        ? paired.slice().reverse().map(card).join("")
        : `<p class="note">目前沒有任何一筆有配對證據。</p>`}

      <h2 style="margin:32px 0 10px">講義列的四個組合,各自在資料裡出現幾次</h2>
      <div class="card flush"><div class="scroller"><table class="mini">
        <thead><tr><th>組合</th><th>路徑</th><th class="n">資料裡</th></tr></thead>
        <tbody>
          ${combos.map((c) => {
            const n = operations.filter((o) => o.tool === c.id).length;
            return `<tr><td>${c.label}</td>
              <td class="num" style="font-size:.78rem">${c.moves.join(" → ")}</td>
              <td class="n"${n ? "" : ' style="color:var(--ink-3)"'}>${n || "—"}</td>
            </tr>`;
          }).join("")}
        </tbody></table></div></div>
      <p style="font-size:.82rem;color:var(--ink-3);margin-top:10px">
        「—」不代表公司沒做過那件事,只代表<b>沒有文件明寫到可以配對的程度</b>。
        例如 ATM 募資去買幣每週都在發生,但 8-K 是在活動表的註腳寫資金來源,
        不是寫成一筆配對 —— 那一類目前記成兩個單一操作。
      </p>

      <div class="note" style="margin-top:28px">
        <b>接下來:</b>把這些操作放到時間軸上,看它們對股價的貢獻。
        <a href="#/board/time">儀表板 · 時間</a>
      </div>
    </div>`;
};
