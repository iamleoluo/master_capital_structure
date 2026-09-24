/** 資本結構工具箱 —— 同一份定義的兩種呈現。
 *
 *  表格版是常設解釋(公司能動用的槓桿有哪些、各自對實得每股含幣量的淨效果);
 *  徽章版給大事記的每一則用,標示該階段實際動用了哪幾把。
 *  兩者共用 meta.toolkit,所以不會出現清單對不上的情況。 */
import { meta } from "../data";

const CEBE_TONE: Record<string, string> = {
  "折價買回 = 加分": "good",
  "加分": "good",
  "稀釋": "bad",
  "看用途": "warn",
};

function tone(cebe: string): string {
  return CEBE_TONE[cebe] ?? "neutral";
}

/** 常設的工具箱表格。 */
export function toolkitTable(): string {
  return `
    <div class="table-wrap"><table class="toolkit">
      <thead><tr>
        <th>工具</th><th>求償權</th><th>股數</th><th>持幣</th>
        <th>對實得每股</th><th>說明</th>
      </tr></thead>
      <tbody>
        ${meta.toolkit.map((t) => `
          <tr>
            <td><b>${t.label}</b></td>
            <td class="mono">${t.claims}</td>
            <td class="mono">${t.shares}</td>
            <td class="mono">${t.btc}</td>
            <td><span class="tool-tag ${tone(t.cebe)}">${t.cebe}</span></td>
            <td class="tool-note">${t.note}</td>
          </tr>`).join("")}
      </tbody>
    </table></div>`;
}

/** 某個階段動用了哪些工具。active 是由資料判定的那一組。 */
export function toolBadges(tools: string[], active: string[]): string {
  const set = new Set(active);
  const all = [...new Set([...tools, ...active])];
  if (!all.length) return "";
  return `<div class="tool-badges">${all.map((id) => {
    const t = meta.toolkit.find((x) => x.id === id);
    if (!t) return "";
    // 資料上沒動作的,淡化顯示並註明 —— 不要讓人工標註蓋過事實
    const off = set.has(id) ? "" : " off";
    const title = set.has(id) ? t.note : `${t.note}(此期間資料上沒有動作)`;
    return `<span class="tool-badge ${tone(t.cebe)}${off}" title="${title}">${t.label}</span>`;
  }).join("")}</div>`;
}
