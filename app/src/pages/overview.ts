import { chronicle, daily, N } from "../data";
import { explorer } from "../components/explorer";
import { btc as fmtBtc, pct } from "../lib/format";
import type { PageFn } from "../router";

export const overviewPage: PageFn = (root) => {
  const i = N - 1;
  const commonShare = daily.common_btc[i]! / daily.held[i]!;
  const latest = chronicle[chronicle.length - 1];
  const m = latest?.metrics;

  root.innerHTML = `
    <div class="wrap">
      <div class="page-head">
        <p class="eyebrow">總覽</p>
        <h1>Strategy(MSTR):一家靠發行證券買比特幣的公司</h1>
        <p class="lede">
          Strategy 原名 MicroStrategy,本業是企業軟體。2020 年起,它把比特幣訂為
          主要的庫存儲備資產,並逐步轉型為以數位資產負債表為核心的融資機構 ——
          目前持有 <b>${fmtBtc(daily.held[i]!)} 顆比特幣</b>,是全球持幣最多的上市公司。
        </p>
        <p class="lede">
          關鍵在於<b>這些幣是怎麼買來的</b>。公司不靠營運現金流買幣,
          而是持續向資本市場發行三類證券 —— 可轉換公司債、五檔永續優先股,
          以及隨市價增發的普通股(ATM)—— 再把募得的美元全數投入現貨市場。
          這是一套刻意的設計:<b>把高波動的底層資產,重組為波動特性迥異的多層求償權</b>,
          由信貸層吸收固定收益需求,由普通股承接全部剩餘波動。
        </p>
        <p class="lede">
          於是形成<b>一家公司、兩層股東</b>:可轉債與優先股排在前面,
          對公司有一筆固定美元的請求權;普通股排在最後,拿剩下的。
          目前普通股分到的是全部持幣的 <b>${pct(commonShare)}</b>。
        </p>
        <div class="note key">
          <b>所以 MSTR 不是比特幣的代理品。</b>
          它的股價同時受四件事推動:<b>幣價</b>、<b>公司的資本操作</b>、
          <b>求償權的縮放</b>,以及<b>市場願意付的溢價</b>。
          這個網站做的事,就是把這四塊逐日拆開 —— 拆得開,誤差為零。
          <div style="margin-top:10px">
            下面的時間軸可以拖到任何一天,看當天的股價是怎麼被拆出來的。
          </div>
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
            <b class="${(m.claims.pct ?? 0) < 0 ? "up" : "down"}">${
              m.claims.pct == null ? "—" : (m.claims.pct >= 0 ? "+" : "") + m.claims.pct.toFixed(1) + "%"}</b></span>
          <span>實得每股
            <b class="${(m.cebe.pct ?? 0) >= 0 ? "up" : "down"}">${
              m.cebe.pct == null ? "—" : (m.cebe.pct >= 0 ? "+" : "") + m.cebe.pct.toFixed(1) + "%"}</b></span>
          <span>持幣
            <b>${m.held.pct == null ? "—" : (m.held.pct >= 0 ? "+" : "") + m.held.pct.toFixed(1) + "%"}</b></span>
        </div>
      </a>` : ""}

      <div id="explorer"></div>

      <div class="note" style="margin-top:30px">
        <b>這套結構由兩個方向相反的控制迴路維持。</b>
        一個把溢價推上去 —— 只要市場願意付的倍數大於一,增發股票買幣就會讓
        <b>每股</b>含幣量上升,所以對外論述不是公關,是融資前提。
        另一個把信貸端拉回面額 —— 浮動股息、折價回購、美元儲備,
        全都在壓制同一個偏差。
        <div style="margin-top:10px">
          少了第一個,增厚沒有動力;少了第二個,正反饋沒有阻尼,遇到衝擊就發散。
          機制與代數在 <a href="#/lecture/structure">推導 · 〇 · 資本架構</a> ——
          其中一條結果是:<b>每股含幣量的年度成長率,上界等於溢價倍數減一</b>。
        </div>
      </div>

      <div class="grid2" style="margin-top:30px">
        <div>
          <h3 style="margin-bottom:8px">怎麼讀這三張圖</h3>
          <p style="font-size:.9rem;color:var(--ink-2);margin-bottom:10px">
            <b>第一張</b>把 MSTR 與 BTC 放在同一個基期,看兩者何時分家 ——
            分家的幅度就是市場情緒與資本結構共同作用的結果。</p>
          <p style="font-size:.9rem;color:var(--ink-2);margin-bottom:10px">
            <b>第二張</b>是同一天的兩種 mNAV。basic 完全看不到優先股,
            CEBE 把求償權扣掉之後再比 —— 兩條線的間距就是優先股造成的差別。</p>
          <p style="font-size:.9rem;color:var(--ink-2);margin:0">
            <b>第三張</b>把資產負債表攤平:下面幾層是求償權(依清償順位堆疊),
            上面那層是 MSTR 市值,虛線是 BTC 總市值。堆疊頂端高過虛線代表市場付溢價,
            縮在虛線之下代表打折。</p>
        </div>
        <div>
          <h3 style="margin-bottom:8px">接下來看什麼</h3>
          <p style="font-size:.9rem;color:var(--ink-2);margin-bottom:10px">
            <a href="#/lecture/structure">推導 · 資本架構</a> ——
            求償權階梯長什麼樣、為什麼<b>沒有一層以幣設質</b>(所以不存在強制平倉),
            以及增厚機制的上界在哪。</p>
          <p style="font-size:.9rem;color:var(--ink-2);margin-bottom:10px">
            <a href="#/board/quantities">儀表板 · 每股計量</a> ——
            它到底買了多少幣、每一批是拿哪個 ATM 的錢買的,逐週原始資料。</p>
          <p style="font-size:.9rem;color:var(--ink-2);margin-bottom:10px">
            <a href="#/posts/chronicle">大事記</a> ——
            公司在不同階段用的是完全不同的資本工具,對股東的後果也完全相反。</p>
          <p style="font-size:.9rem;color:var(--ink-2);margin-bottom:10px">
            <a href="#/lecture/quantities">推導 · 每股計量</a> ——
            求償權怎麼算、兩個每股指標差在哪裡,以及公司能動用哪些工具去改變它。</p>
          <p style="font-size:.9rem;color:var(--ink-2);margin:0">
            <a href="#/pricing">槓桿與定價</a> ——
            求償權固定在美元,所以實得每股含幣量是一個對 BTC 有槓桿的部位。</p>
        </div>
      </div>
    </div>`;

  return explorer(root.querySelector<HTMLElement>("#explorer")!, {
    charts: ["price", "mnav", "riverUsd"], showIdentity: true,
  });
};
