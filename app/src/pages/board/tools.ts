/** 儀表板 · 工具 —— L2 的數值解。
 *
 *  講義列出公司能做的九個動作;這一頁列出它**實際做過**的每一筆,
 *  以及每一筆對兩把尺的效果。效果由 Python 的 toolbox 算,前端只排版。 */
import { operations } from "../../data";
import { byId } from "../../formulas";
import { boardHead, tile } from "../../components/board";
import { edgarUrl } from "../../lib/format";
import type { Operation } from "../../types";
import type { PageFn } from "../../router";

const money = (v: number | null) =>
  v == null ? "—" : "$" + (Math.abs(v) / 1e6).toLocaleString(undefined,
    { maximumFractionDigits: 0 }) + "M";
const sats = (v: number | null) =>
  v == null ? "—" : (v >= 0 ? "+" : "") + Math.round(v).toLocaleString();

const VERDICT: Record<string, [string, string]> = {
  true: ["加分", "good"], false: ["減分", "bad"],
};
const verdict = (o: Operation) =>
  o.accretive == null
    ? `<span class="tool-tag neutral">結構中性</span>`
    : `<span class="tool-tag ${VERDICT[String(o.accretive)]![1]}">${
        VERDICT[String(o.accretive)]![0]}</span>`;

function row(o: Operation): string {
  const f = byId[o.tool];
  const wk = o.acc.length
    ? `<a class="src" href="${edgarUrl(o.acc[0]!)}" target="_blank"
         rel="noopener" title="EDGAR ${o.acc[0]}">${o.hi}</a>`
    : o.hi;
  return `<tr>
    <td class="num">${wk}</td>
    <td>${f?.label ?? o.tool}</td>
    <td class="n">${money(o.usd)}</td>
    <td class="n" style="color:${(o.dB ?? 0) < 0 ? "var(--bad)" : "var(--ink-2)"}">${sats(o.dB)}</td>
    <td class="n" style="color:${(o.dE ?? 0) > 0 ? "var(--good)" : (o.dE ?? 0) < 0 ? "var(--bad)" : "var(--ink-3)"}">${sats(o.dE)}</td>
    <td>${verdict(o)}</td>
  </tr>`;
}

export const boardToolsPage: PageFn = (root) => {
  const atoms = operations.filter((o) => o.kind === "atom");
  const recent = operations.slice().reverse().slice(0, 40);
  const byTool = new Map<string, Operation[]>();
  for (const o of operations) {
    byTool.set(o.tool, [...(byTool.get(o.tool) ?? []), o]);
  }
  const span = [operations[0]?.hi, operations[operations.length - 1]?.hi];

  root.innerHTML = `
    <div class="wrap">
      ${boardHead("二 · 工具", "它實際用過哪幾把",
        `${"講義列出公司<b>能做</b>的九個動作。這一頁是它<b>做過</b>的每一筆 ——"
        }以及每一筆對帳面每股與實得每股的效果。
         效果由同一套代數算出來,不是另外估的。`,
        "#/lecture/tools", span[1] ?? "")}

      <div class="grid3" style="margin-bottom:24px">
        ${tile("具名操作", operations.length.toLocaleString(), 
          `${span[0]} → ${span[1]}`)}
        ${tile("用過幾把工具", String(byTool.size),
          `講義列了 ${Object.keys(byId).length} 把(含組合)`)}
        ${tile("最常用的", byId[[...byTool.entries()]
          .sort((a, b) => b[1].length - a[1].length)[0]![0]]?.label ?? "—",
          `${[...byTool.values()].sort((a, b) => b.length - a.length)[0]!.length} 筆`)}
        ${tile("單一動作 / 組合",
          `${atoms.length} / ${operations.length - atoms.length}`,
          "組合要有文件明寫用途才算得上")}
      </div>

      <h2 style="margin-bottom:10px">各把工具用了多少</h2>
      <div class="card flush" style="margin-bottom:28px"><div class="scroller"><table class="mini">
        <thead><tr><th>工具</th><th class="n">筆數</th><th class="n">累計金額</th>
          <th>判準</th></tr></thead>
        <tbody>
          ${[...byTool.entries()].sort((a, b) => b[1].length - a[1].length)
            .map(([id, list]) => {
              const f = byId[id];
              const tot = list.reduce((s, o) => s + Math.abs(o.usd ?? 0), 0);
              return `<tr><td>${f?.label ?? id}</td>
                <td class="n">${list.length}</td>
                <td class="n">${money(tot)}</td>
                <td style="font-size:.8rem;color:var(--ink-3)">${f?.cebe ?? ""}</td></tr>`;
            }).join("")}
        </tbody></table></div></div>

      <h2 style="margin-bottom:10px">最近 ${recent.length} 筆</h2>
      <p class="lede" style="margin-bottom:12px">
        ΔB 是對帳面每股的效果,ΔE 是對實得每股 —— 單位都是 sats。
        <b>兩欄常常相反</b>,那個相反就是講義在講的事。
        週次可以點,連回那份 8-K。
      </p>
      <div class="card flush"><div class="scroller tall"><table class="mini">
        <thead><tr><th>週</th><th>工具</th><th class="n">金額</th>
          <th class="n">ΔB</th><th class="n">ΔE</th><th>判準</th></tr></thead>
        <tbody>${recent.map(row).join("")}</tbody>
      </table></div></div>

      <div class="note" style="margin-top:28px">
        <b>接下來:</b>公司幾乎不會只做一個動作。
        <a href="#/board/pairing">儀表板 · 配對</a>列出文件明寫「這筆錢拿去做那件事」的那些。
      </div>
    </div>`;
};
