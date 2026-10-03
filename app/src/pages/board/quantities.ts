/** 儀表板 · 每股計量 —— L1 的數值解。
 *
 *  推導說「只需要四個量」,這一頁說「今天這四個量各是多少、從哪來」。 */
import { daily, meta, N } from "../../data";
import { accumulationStats, accumulationTable, drawAccumulation }
  from "../../charts/accumulation";
import { boardHead, staleness, tile } from "../../components/board";
import { explorer } from "../../components/explorer";
import { zoomable } from "../../lib/zoomable";
import { bn, btc as fmtBtc, pct, usd0 } from "../../lib/format";
import type { PageFn } from "../../router";

export const boardQuantitiesPage: PageFn = (root) => {
  const i = N - 1;
  const claims = daily.debt[i]! + daily.pref_total[i]! - daily.cash[i]!;
  const perShare = (daily.common_btc[i]! / (daily.shares[i]! * 1e6)) * 1e8;
  const prov = meta.prov;
  const st = accumulationStats();

  // 插值距離 —— 這個數字是申報當日的硬資料,還是插出來的猜測
  const buckets = { live: 0, near: 0, far: 0 };
  for (const d of daily.stale) {
    if (d <= 15) buckets.live++;
    else if (d <= 90) buckets.near++;
    else buckets.far++;
  }

  root.innerHTML = `
    <div class="wrap">
      ${boardHead("一 · 每股計量", "當期的兩種每股含幣量", 
        `${"推導說只需要四個量就能決定全部。這一頁是那四個量今天的值,"
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

      <h2 style="margin:34px 0 10px">資料可信度</h2>
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
        <a href="#/provenance">出處</a>。
      </p>

      <h2 style="margin:34px 0 10px">插值距離</h2>
      <p class="lede" style="margin-bottom:12px">
        持幣與美元流動性是 8-K 逐週揭露的<b>實測值</b>;可轉債、現金、股數
        來自季度 XBRL,中間是<b>線性插值</b>。所以求償權 ${tex0("C")} 的日內變化
        有一部分是插出來的 —— 錨點附近最可信,錨點中間最弱。
      </p>
      <div class="grid3" style="margin-bottom:10px">
        ${tile("±15 天內有真實申報", String(buckets.live),
          `天(${pct(buckets.live / N)})`, { tone: "var(--good)" })}
        ${tile("16–90 天", String(buckets.near), `天(${pct(buckets.near / N)})`)}
        ${tile("90 天以上", String(buckets.far), `天(${pct(buckets.far / N)})`,
          { tone: buckets.far ? "var(--warn)" : undefined })}
        ${tile("融資來源涵蓋率", pct(st.coveredPct),
          `${st.statedWeeks + st.derivedWeeks}/${st.activeWeeks} 個有買賣的週次<br>
           ${st.statedWeeks} 明示 + ${st.derivedWeeks} 推得`)}
      </div>

      <h2 style="margin:34px 0 10px">結構變化偵測</h2>
      <p class="lede" style="margin-bottom:12px">
        分期是編輯判斷,不是演算法切出來的 —— 但「該不該重新檢視分期」
        可以自動提醒:求償權變動超過 5%、優先股穿越面額、
        或當期已持續超過半年時列出。
      </p>
      ${meta.watch.length
        ? `<ul class="watch-list">${meta.watch.map((w) => `<li>${w}</li>`).join("")}</ul>`
        : `<p class="note" style="margin-top:0">目前沒有觸發任何提示。</p>`}

      <h2 style="margin:34px 0 10px">逐週原始資料</h2>
      <p class="lede" style="margin-bottom:14px">
        沒有插值的那一份 —— 累計持有量畫成階梯線,只在公司實際揭露的那天跳動。
        <b>週次可以點</b>,連回 EDGAR 上那一份 8-K。
      </p>
      <div class="card flush" style="padding:18px 22px 8px;margin-bottom:14px">
        <div class="scroller"><div id="board-accum"></div></div>
      </div>
      <div class="card flush"><div class="scroller tall">${accumulationTable()}</div></div>
      <p style="font-size:.8rem;color:var(--ink-3);margin-top:10px">
        共 ${st.weeks} 週。各券種欄位為該週 ATM 淨募資(百萬美元),
        「—」代表當週未動用;沒有連結的週次代表那一週只有持有量觀測。
      </p>

      <div class="note" style="margin-top:28px">
        <b>接下來:</b>這四個量怎麼變成現在這樣的?
        <a href="#/board/tools">儀表板 · 資本操作</a>列出公司實際用過的每一個動作。
      </div>
    </div>`;

  const teardownExplorer = explorer(
    root.querySelector<HTMLElement>("#board-explorer")!);
  const z = zoomable(root.querySelector<HTMLElement>("#board-accum")!,
    "BTC 累計持有量與逐週買賣(依融資來源上色)",
    (el, h) => { drawAccumulation(el, h); },
    { inlineHeight: 320, zoomHeight: 600 });
  return () => { teardownExplorer(); z.destroy(); };
};

/** 行內符號。推導那邊用 KaTeX,這裡只是要一個等寬的 C,不值得載整個 KaTeX。 */
const tex0 = (s: string) => `<i style="font-family:var(--serif)">${s}</i>`;
