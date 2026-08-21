import { daily, meta, N } from "../data";
import { explorer } from "../components/explorer";
import { btc as fmtBtc, pct } from "../lib/format";
import { rangeIndices } from "../lib/range";
import type { PageFn } from "../router";

export const structurePage: PageFn = (root) => {
  // 對比窗口跟著資料走:永遠是「約一年前 → 最新一天」,
  // 每次資料更新這一頁的頭條數字就會跟著動,不會卡在建置當下的舊快照。
  const [a, b] = rangeIndices("1y");
  const i = N - 1;

  const perShareOf = (k: number) =>
    (daily.common_btc[k]! / (daily.shares[k]! * 1e6)) * 1e8;
  const d = (x: number, y: number) => ((y / x - 1) * 100);
  const sign = (v: number) => (v >= 0 ? "+" : "") + v.toFixed(1) + "%";

  const dHeld = d(daily.held[a]!, daily.held[b]!);
  const dCommon = d(daily.common_btc[a]!, daily.common_btc[b]!);
  const dShares = d(daily.shares[a]!, daily.shares[b]!);
  const dPerShare = d(perShareOf(a), perShareOf(b));
  const dGross = d(daily.bps[a]!, daily.bps[b]!);

  const grossNow = daily.bps[i]!;
  const cebeNow = perShareOf(i);
  const eatenNow = grossNow - cebeNow;

  root.innerHTML = `
    <div class="wrap">
      <div class="page-head">
        <p class="eyebrow">資本結構</p>
        <h1>帳面每股在漲,實際每股在縮</h1>
        <p class="lede">求償權的面額鎖死在美元,普通股拿的是殘值。
          公司報的「每股持幣」是把總持幣除以股數,看起來一路成長;
          但把求償權扣掉、再算進股數的擴張,單一股東實際能分到的比特幣是<b>減少</b>的。
          這一頁就是把這兩個數字擺在一起。</p>
      </div>

      <div class="grid3" style="margin-bottom:14px">
        <div class="tile"><div class="k">帳面每股持幣(basic 股數)</div>
          <div class="v" style="color:var(--good)">${sign(dGross)}</div>
          <div class="d">${Math.round(daily.bps[a]!).toLocaleString()} → ${Math.round(daily.bps[b]!).toLocaleString()} sats<br>總持幣 ÷ basic 股數,不扣求償權、不算可轉債稀釋</div></div>
        <div class="tile" style="border-left:3px solid var(--equity)">
          <div class="k">實際每股持幣(CEBE)</div>
          <div class="v" style="color:var(--bad)">${sign(dPerShare)}</div>
          <div class="d">${Math.round(perShareOf(a)).toLocaleString()} → ${Math.round(perShareOf(b)).toLocaleString()} sats<br>扣求償權後,才是股東的</div></div>
        <div class="tile"><div class="k">在外股數</div>
          <div class="v">${sign(dShares)}</div>
          <div class="d">${daily.shares[a]!.toFixed(0)}M → ${daily.shares[b]!.toFixed(0)}M<br>增發也在稀釋每股</div></div>
        <div class="tile"><div class="k">公司多買了</div>
          <div class="v">${sign(dHeld)}</div>
          <div class="d">${fmtBtc(daily.held[a]!)} → ${fmtBtc(daily.held[b]!)} 顆<br>${daily.date[a]!} → ${daily.date[b]!}</div></div>
      </div>

      <div class="note key" style="margin-bottom:26px">
        <b>同一段期間,兩個數字方向相反。</b>
        公司多買了 ${fmtBtc(daily.held[b]! - daily.held[a]!)} 顆幣,帳面每股持幣因此 ${sign(dGross)};
        但求償權在幣計價下膨脹、股數又增加了 ${sign(dShares)},
        兩者夾殺之下,股東實際能分到的每股比特幣是 <b>${sign(dPerShare)}</b>。
        總量看起來只是「原地踏步」(${sign(dCommon)}),但那是還沒除以股數 ——
        分母變大了三成,個別股東的處境比總量更差。
      </div>

      <h2 style="margin-bottom:8px">CEBE 是什麼</h2>
      <p class="lede" style="margin-bottom:18px">
        CEBE(Common Equity Bitcoin Exposure)就是<b>扣掉所有優先求償權之後,每股真正對應到的比特幣</b>。
        下面那張 BTC 計價的圖直接把它畫出來:堆疊的下半部是求償權吃掉的幣,
        最上面那條橘色帶子才是普通股的 —— 按「每股」鈕就會把整張圖除以在外股數,
        頂端帶子的厚度就是 CEBE。
      </p>

      <div class="grid3" style="margin-bottom:10px">
        <div class="tile"><div class="k">帳面每股(basic 股數)</div>
          <div class="v">${Math.round(grossNow).toLocaleString()}</div>
          <div class="d">sats。總持幣 ÷ basic 股數,不含可轉債稀釋</div></div>
        <div class="tile"><div class="k">求償權吃掉</div>
          <div class="v" style="color:var(--bad)">−${Math.round(eatenNow).toLocaleString()}</div>
          <div class="d">sats,佔帳面的 ${pct(eatenNow / grossNow)}</div></div>
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
          <h3 style="margin-bottom:8px">為什麼帳面會漲、實際會縮</h3>
          <p style="font-size:.9rem;color:var(--ink-2);margin:0">
            優先股募來的錢拿去買幣,總持幣上升,帳面每股(basic 股數)也跟著上升,
            看起來像在替股東累積比特幣。但同一筆交易等量增加了排在普通股前面的求償權,
            扣掉之後普通股一顆都沒多拿到 —— 這就是 phantom growth。
            真正會讓 CEBE 上升的只有三種:以高於淨值的價格增發普通股、
            以折價回購優先股、或可轉債轉股讓求償權直接消失。</p>
        </div>
        <div>
          <h3 style="margin-bottom:8px">那這些幣是白買的嗎</h3>
          <p style="font-size:.9rem;color:var(--ink-2);margin:0">
            不是。買進來的幣換到的是<b>槓桿</b>。求償權的面額固定在美元,
            所以 BTC 一漲,它在幣計價下就縮小,CEBE 不用多買一顆就會自己長回來。
            現在的低點其實是槓桿在蓄力 —— 這個反轉有多大,
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
