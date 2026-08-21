import { daily, indexOfDate, N } from "../data";
import { explorer } from "../components/explorer";
import { btc as fmtBtc, pct } from "../lib/format";
import type { PageFn } from "../router";

export const overviewPage: PageFn = (root) => {
  const i = N - 1;
  const first = indexOfDate("2024-12-31");
  const commonShare = daily.common_btc[i]! / daily.held[i]!;
  const commonShare0 = daily.common_btc[first]! / daily.held[first]!;

  root.innerHTML = `
    <div class="wrap">
      <div class="page-head">
        <p class="eyebrow">總覽</p>
        <h1>一家公司,兩層股東</h1>
        <p class="lede">MSTR 買了 ${fmtBtc(daily.held[i]!)} 顆比特幣,但這些幣不全是普通股股東的。
          優先股與可轉債排在前面,先切走固定金額的一塊,剩下的才輪到普通股。
          兩年前普通股還能分到 ${pct(commonShare0)},現在只剩 ${pct(commonShare)}。
          下面的時間軸可以拖到任何一天,看當天的股價是怎麼被拆出來的。</p>
      </div>

      <div id="explorer"></div>

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
            <a href="#/accumulation">持幣與融資</a> ——
            它到底買了多少幣、每一批是拿哪個 ATM 的錢買的,逐週原始資料。</p>
          <p style="font-size:.9rem;color:var(--ink-2);margin-bottom:10px">
            <a href="#/structure">資本結構</a> ——
            把縱軸換成「幣的顆數」,會看到一件用美元看不出來的事:
            公司一直在買幣,普通股分到的量卻幾乎沒動。</p>
          <p style="font-size:.9rem;color:var(--ink-2);margin:0">
            <a href="#/pricing">槓桿與定價</a> ——
            但那不代表白買。BTC 漲回來的時候,每股含幣量會自己長回來。</p>
        </div>
      </div>
    </div>`;

  return explorer(root.querySelector<HTMLElement>("#explorer")!, {
    charts: ["price", "mnav", "riverUsd"], showIdentity: true,
  });
};
