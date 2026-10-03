/** 儀表板 · 時間 —— L4 的數值解。
 *
 *  講義推導四層歸因為什麼沒有殘差;這一頁是那四層今天的數字。
 *  四層與各階段的口徑完全相同,所以用的是同一個 layers.ts。 */
import { chronicle, daily, meta, N } from "../../data";
import { boardHead, tile } from "../../components/board";
import { layerBars, layerStats, offsetNote, ownPct } from "../../components/layers";
import { pct } from "../../lib/format";
import type { PageFn } from "../../router";

/** 階段指標的 pct 可能是 null(那一段沒有可比的起點) */
const d = (v: number | null) => (v == null ? "—" : pct(v / 100));
const sats = (v: number) => (v >= 0 ? "+" : "") + Math.round(v).toLocaleString();

export const boardTimePage: PageFn = (root) => {
  const p = meta.program;
  const st = layerStats(p.layers4);
  const era = chronicle[chronicle.length - 1]!;
  const eraSt = layerStats(era.layers4);

  root.innerHTML = `
    <div class="wrap">
      ${boardHead("四 · 時間", "這段報酬是誰造成的",
        `${"講義推導出四層加總恰好等於總報酬、沒有殘差。"
        }這一頁是那四層的數字 —— 全期一組,當期一組。
         <b>只有「公司決策」那一層是公司控制得了的</b>,其餘三層都不是。`,
        "#/lecture/time", daily.date[N - 1]!)}

      <h2 style="margin-bottom:10px">全期 ${p.span[0]} → ${p.span[1]}</h2>
      <div class="grid3" style="margin-bottom:18px">
        ${tile("MSTR 報酬", pct(Math.exp(st.total) - 1),
          "四層相乘的結果")}
        ${tile("公司決策", pct(ownPct(p.layers4.decision) / 100),
          `佔變動量 ${(Math.abs(p.layers4.decision) / st.gross * 100).toFixed(0)}%`,
          { tone: "var(--equity)" })}
        ${tile("實得每股變化", sats(p.split.decision + p.split.market) + " sats",
          `決策 ${sats(p.split.decision)} · 行情 ${sats(p.split.market)}`)}
      </div>
      ${layerBars(p.layers4, st)}
      ${offsetNote(p.layers4, st)}

      <h2 style="margin:34px 0 10px">當期:${era.title}</h2>
      <p class="lede" style="margin-bottom:14px">
        ${era.start} → ${era.ongoing ? "進行中" : era.end} ·
        ${era.days} 天 · 主要手法 ${era.tools.length} 把。
        完整敘述在<a href="#/posts/chronicle">大事記</a>。
      </p>
      <div class="grid3" style="margin-bottom:18px">
        ${tile("持幣", d(era.metrics.held.pct), "")}
        ${tile("求償權", d(era.metrics.claims.pct), "",
          { tone: (era.metrics.claims.pct ?? 0) < 0 ? "var(--good)" : "var(--bad)" })}
        ${tile("實得每股", d(era.metrics.cebe.pct), "",
          { tone: (era.metrics.cebe.pct ?? 0) > 0 ? "var(--good)" : "var(--bad)" })}
        ${tile("決策 / 行情",
          `${sats(era.split.decision)} / ${sats(era.split.market)}`,
          "sats。逐日鏈結,決策用當下幣價評價")}
      </div>
      ${layerBars(era.layers4, eraSt)}

      <div class="note key" style="margin-top:22px">
        <b>佔比用的是「佔變動量」,不是淨額。</b>
        四層會互相抵銷 —— 某一層大幅為正、另一層大幅為負時,淨額接近零,
        用它當分母會吐出 158%、−100% 這種數字。
        分母改成四層絕對值的總和,每一層都落在 0 到 1 之間。
        <br><br>
        它回答的是「這段期間的力氣花在哪裡」,不是「淨結果怎麼來的」——
        要回答後者就直接看四層的數值,不要再除一次。
      </div>

      <div class="note" style="margin-top:24px">
        <b>講義與儀表板都走完了。</b>
        接下來是<b>詮釋</b> —— 這些數字該怎麼看,在
        <a href="#/posts/chronicle">大事記</a>與<a href="#/structure">資本結構</a>。
      </div>
    </div>`;
};
