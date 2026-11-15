/** 儀表板 · 每股計量 —— L1 的數值解。
 *
 *  推導說「只需要四個量」,這一頁說「今天這四個量各是多少、從哪來」。 */
import { daily, meta, N } from "../../data";
import { accumulationStats, accumulationTable, drawAccumulation }
  from "../../charts/accumulation";
import { boardHead, tile } from "../../components/board";
import { BADGE_ORDER, FIELD_LABEL, freshness, METHOD_LABEL } from "../../metrics/asof";
import { explorer } from "../../components/explorer";
import { zoomable } from "../../lib/zoomable";
import { bn, btc as fmtBtc, pct, usd0 } from "../../lib/format";
import { metricAt } from "../../metrics/read";
import type { PageFn } from "../../router";
import { setIndex } from "../../state";

export const boardQuantitiesPage: PageFn = (root) => {
  setIndex(N - 1);
  const i = N - 1;
  const claims = metricAt("claims.cebe", i);
  const debt = metricAt("claims.debt", i);
  const pref = metricAt("claims.pref", i);
  const cash = metricAt("claims.cash", i);
  const held = metricAt("btc.held", i);
  const shares = metricAt("shares.basic", i);
  const px = metricAt("price.btc", i);
  const book = metricAt("btc.perShare.basic", i);
  const perShare = metricAt("btc.perShare.cebe", i).value!;
  const mnavCebe = metricAt("mnav.cebe", i);
  const mnavBasic = metricAt("mnav.basic", i);
  const prov = meta.prov;
  const st = accumulationStats();
  const fields = BADGE_ORDER.map((id) => freshness(id, i));

  root.innerHTML = `
    <div class="wrap">
      ${boardHead("一 · 每股計量", "當期的兩種每股含幣量", 
        `${"推導說只需要四個量就能決定全部。這一頁是那四個量今天的值,"
        }每一個標了自己的方法與截至日。`,
        "#/lecture/quantities", daily.date[i]!)}

      <div class="grid3" style="margin-bottom:12px">
        ${tile("總持幣 H", fmtBtc(held.value), "顆 BTC",
          { src: `${METHOD_LABEL[held.method]} · 截至 ${held.asOf}` })}
        ${tile("淨求償權 C", bn(claims.value),
          `可轉債 ${bn(debt.value)} + 優先股 ${bn(pref.value)} − 現金 ${bn(cash.value)}`)}
        ${tile("在外股數 S", shares.value!.toFixed(1) + "M", "basic 股數,不含假設轉股")}
        ${tile("比特幣價格 p", usd0(px.value!), "Binance 日線收盤")}
      </div>

      <div class="grid3" style="margin-bottom:26px">
        ${tile("帳面每股 B", Math.round(book.value!).toLocaleString(),
          "sats。總持幣 ÷ 股數,看不到求償權")}
        ${tile("實得每股 E", Math.round(perShare).toLocaleString(),
          `sats。扣掉求償權之後,求償權吃掉 ${pct(1 - perShare / book.value!)}`,
          { tone: "var(--equity)" })}
        ${tile("市場溢價 m", mnavCebe.value!.toFixed(3) + "x",
          `CEBE mNAV。basic mNAV 是 ${mnavBasic.value!.toFixed(3)}x`,
          { tone: "var(--senti)" })}
        ${tile("槓桿 A", daily.amp[i]!.toFixed(2) + "x",
          "幣價變動 1% 時每股殘值變動幾 %")}
      </div>

      <div class="chart-block">
        <div class="chart-head"><div class="chart-label">拖曳任一張圖看任何一天</div></div>
      </div>
      <div id="board-explorer"></div>

      <h2 style="margin:34px 0 10px">各欄截至日</h2>
      <p class="lede" style="margin-bottom:14px">
        持幣只在 8-K 揭露日跳動。可轉債、現金欄、股數在兩次申報之間若斜率不變，
        就是依日數比例補上；數值停住時沿用上一筆，中間沒有補點。
      </p>
      <div class="card flush" style="margin-bottom:12px"><div class="scroller"><table class="mini">
        <thead><tr><th>欄位</th><th>方法</th><th>截至</th><th>說明</th></tr></thead>
        <tbody>
          ${BADGE_ORDER.map((id, k) => `<tr>
            <td>${FIELD_LABEL[id]}</td>
            <td><span class="badge" data-method="${fields[k]!.method}">${METHOD_LABEL[fields[k]!.method]}</span></td>
            <td>${fields[k]!.asOf}</td>
            <td>${freshness(id, i).note}</td></tr>`).join("")}
        </tbody></table></div></div>
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

      <div class="grid3" style="margin-bottom:10px">
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
        累計持有量畫成階梯線,只在公司實際揭露的那天跳動。
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
