/** 資本結構 —— 常設的結構解釋,不綁任何時間點。
 *
 *  這一頁只回答「這家公司的資本結構長什麼樣、CEBE 是什麼、怎麼從圖上讀出來」。
 *  「某段期間發生了什麼」一律放到大事記,避免頁面隨資料更新而過期 ——
 *  先前這裡的標題是「帳面每股在漲,實際每股在縮」,在 2026-06 之後就不再成立了。 */
import { chronicle, daily, meta, N } from "../data";
import { explorer } from "../components/explorer";
import { toolkitTable } from "../components/toolkit";
import { bn, pct } from "../lib/format";
import type { PageFn } from "../router";

export const structurePage: PageFn = (root) => {
  const i = N - 1;
  const perShareOf = (k: number) =>
    (daily.common_btc[k]! / (daily.shares[k]! * 1e6)) * 1e8;

  const grossNow = daily.bps[i]!;
  const cebeNow = perShareOf(i);
  const eatenNow = grossNow - cebeNow;
  const claimsNow = daily.debt[i]! + daily.pref_total[i]! - daily.cash[i]!;

  const latest = chronicle[chronicle.length - 1];

  root.innerHTML = `
    <div class="wrap">
      <div class="page-head">
        <p class="eyebrow">資本結構</p>
        <h1>誰排在誰前面</h1>
        <p class="lede">MSTR 的比特幣不是全部屬於普通股股東的。可轉債與優先股排在前面,
          各自有一筆<b>鎖死在美元的固定請求權</b>;普通股拿的是把那些扣掉之後剩下的殘值。
          這一頁解釋這個結構怎麼運作、怎麼量化,以及公司能用哪些工具去改變它。</p>
      </div>

      <div class="grid3" style="margin-bottom:10px">
        <div class="tile"><div class="k">帳面每股(basic 股數)</div>
          <div class="v">${Math.round(grossNow).toLocaleString()}</div>
          <div class="d">sats。總持幣 ÷ basic 股數,不含可轉債稀釋</div></div>
        <div class="tile"><div class="k">求償權吃掉</div>
          <div class="v" style="color:var(--bad)">−${Math.round(eatenNow).toLocaleString()}</div>
          <div class="d">sats,佔帳面的 ${pct(eatenNow / grossNow)}<br>
            對應 ${bn(claimsNow)} 的固定美元請求權</div></div>
        <div class="tile" style="border-left:3px solid var(--equity)">
          <div class="k">CEBE(實際每股)</div>
          <div class="v" style="color:var(--equity)">${Math.round(cebeNow).toLocaleString()}</div>
          <div class="d">sats。這才是股東手上真正的量</div></div>
      </div>

      <div class="note" style="margin-bottom:26px">
        <b>公司官方揭露的 Gross BPS 其實更低。</b>
        上面「帳面每股」用的是 basic 股數,沒算進可轉債假設轉股的稀釋。
        公司最新一期 FWP 用「假設稀釋股數」(${(meta.fwp.assumed / 1e6).toFixed(1)}M,
        比 basic 多 ${((meta.fwp.assumed - meta.fwp.basic) / 1e6).toFixed(1)}M 股)算出來的官方 Gross BPS 是
        <b>${meta.fwp.gross_bps.toLocaleString()} sats</b> —— 比上面 basic 口徑的
        ${Math.round(grossNow).toLocaleString()} sats 低 ${pct(1 - meta.fwp.gross_bps / grossNow)}。
        這個「假設稀釋股數」只有官方在敏感度表裡揭露這一個數字,沒有歷史序列,
        所以「每股持幣」圖上只標成單點,不畫成整條線。</div>

      <h2 style="margin-bottom:8px">CEBE 是什麼</h2>
      <p class="lede" style="margin-bottom:18px">
        CEBE(Common Equity Bitcoin Exposure)就是<b>扣掉所有優先求償權之後,每股真正對應到的比特幣</b>。
        公式只有一行,但它解釋了這家公司絕大部分的行為:
      </p>

      <div class="card" style="padding:18px 20px;margin-bottom:26px">
        <div style="font-family:var(--mono);font-size:.92rem;line-height:2">
          求償權(BTC) = (可轉債 + 優先股清算優先權 − 現金) ÷ BTC 價格<br>
          CEBE = (總持幣 − 求償權(BTC)) ÷ 在外股數
        </div>
        <p style="font-size:.88rem;color:var(--ink-2);margin:12px 0 0">
          注意分子那一項:求償權的面額是<b>固定美元</b>,所以換算成「幾顆幣」時,
          分母是當下的 BTC 價格。BTC 漲,同一筆求償權吃掉的幣就變少,
          普通股不用多買一顆,每股含幣量就會自己上升 —— 這就是槓桿。
          反過來 BTC 跌的時候,它也會把跌幅放大。</p>
      </div>

      <h2 style="margin-bottom:8px">公司能動用的工具</h2>
      <p class="lede" style="margin-bottom:16px">
        改變這個結構的方法是有限且可列舉的。每一項對求償權、股數、持幣的作用不同,
        對 CEBE 的淨效果也不同 —— <b>真正會讓 CEBE 上升的只有右邊標成加分的那幾項</b>。
        公司在不同時期用的是不同組合,那就是<a href="#/chronicle">大事記</a>在記錄的事。
      </p>
      ${toolkitTable()}

      <div class="note key" style="margin:22px 0 30px">
        <b>目前在哪一段?</b>
        <a href="#/chronicle">${latest ? latest.title : "—"}</a>
        ${latest ? `—— ${latest.subtitle}。${latest.ongoing ? "進行中" : ""}` : ""}
      </div>

      <h2 style="margin-bottom:12px">從圖上讀出來</h2>
      <div id="explorer"></div>

      <div class="note" style="margin-top:24px">
        <b>怎麼從圖上讀出 CEBE。</b>
        BTC 計價那張圖的下緣是求償權(依清償順位堆疊),上緣的黑線是總持幣,
        中間那條橘色帶子就是普通股。帶子越薄代表 CEBE 越小。
        切到「每股」模式後,縱軸變成 sats／股,帶子的厚度直接就是 CEBE 的數值 ——
        游標標籤會同時顯示「帳面每股」與「普通股每股」,兩者相減就是求償權吃掉的部分。
        下面那張美元計價的圖完全看不出這件事,因為求償權與資產同時以美元計價,
        比例變化被價格漲跌蓋掉了。
      </div>

      <div class="grid2" style="margin-top:30px">
        <div>
          <h3 style="margin-bottom:8px">為什麼「多買幣」不一定對股東有利</h3>
          <p style="font-size:.9rem;color:var(--ink-2);margin:0">
            用發優先股募到的錢買幣,總持幣上升,帳面每股也跟著上升,
            看起來像在替股東累積比特幣。但同一筆交易等量增加了排在普通股前面的求償權,
            扣掉之後普通股一顆都沒多拿到 —— 這就是 phantom growth。
            真正會讓 CEBE 上升的只有三種:以高於淨值的價格增發普通股、
            以折價回購優先股或可轉債、或可轉債轉股讓求償權直接消失。</p>
        </div>
        <div>
          <h3 style="margin-bottom:8px">為什麼求償權會自己縮小</h3>
          <p style="font-size:.9rem;color:var(--ink-2);margin:0">
            求償權的面額固定在美元,所以 BTC 一漲,它在幣計價下就縮小,
            CEBE 不用多買一顆就會自己長回來。這個效果有多大、在什麼價位會反轉,
            <a href="#/pricing">槓桿與定價</a>那一頁用同一份資料算給你看。</p>
        </div>
      </div>

      <p style="font-size:.8rem;color:var(--ink-3);margin-top:22px">
        堆疊方式:現金抵減最優先的可轉債層,其餘各優先股系列依清償順位往上疊,
        頂端是普通股殘量,總和精確等於當日總持有量(黑線)。</p>
    </div>`;

  return explorer(root.querySelector<HTMLElement>("#explorer")!, {
    charts: ["perShare", "riverBtc", "riverUsd"], showIdentity: false,
  });
};
