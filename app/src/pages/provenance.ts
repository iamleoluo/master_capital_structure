/** 出處 —— L1 的檔案庫、粒度規則與資金對帳。
 *
 *  **「這個數字能信多少」溶在儀表板每個數字旁邊;這一頁講的是
 *  「這個數字是怎麼來的」。** 兩件事不同(見 reference/11-site.md §2.1)。
 *
 *  由 pages/dataQuality.ts 改名而來:原本那一頁把兩件事混在一起,
 *  讀者要讀完整頁才知道哪裡不能信。插值距離與結構變化偵測已搬到
 *  儀表板 · 每股計量,留在這裡的是出處本身。 */
import { meta } from "../data";
import { edgarFormUrl } from "../lib/format";
import type { PageFn } from "../router";

const FORM_OF: Record<string, string> = {
  sec_8k: "8-K", sec_10q: "10-Q", sec_10k: "10-K", sec_424b5: "424B5",
};

const SRC_LABEL: Record<string, string> = {
  sec_8k: "8-K 每週揭露", sec_10q: "10-Q 季報", sec_10k: "10-K 年報",
  sec_424b5: "424B5 公開說明書", sec_xbrl: "XBRL companyfacts",
  sec_submissions: "申報索引",
};

export const provenancePage: PageFn = (root) => {
  const prov = meta.prov;

  root.innerHTML = `
    <div class="wrap">
      <div class="page-head">
        <p class="eyebrow">出處</p>
        <h1>每個數字是怎麼來的</h1>
        <p class="lede">申報原文全部內容定址存檔,解析器只讀檔案庫、不碰網路 ——
          同一份原文永遠解出同一個數字。這一頁講的是<b>數字怎麼來的</b>;
          <b>能信多少</b>(插值距離、口徑偏差)貼在
          <a href="#/board">儀表板</a>每個數字旁邊。</p>
      </div>

            <h2 style="margin:0 0 12px">檔案庫</h2>
      <p style="font-size:.86rem;color:var(--ink-2);margin-bottom:14px">
        申報原文全部內容定址存檔(sha256),解析器只讀檔案庫、不碰網路 ——
        所以同一份原文永遠解出同一個數字,而且任何一個數字都能回推到
        哪一份申報的哪一個位置。稽核軌跡在
        <code>web/archive/manifest.json</code>,每列有 url 與 sha256,
        任何人都能自己抓來對。
      </p>
      <div class="card flush" style="margin-bottom:10px"><div class="scroller"><table class="mini">
        <thead><tr><th>表單</th><th>份數</th><th>期間</th><th>原文大小</th></tr></thead>
        <tbody>
          ${prov.docs.map((d) => {
            const form = FORM_OF[d.src];
            const label = SRC_LABEL[d.src] ?? d.src;
            return `<tr><td>${form
              ? `<a class="src" href="${edgarFormUrl(form)}" target="_blank" rel="noopener"
                   title="在 EDGAR 上看這家公司的全部 ${form}">${label}</a>`
              : label}</td>
            <td>${d.n}</td><td>${d.lo} → ${d.hi}</td><td>${d.mb.toFixed(1)} MB</td></tr>`;
          }).join("")}
          <tr style="font-weight:600"><td>合計</td><td>${prov.doc_total}</td><td></td>
            <td>${prov.docs.reduce((a, d) => a + d.mb, 0).toFixed(1)} MB</td></tr>
        </tbody></table></div></div>
      <p style="font-size:.82rem;color:var(--ink-3);margin-bottom:30px">
        由這些文件推出 ${prov.event_total.toLocaleString()} 個事件,其中
        ${prov.action_total.toLocaleString()} 個是<strong>動作</strong>(公司做了什麼),
        其餘是<strong>觀測</strong>(當下的餘額)。兩者在資料結構上分家 ——
        混在一起會把「餘額變了」讀成「公司做了什麼」。
      </p>

      <h2 style="margin:34px 0 12px">三種粒度:粗粒度只用於補洞</h2>
      <p style="font-size:.86rem;color:var(--ink-2);margin-bottom:14px">
        同一批動作會被三份文件各講一次 —— 8-K 的週表、10-Q 的季表、10-K 的年表。
        <strong>三者不得相加</strong>,否則同一筆錢會被算好幾次。規則是粗粒度只能
        補上細粒度沒蓋到的部分。驗證方式是看年報:
      </p>
      <div class="card flush" style="margin-bottom:10px"><div class="scroller"><table class="mini">
        <thead><tr><th>年</th><th>10-K 講的買幣</th><th>被季與週解釋掉之後還剩</th><th></th></tr></thead>
        <tbody>
          ${prov.years.map((y) => `<tr><td>${y.y}</td>
            <td>$${Math.abs(y.stated_b).toFixed(2)}B</td>
            <td>$${Math.abs(y.left_b).toFixed(3)}B</td>
            <td style="color:var(--ink-3)">${y.pct.toFixed(1)}%</td></tr>`).join("")}
        </tbody></table></div></div>
      <p style="font-size:.82rem;color:var(--ink-3);margin-bottom:${prov.conflicts.length ? 10 : 30}px">
        年報是另一次獨立申報。週與季若有系統性的漏記或重複,這裡會留下一大塊殘差。
      </p>
      ${prov.conflicts.length ? `
        <p class="note" style="margin-bottom:30px">
          ${prov.conflicts.length} 筆跨文件對不上的粗粒度事件,全部列在下方
          「建置期發現的資料問題」裡 —— 不會被悄悄抹平。</p>` : ""}

      <h2 style="margin:34px 0 12px">資金流對帳</h2>
      <p style="font-size:.86rem;color:var(--ink-2);margin-bottom:14px">
        這是對整份分析最直接的檢查:<strong>買幣 + 股息 + 回購 + 儲備增加
        = 各種募資 + 賣幣</strong>。兩邊都是現金口徑,所以不受「優先股按面額
        還是按市價計」那個選擇影響。
      </p>
      <div class="card flush" style="margin-bottom:10px"><div class="scroller"><table class="mini">
        <thead><tr><th>階段</th><th>用途</th><th>來源</th><th>未解釋</th><th>其中按天數攤分</th></tr></thead>
        <tbody>
          ${prov.recon.map((r) => `<tr>
            <td>${r.title}${r.resolvable ? "" : " ⚠️"}</td>
            <td>$${r.uses_b.toFixed(1)}B</td><td>$${r.sources_b.toFixed(1)}B</td>
            <td>${r.resolvable
              ? `${r.gap_b < 0 ? "−" : "+"}$${Math.abs(r.gap_b).toFixed(2)}B <span style="color:var(--ink-3)">(${r.gap_pct.toFixed(1)}%)</span>`
              : `<span style="color:var(--ink-3)">不成立</span>`}</td>
            <td style="color:var(--ink-3)">$${r.prorated_b.toFixed(1)}B</td></tr>`).join("")}
        </tbody></table></div></div>
      <p style="font-size:.82rem;color:var(--ink-3);margin-bottom:30px">
        階段邊界按結構轉折劃,不會剛好切在季底,所以跨段的季資料按天數攤 ——
        攤分的金額列在最後一欄。
        ${prov.recon.some((r) => !r.resolvable) ? `
          標 ⚠️ 的那一段<strong>比可用粒度還短</strong>
          (${prov.recon.filter((r) => !r.resolvable).map((r) => r.title).join("、")}),
          對帳結果會由攤分假設決定而不是由資料決定 —— 所以這裡不給數字。
          可用粒度比分析窗口還粗的時候,對帳不會錯,它只是不成立。` : ""}
      </p>

      <h2 style="margin:30px 0 14px">建置期發現的資料問題</h2>
      <div class="grid2">
        ${meta.findings.map((f) => `
          <div class="card"><h3 style="font-size:1rem;margin-bottom:7px">${f.t}</h3>
          <p style="font-size:.87rem;color:var(--ink-2);margin:0">${f.b}</p></div>`).join("")}
      </div>

      <h2 style="margin:34px 0 12px">資料來源</h2>
      <div class="card flush"><div class="scroller"><table class="mini">
        <thead><tr><th>資料</th><th>來源</th><th>頻率</th><th>取得方式</th></tr></thead>
        <tbody>
          <tr><td>BTC 日線</td><td>Binance</td><td>日</td><td>公開 API,免 key</td></tr>
          <tr><td>MSTR / STRF / STRC / STRK / STRD 日線</td><td>Yahoo Finance</td><td>日</td><td>chart 端點</td></tr>
          <tr><td>BTC 持有量、逐週買賣、融資來源</td><td>SEC 8-K</td><td>週</td><td>解析 BTC Update 表格與 prose 兩種版型</td></tr>
          <tr><td>各券種 ATM 募資</td><td>SEC 8-K</td><td>週</td><td>解析 ATM Program Summary 表格(2026-09 起該表已停止揭露)</td></tr>
          <tr><td>優先股回購</td><td>SEC 8-K</td><td>週</td><td>解析 Shares Repurchased 表格(2026-07-27 起)</td></tr>
          <tr><td>可轉債 / 現金 / 股數</td><td>SEC XBRL</td><td>季</td><td>companyconcept API</td></tr>
          <tr><td>買幣的資金歸屬(逐券種)</td><td>SEC 10-Q / 10-K 現金流量表</td><td>季</td><td>解析資金來源敘述;覆蓋 2025-09 之前 8-K 還沒揭露的那段</td></tr>
          <tr><td>優先股 IPO 的發行條件與面額</td><td>SEC 424B5</td><td>事件</td><td>五個系列全部解析驗證過,與手動輸入的面額完全吻合</td></tr>
          <tr><td>可轉債發行與償還</td><td>SEC XBRL</td><td>季</td><td>8-K 完全沒有這一項,只能靠 XBRL</td></tr>
          <tr><td>優先股分系列餘額</td><td>10-K / 10-Q / 8-K</td><td>季</td><td>人工整理,錨點間線性插值</td></tr>
          <tr><td>官方每股淨值錨點</td><td>${meta.fwp.date} Form FWP</td><td>單點</td><td>Tier 1,用於回歸驗證</td></tr>
        </tbody></table></div></div>
    </div>`;
};
