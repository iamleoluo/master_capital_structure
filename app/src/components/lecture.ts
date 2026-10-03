/** 講義的共用版型。
 *
 *  每一節的結構固定:**問題 → 推導 → 驗證 → 邊界**(見 reference/10 §2.2)。
 *  固定下來有兩個作用:讀者知道往下看會看到什麼;
 *  而「邊界」那一格強迫每一節都回答「這一層算不準的地方在哪」——
 *  講義涵蓋得了的東西會隨不確定性增加而變少,那件事要寫在講義裡面。 */
import { texBlock } from "../lib/math";

export interface Step {
  /** 這一節要回答的問題 */
  q: string;
  /** 推導的本文(HTML)。公式用 texBlock / eqCard */
  body: string;
  /** 怎麼確認這條沒寫錯。驗證跑在建置期,讀者不必看到數字 */
  check?: string;
  /** 這一層算不準的地方 */
  edge?: string;
}

export function lectureHead(eyebrow: string, title: string, lede: string): string {
  return `
    <div class="page-head">
      <p class="eyebrow">講義 · ${eyebrow}</p>
      <h1>${title}</h1>
      <p class="lede">${lede}</p>
    </div>
    <div class="note" style="margin-bottom:28px">
      <b>這一頁不帶任何數字。</b>講義解的是<b>公式解</b> ——
      同一套 L1–L4 代進真實參數之後就是數值解,今天的讀數在
      <a href="#/">總覽</a>與其他頁。兩邊是同一個結構,解兩次。
    </div>`;
}

export function steps(list: Step[]): string {
  return list.map((s, i) => `
    <section class="lec-step">
      <h2><span class="lec-n">${i + 1}</span>${s.q}</h2>
      <div class="lec-body">${s.body}</div>
      ${s.check ? `<p class="lec-check"><b>怎麼驗</b> ${s.check}</p>` : ""}
      ${s.edge ? `<p class="lec-edge"><b>邊界</b> ${s.edge}</p>` : ""}
    </section>`).join("");
}

/** 一條編號的恆等式,置中排版 */
export const identity = (src: string): string => texBlock(src);
