/** 一篇觀點的內文。
 *
 *  **凍結的標日期,活的不要手寫。** 文章引用的數字是寫作當下的快照
 *  (存在 pins 裡,永遠不改),現況由資料層給 —— 兩者並排。
 *  這樣你能看到一個觀點寫下時的世界,以及它後來變成什麼。 */
import { chronicle, posts } from "../../data";
import { eraChartSlot, eraSkeleton, mountEraChart } from "../../components/era";
import { layerBars, layerStats } from "../../components/layers";
import { toolBadges } from "../../components/toolkit";
import type { Post } from "../../types";
import type { PageFn } from "../../router";

const KIND_LABEL = { chronicle: "大事記", structure: "資本結構" } as const;

/** 百分比保留一位小數 —— 小數值捨成整數會讓「+1.1%」變成「+1%」,
 *  而那一位正是重點(優先股堆疊那一段的實得每股幾乎持平)。 */
const fmt = (v: number, unit: string) =>
  unit === "%"
    ? (v >= 0 ? "+" : "") + v.toFixed(1) + "%"
    : (v >= 0 ? "+" : "") + Math.round(v).toLocaleString()
      + (unit ? " " + unit : "");

/** 寫的時候 vs 現在。沒有解析器認得的 key 就只顯示當時的值 —— 不假裝有對照。 */
function pins(p: Post): string {
  if (!p.pins.length) return "";
  return `
    <div class="pins">
      <div class="pins-head">寫於 ${p.date} 的數字,與今天的對照</div>
      <table class="mini">
        <thead><tr><th></th><th class="n">寫的時候</th><th class="n">今天</th></tr></thead>
        <tbody>
          ${p.pins.map((x) => {
            const moved = x.now != null && Math.abs(x.now - x.then) > 0.5;
            return `<tr>
              <td>${x.label}</td>
              <td class="n">${fmt(x.then, x.unit)}</td>
              <td class="n"${moved ? ' style="color:var(--equity)"' : ""}>${
                x.now == null ? "—" : fmt(x.now, x.unit)}</td>
            </tr>`;
          }).join("")}
        </tbody>
      </table>
      <p class="pins-note">
        左欄永遠不會變 —— 那是這個觀點寫下時的世界。
        右欄每週更新。兩欄開始分岔的時候,那本身就是資訊。
      </p>
    </div>`;
}

export function postDetail(slug: string): PageFn {
  return (root) => {
    const p = posts.find((x) => x.slug === slug);
    const era = p?.era ? chronicle.find((e) => e.id === p.era) : undefined;
    if (!p) {
      root.innerHTML = `<div class="wrap"><p class="note">找不到這一篇。</p></div>`;
      return;
    }
    root.innerHTML = `
      <div class="wrap post">
        <div class="page-head">
          <p class="eyebrow">
            <a href="#/posts/${p.kind}">觀點 · ${KIND_LABEL[p.kind]}</a>
          </p>
          <h1>${p.title}</h1>
          <div class="post-meta">
            <time>${p.date}</time>
            ${p.author ? `<span class="post-author">${p.author}</span>` : ""}
            ${p.tags.map((t) => `<span class="post-tag">${t}</span>`).join("")}
          </div>
        </div>
        ${p.claim ? `<div class="note key post-claim-box">
          <b>主張</b>${p.claim}
          <p style="margin:8px 0 0;font-size:.82rem;color:var(--ink-3)">
            主張可以被後續的資料檢驗 —— 這是資本結構那一類與大事記的差別。</p>
        </div>` : ""}
        ${pins(p)}
        <article class="post-body">${p.html}</article>
        ${era ? `
          <h2 style="margin:36px 0 12px">這一段的數字</h2>
          <p class="lede" style="margin-bottom:14px">
            以下全部由管線算,不在上面那段文字裡 ——
            <b>所以它們不會隨文章一起過期</b>。
          </p>
          ${toolBadges(era.tools, era.toolsActive)}
          ${eraChartSlot(era)}
          ${eraSkeleton(era)}
          <h3 style="margin:28px 0 10px">四層歸因</h3>
          ${layerBars(era.layers4, layerStats(era.layers4))}` : ""}
      </div>`;

    return era ? (mountEraChart(root, era) ?? undefined) : undefined;
  };
}
