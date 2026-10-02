import { daily, meta, N } from "../data";
import { accumulationStats } from "../charts/accumulation";
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

export const dataQualityPage: PageFn = (root) => {
  const buckets = { live: 0, near: 0, far: 0 };
  for (const s of daily.stale) {
    if (s <= 15) buckets.live++;
    else if (s <= 90) buckets.near++;
    else buckets.far++;
  }
  const anchors = meta.anchors.btc_held;
  const gaps = anchors.slice(1).map((a, i) =>
    (new Date(a[0]).getTime() - new Date(anchors[i]![0]).getTime()) / 86400000);
  const maxGap = Math.max(...gaps);
  const avgGap = gaps.reduce((s, g) => s + g, 0) / gaps.length;
  // 與「持幣與融資」頁共用同一套定義,避免同一個網站出現兩個不一樣的涵蓋率:
  // 分母只算真的有進出幣的週次(零交易週不需要資金來源),
  // 分子是敘述句明示 + 由 ATM 表推得。
  const st = accumulationStats();
  const prov = meta.prov;

  root.innerHTML = `
    <div class="wrap">
      <div class="page-head">
        <p class="eyebrow">資料品質</p>
        <h1>這份分析站不住的地方</h1>
        <p class="lede">每個數字的來源與可信度都攤開來講。原始數值全部保留未改 ——
          發現來源自相矛盾時記錄下來,而不是悄悄修掉。</p>
      </div>

      <div class="grid3" style="margin-bottom:26px">
        <div class="tile"><div class="k">BTC 持有量錨點</div><div class="v">${anchors.length}</div>
          <div class="d">8-K 週報為主,季度申報補空檔<br>平均間隔 ${avgGap.toFixed(1)} 天,最長 ${maxGap.toFixed(0)} 天</div></div>
        <div class="tile"><div class="k">日頻覆蓋</div><div class="v">${N}</div>
          <div class="d">交易日<br>${daily.date[0]} → ${daily.date[N - 1]}</div></div>
        <div class="tile"><div class="k">融資來源涵蓋率</div><div class="v">${(st.coveredPct * 100).toFixed(0)}%</div>
          <div class="d">${st.statedWeeks + st.derivedWeeks}/${st.activeWeeks} 個有買賣的週次<br>
            ${st.statedWeeks} 明示 + ${st.derivedWeeks} 推得</div></div>
        <div class="tile"><div class="k">官方錨點誤差</div><div class="v">&lt;1bp</div>
          <div class="d">FWP 敏感度表六列全數重現</div></div>
      </div>

      <h3 style="margin-bottom:12px">插值距離分布</h3>
      <div class="card" style="margin-bottom:8px">
        <div style="display:flex;height:26px;border-radius:3px;overflow:hidden;margin-bottom:10px">
          <div style="width:${(buckets.live / N) * 100}%;background:var(--equity)"></div>
          <div style="width:${(buckets.near / N) * 100}%;background:var(--good)"></div>
          <div style="width:${(buckets.far / N) * 100}%;background:var(--senti)"></div>
        </div>
        <div class="legend">
          <span><i class="swatch" style="background:var(--equity)"></i>±15 天內有真實申報 · ${buckets.live} 天(${((buckets.live / N) * 100).toFixed(0)}%)</span>
          <span><i class="swatch" style="background:var(--good)"></i>16–90 天 · ${buckets.near} 天(${((buckets.near / N) * 100).toFixed(0)}%)</span>
          <span><i class="swatch" style="background:var(--senti)"></i>90 天以上 · ${buckets.far} 天(${((buckets.far / N) * 100).toFixed(0)}%)</span>
        </div>
      </div>
      <p style="font-size:.82rem;color:var(--ink-3);margin-bottom:30px">
        這個指標只看真正牽動 mNAV 讀數的欄位(BTC 持有量、股數、可轉債、現金、STRC)。
        STRF/STRK/STRD 的股數已用 ATM 表重建成逐週序列,STRE 沒有 ATM 只有單點;
        可轉債與現金來自季度 XBRL,本來就只有季頻,是目前插值距離的主要來源。</p>

      <h3 style="margin-bottom:12px">結構變化偵測</h3>
      <p style="font-size:.86rem;color:var(--ink-2);margin-bottom:12px">
        分期是編輯判斷,不是演算法切出來的 —— 但「該不該重新檢視分期」可以自動提醒。
        每次跑資料管線時會比對目前狀態與<a href="#/chronicle">當期</a>起點,
        在求償權變動超過 5%、優先股穿越面額($100)、或當期已經持續超過半年時列出提示。
      </p>
      ${meta.watch.length ? `
        <ul class="watch-list">
          ${meta.watch.map((w) => `<li>${w}</li>`).join("")}
        </ul>` : `
        <p class="note" style="margin-top:0">目前沒有觸發任何提示。</p>`}

      <h3 style="margin:34px 0 12px">每個數字都指得回一份文件</h3>
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

      <h3 style="margin-bottom:12px">三種粒度,粗的只能補洞</h3>
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
          「建置期發現的問題」裡 —— 不會被悄悄抹平。</p>` : ""}

      <h3 style="margin-bottom:12px">買幣的錢對得上嗎</h3>
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

      <h3 style="margin:30px 0 14px">建置期發現的問題</h3>
      <div class="grid2">
        ${meta.findings.map((f) => `
          <div class="card"><h3 style="font-size:1rem;margin-bottom:7px">${f.t}</h3>
          <p style="font-size:.87rem;color:var(--ink-2);margin:0">${f.b}</p></div>`).join("")}
      </div>

      <h3 style="margin:32px 0 12px">資料來源</h3>
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
