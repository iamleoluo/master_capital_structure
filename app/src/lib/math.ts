/** 數學式排版 —— 薄薄一層包在 KaTeX 外面。
 *
 *  全站的公式原始碼都是 LaTeX,收斂在「資本結構」頁(src/pages/structure.ts),
 *  其他頁需要時以超連結指回去,不重述。
 *
 *  KaTeX 的 CSS 與字型在 main.ts 一併載入(順序排在 app.css 之前,
 *  這樣站上的樣式永遠蓋得過它)。artifact 模式會把字型 base64 inline 進
 *  單一 HTML,所以 vite.config.ts 有一個 plugin 先把用不到的 woff/ttf 剃掉。 */
import katex from "katex";

/** throwOnError:TeX 打錯時直接炸掉,而不是在頁面上 render 一串紅字。
 *  strict:false —— \text{} 裡放中文會觸發 KaTeX 的 unicode 警告,但它本來就排得出來。 */
const OPTS = { throwOnError: true, strict: false as const };

/** 行內數學式,跟著本文一起排。 */
export function tex(src: string): string {
  return katex.renderToString(src, { ...OPTS, displayMode: false });
}

/** 獨立成行、置中的數學式。 */
export function texBlock(src: string): string {
  return katex.renderToString(src, { ...OPTS, displayMode: true });
}

/** 多行對齊的推導:每行用 & 標出對齊點(通常放在等號前),
 *  等號就會上下對齊成一直線。 */
export function texAlign(lines: string[]): string {
  return texBlock(`\\begin{aligned}${lines.join(" \\\\ ")}\\end{aligned}`);
}

/** 一個有底色的公式卡片:式子 + 底下的白話說明。 */
export function eqCard(math: string, note?: string): string {
  return `<div class="eq-card">${math}${
    note ? `<p class="eq-note">${note}</p>` : ""}</div>`;
}
