/** 總覽 —— 唯一一頁要對完全沒看過的人說話。
 *
 *  論述照 reference/00-purpose.md 的主線走,順序不可以換:
 *    它是誰 → 目的(贏過比特幣)→ 怎麼做到(把風險往外推)
 *    → ⚠️ 轉嫁≠不用管(閘門)→ 所以股價要怎麼讀
 *
 *  每一段都要能指回「贏過比特幣」。指不回去的不要放在這一頁。 */
import { chronicle, daily, meta, N } from "../data";
import { explorer } from "../components/explorer";
import { btc as fmtBtc, pct } from "../lib/format";
import type { PageFn } from "../router";

export const overviewPage: PageFn = (root) => {
  const i = N - 1;
  const commonShare = daily.common_btc[i]! / daily.held[i]!;
  const latest = chronicle[chronicle.length - 1];
  const m = latest?.metrics;
  const sign = (v: number | null | undefined) =>
    v == null ? "—" : (v >= 0 ? "+" : "") + v.toFixed(1) + "%";

  root.innerHTML = `
    <div class="wrap">
      <div class="page-head">
        <p class="eyebrow">總覽</p>
        <h1>Strategy(MSTR):用資本市場的錢,贏過比特幣</h1>
        <p class="lede">
          Strategy 原名 MicroStrategy,本業是企業軟體。2020 年起把比特幣訂為主要儲備資產,
          目前持有 <b>${fmtBtc(daily.held[i]!)} 顆</b>,是全球持幣最多的上市公司。
        </p>
        <p class="lede">
          但它的目標比「持有比特幣」高一階。<b>如果只是要比特幣的曝險,買幣或買 ETF 就好</b> ——
          一家上市公司值得存在的理由,是它能做到<b>比單純持有更好</b>。
          而比特幣是有限的,所以「更好」只有一種定義:
          <b>每一股背後含有的比特幣要變多。</b>
        </p>
      </div>

      <h2 style="margin:28px 0 8px">做法:把風險一步步推給市場</h2>
      <p class="lede" style="margin-bottom:14px">
        公司自己沒有錢一直買幣,必須向資本市場要。而<b>用什麼名義要,決定了風險留在誰身上</b>:
      </p>
      <div class="card flush" style="margin-bottom:16px"><div class="scroller">
        <table class="mini">
          <thead><tr><th>工具</th><th>風險在誰</th><th>代價</th></tr></thead>
          <tbody>
            <tr><td>抵押借錢</td><td><b>公司</b></td>
                <td>幣價跌破線就被強制清算 —— 而那是你最不想賣幣的時候</td></tr>
            <tr><td>可轉換公司債</td><td>公司,但小得多</td>
                <td>無擔保、到期日長,所以沒有保證金追繳;<b>發出去就不用再管</b></td></tr>
            <tr><td>永續優先股</td><td><b>市場</b></td>
                <td>風險賣掉了,但換來一個新問題 —— 見下</td></tr>
          </tbody>
        </table>
      </div></div>
      <p class="lede" style="margin-bottom:24px">
        跟銀行借錢,風險很高<b>而且在自己身上</b>;用證券發售出去,<b>風險就在市場</b>。
        前提是市場規模要夠大 —— 規模夠大才有議價權,有議價權才轉嫁得掉。
      </p>

      <div class="note key" style="margin-bottom:24px">
        <b>⚠️ 但轉嫁出去,不等於不用管。</b>
        可轉債發出去就不用再碰;優先股不一樣,它需要被管理。
        <div style="margin-top:10px">
          優先股跌到 70、60,<b>跟公司的盈虧沒有關係</b> —— 公司照常付息,帳上一毛都不會少。
          <b>但公司要繼續買幣擴張,就得把它帶回面額。</b>
        </div>
        <div style="margin-top:10px">
          所以優先股的市價相對面額是一道<b>閘門</b>:開著才能再發行、再買幣、再加槓桿。
          折價回購、調整股息率、備足美元儲備、必要時賣幣 —— <b>全部是為了把閘門打開</b>。
        </div>
        <div style="margin-top:10px">
          <b>風險是市場的,約束是公司的。</b>
          公司幫市場管理風險不是出於責任,是因為它需要市場再借一次。
        </div>
      </div>

      ${latest && m ? `
      <a class="latest-era" href="#/posts/chronicle">
        <div class="latest-era-top">
          <span class="eyebrow" style="margin:0">目前階段</span>
          ${latest.ongoing ? `<span class="badge live"><i class="dot"></i>進行中</span>` : ""}
        </div>
        <div class="latest-era-title">${latest.title}</div>
        <div class="latest-era-sub">${latest.subtitle}</div>
        <div class="latest-era-stats">
          <span><i>自 ${latest.start}</i> 求償權
            <b class="${(m.claims.pct ?? 0) < 0 ? "up" : "down"}">${sign(m.claims.pct)}</b></span>
          <span>實得每股
            <b class="${(m.cebe.pct ?? 0) >= 0 ? "up" : "down"}">${sign(m.cebe.pct)}</b></span>
          <span>持幣 <b>${sign(m.held.pct)}</b></span>
        </div>
      </a>` : ""}

      <h2 style="margin:28px 0 8px">證據:波動確實被分層了</h2>
      <p class="lede" style="margin-bottom:14px">
        「把風險賣給市場」聽起來像說法。把每一檔的日線拿來算
        ${meta.vol.window} 天年化已實現波動率就看得到:
      </p>
      <div class="card flush" style="margin-bottom:14px"><div class="scroller">
        <table class="mini">
          <thead><tr><th>工具</th><th class="n">年化已實現波動</th>
            <th class="n">相對普通股剝離</th></tr></thead>
          <tbody>${meta.vol.rows.map((r) => `
            <tr><td><b>${r.t}</b></td>
                <td class="n">${r.vol.toFixed(1)}%</td>
                <td class="n">${r.damp == null ? "—" : r.damp.toFixed(0) + "%"}</td></tr>`
          ).join("")}</tbody>
        </table>
      </div></div>
      <p class="lede" style="margin-bottom:24px">
        普通股的波動是比特幣的 <b>${meta.vol.amp?.toFixed(2)}x</b> ——
        <b>被剝下來的波動全部塞到這裡</b>。
        而且注意 <b>STRK 比 STRD 優先,波動卻高得多</b>:
        如果低波動只是順位的副產品,這裡應該反過來。它沒有,因為 STRK 嵌了轉換權。
        <b>波動階梯跟著條款走,不跟著順位走</b> ——
        剝離波動不是順位的副作用,是逐條設計出來的。
      </p>

      <h2 style="margin:28px 0 8px">所以股價要分兩種口徑讀</h2>
      <p class="lede" style="margin-bottom:14px">
        上了槓桿之後,同一個問題有兩個答案,<b>差別只在分母算不算求償權</b>。
        目前普通股分到的是全部持幣的 <b>${pct(commonShare)}</b>。
      </p>
      <div class="card flush" style="margin-bottom:14px"><div class="scroller">
        <table class="mini">
          <thead><tr><th>分母</th><th>相對市值</th><th>相對股數</th><th>它回答什麼</th></tr></thead>
          <tbody>
            <tr><td>全部持幣</td><td>basic mNAV</td><td><b>帳面每股含幣量</b></td>
                <td>幣堆相對股數有多大 ·<b>公司公布的就是這一組</b></td></tr>
            <tr><td>扣求償權後</td><td><b>CEBE mNAV</b></td><td><b>實得每股含幣量</b></td>
                <td>我這一股實得多少 ·<b>本站整套算這一組</b></td></tr>
          </tbody>
        </table>
      </div></div>
      <p class="lede" style="margin-bottom:24px">
        不是哪一組比較準,是<b>它們回答不同的問題</b> ——
        同一天可以一個折價、一個溢價,因為分母差了一整個求償權。
        下面第二張圖畫的就是這兩條線的間距。
        <br><br>
        <b>而且槓桿加大並不會自動讓每股含幣量上升。</b>
        求償權是美元計價,每股含幣量是比特幣計價 —— 幣價上漲時那筆美元債在幣計價下縮水,
        扣掉之後普通股分到的幣才變多,<b>而普通股股數並沒有新增發行</b>。
        加槓桿加的是<b>對幣價的曝險</b>,不是直接加每股含幣量。
        推導在 <a href="#/lecture/structure">推導 · 資本架構</a>。
      </p>

      <div id="explorer"></div>

      <div class="grid2" style="margin-top:30px">
        <div>
          <h3 style="margin-bottom:8px">怎麼讀這三張圖</h3>
          <p style="font-size:.9rem;color:var(--ink-2);margin-bottom:10px">
            <b>第一張</b>把 MSTR 與 BTC 放在同一個基期,看兩者何時分家。</p>
          <p style="font-size:.9rem;color:var(--ink-2);margin-bottom:10px">
            <b>第二張</b>是同一天的兩種 mNAV —— 兩條線的間距就是求償權造成的差別。</p>
          <p style="font-size:.9rem;color:var(--ink-2);margin:0">
            <b>第三張</b>把資產負債表攤平:下面幾層是求償權(依清償順位堆疊),
            上面那層是 MSTR 市值,虛線是 BTC 總市值。</p>
        </div>
        <div>
          <h3 style="margin-bottom:8px">接下來看什麼</h3>
          <p style="font-size:.9rem;color:var(--ink-2);margin-bottom:10px">
            <a href="#/lecture/structure">推導 · 資本架構</a> ——
            三代工具的演進、為什麼<b>沒有一層以幣設質</b>、閘門怎麼開。</p>
          <p style="font-size:.9rem;color:var(--ink-2);margin-bottom:10px">
            <a href="#/board/tools">儀表板 · 資本操作</a> ——
            它實際動用過哪些工具、每一筆多少錢。</p>
          <p style="font-size:.9rem;color:var(--ink-2);margin-bottom:10px">
            <a href="#/posts/chronicle">觀點 · 大事記</a> ——
            不同階段用的是完全不同的工具,對股東的後果也完全相反。</p>
          <p style="font-size:.9rem;color:var(--ink-2);margin:0">
            <a href="#/pricing">槓桿與定價</a> ——
            求償權固定在美元,所以實得每股含幣量是一個對幣價有槓桿的部位。</p>
        </div>
      </div>
    </div>`;

  return explorer(root.querySelector<HTMLElement>("#explorer")!, {
    charts: ["price", "mnav", "riverUsd"], showIdentity: true,
  });
};
