/** 儀表板 · 量 —— L1 的數值解。
 *
 *  講義說「只需要四個量」,這一頁說「今天這四個量各是多少、從哪來」。 */
import { daily, meta, N } from "../../data";
import { boardHead, staleness, tile } from "../../components/board";
import { explorer } from "../../components/explorer";
import { bn, btc as fmtBtc, pct, usd0 } from "../../lib/format";
import type { PageFn } from "../../router";

export const boardQuantitiesPage: PageFn = (root) => {
  const i = N - 1;
  const claims = daily.debt[i]! + daily.pref_total[i]! - daily.cash[i]!;
  const perShare = (daily.common_btc[i]! / (daily.shares[i]! * 1e6)) * 1e8;
  const prov = meta.prov;

  root.innerHTML = `
    <div class="wrap">
      ${boardHead("一 · 量", "今天這四個數字", 
        `${"講義說只需要四個量就能決定全部。這一頁是那四個量今天的值,"
        }以及每一個是<b>申報當日的硬資料</b>還是插值出來的。`,
        "#/lecture/quantities", daily.date[i]!)}

      <div class="grid3" style="margin-bottom:12px">
        ${tile("總持幣 H", fmtBtc(daily.held[i]!), "顆 BTC",
          { src: staleness(daily.stale[i]!) })}
        ${tile("求償權 C", bn(claims), 
          `可轉債 ${bn(daily.debt[i]!)} + 優先股 ${bn(daily.pref_total[i]!)}
           − 美元流動性 ${bn(daily.cash[i]!)}`)}
        ${tile("在外股數 S", (daily.shares[i]!).toFixed(1) + "M", "basic 股數,不含假設轉股")}
        ${tile("比特幣價格 p", usd0(daily.btc[i]!), "Binance 日線收盤")}
      </div>

      <div class="grid3" style="margin-bottom:26px">
        ${tile("帳面每股 B", Math.round(daily.bps[i]!).toLocaleString(),
          "sats。總持幣 ÷ 股數,看不到求償權")}
        ${tile("實得每股 E", Math.round(perShare).toLocaleString(),
          `sats。扣掉求償權之後,求償權吃掉 ${pct(1 - perShare / daily.bps[i]!)}`,
          { tone: "var(--equity)" })}
        ${tile("市場溢價 m", daily.mnav_cebe[i]!.toFixed(3) + "x",
          `CEBE mNAV。一般口徑的 mNAV 是 ${daily.mnav_basic[i]!.toFixed(3)}x`,
          { tone: "var(--senti)" })}
        ${tile("槓桿 A", daily.amp[i]!.toFixed(2) + "x",
          "幣價變動 1% 時每股殘值變動幾 %")}
      </div>

      <div class="chart-block">
        <div class="chart-head"><div class="chart-label">拖曳任一張圖看任何一天</div></div>
      </div>
      <div id="board-explorer"></div>

      <h2 style="margin:34px 0 10px">這些數字能信到什麼程度</h2>
      <p class="lede" style="margin-bottom:14px">
        四個量的血統不一樣。持幣與美元流動性是 8-K 逐週揭露的<b>實測值</b>;
        可轉債、現金、股數來自季度 XBRL,中間是<b>線性插值</b>。
        所以求償權 C 的日內變化有一部分是插出來的 —— 錨點附近最可信,錨點中間最弱。
      </p>
      <div class="card flush" style="margin-bottom:12px"><div class="scroller"><table class="mini">
        <thead><tr><th>來源</th><th>份數</th><th>期間</th></tr></thead>
        <tbody>
          ${prov.docs.slice(0, 4).map((d) => `<tr>
            <td>${d.src.replace("sec_", "").toUpperCase()}</td>
            <td>${d.n}</td><td>${d.lo} → ${d.hi}</td></tr>`).join("")}
        </tbody></table></div></div>
      <p style="font-size:.82rem;color:var(--ink-3)">
        共 ${prov.doc_total} 份申報內容定址歸檔,由它們推出
        ${prov.event_total.toLocaleString()} 個事件。完整清單與稽核軌跡在
        <a href="#/data-quality">資料品質</a>。
      </p>

      <div class="note" style="margin-top:28px">
        <b>接下來:</b>這四個量怎麼變成現在這樣的?
        <a href="#/board/tools">儀表板 · 工具</a>列出公司實際用過的每一個動作。
      </div>
    </div>`;

  const el = root.querySelector<HTMLElement>("#board-explorer")!;
  return explorer(el);
};
