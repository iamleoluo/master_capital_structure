/** 儀表板的共用版型 —— 講義的對照物。
 *
 *  四個子分頁與講義**同名同序**,那是「同一個 L1–L4 解兩次」最直接的呈現:
 *  在講義看到式子,切到這裡同一個分頁就看到今天的數字。
 *
 *  這裡**不重述公式**(那是講義的事),也**不下判斷**(那是觀點的事)——
 *  數據本身是中性的。可以顯示代數直接推出的結果(「在這個 m 之下這筆增發
 *  對既有股東加分」),因為那是講義的公式套用;不能顯示「這是好決策」。 */

export function boardHead(eyebrow: string, title: string, lede: string,
                          lectureHref: string, asOf: string): string {
  return `
    <div class="page-head">
      <p class="eyebrow">儀表板 · ${eyebrow}</p>
      <h1>${title}</h1>
      <p class="lede">${lede}</p>
    </div>
    <div class="note" style="margin-bottom:26px">
      <b>資料至 ${asOf}。</b>這一頁是<b>數值解</b> ——
      式子為什麼長那樣、判準怎麼來的,在<a href="${lectureHref}">對應的講義</a>。
      兩邊是同一個結構,解兩次。
    </div>`;
}

/** 一個數字磚。`src` 是出處註記 —— 數值解的每個數字都要說得出它從哪來。 */
export function tile(k: string, v: string, d: string, opt: {
  tone?: string; src?: string;
} = {}): string {
  return `
    <div class="tile"${opt.tone ? ` style="border-left:3px solid ${opt.tone}"` : ""}>
      <div class="k">${k}</div>
      <div class="v"${opt.tone ? ` style="color:${opt.tone}"` : ""}>${v}</div>
      <div class="d">${d}</div>
      ${opt.src ? `<div class="tile-src">${opt.src}</div>` : ""}
    </div>`;
}

/** 這個數字離最近一次真實申報幾天 —— 插值距離。 */
export function staleness(days: number): string {
  if (days <= 3) return `<span class="fresh">申報當日</span>`;
  if (days <= 15) return `<span class="fresh">距申報 ${days} 天</span>`;
  return `<span class="stale">距申報 ${days} 天,插值</span>`;
}
