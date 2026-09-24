/** 符號表 —— 全站唯一的定義來源。
 *
 *  「資本結構 · 求償權與殘值」用結構量那一組,「資本操作」再加上操作量那一組。
 *  同一個符號在兩頁一定是同一個意思,所以定義只寫一次,由各頁挑要顯示哪幾個。 */
import { tex, texBlock } from "../lib/math";

interface Sym { name: string; unit: string; def: string }

const SYMBOLS: Record<string, Sym> = {
  // 結構量 —— 描述「現在長什麼樣」
  H: { name: "總持幣", unit: "BTC", def: "公司帳上全部的比特幣,8-K 逐週揭露" },
  S: { name: "在外股數", unit: "股", def: "普通股 basic 股數,不含可轉債假設轉股" },
  C: { name: "求償權", unit: "USD", def: "排在普通股前面、面額鎖死在美元的部分" },
  p: { name: "比特幣價格", unit: "USD", def: "當下的幣價" },
  B: { name: "帳面每股含幣量", unit: "sats", def: "Gross BPS,也就是公司的 BTC Yield" },
  E: { name: "實得每股含幣量", unit: "sats", def: "CEBE,扣掉求償權後每股真正對應到的幣" },
  m: { name: "市場溢價", unit: "倍", def: "CEBE mNAV,市場願意付幾倍的每股殘值" },
  P: { name: "MSTR 股價", unit: "USD", def: "普通股市價;增發或回購時即成交價" },
  // 操作量 —— 描述「這一筆動作有多大」
  // 這五個都是「量」,方向由式子裡的正負號決定,不由符號本身承擔。
  // 先前寫成「買回或發行的面額」像是在列兩個相反的動作,反而看不懂。
  c: { name: "美元金額", unit: "USD",
       def: "這筆操作經手的現金。發行是<b>募到</b>這麼多,回購或買幣是<b>付出</b>這麼多" },
  F: { name: "面額", unit: "USD",
       def: "優先股的清算優先權(或可轉債本金)金額。發行是<b>掛上</b>這筆面額,"
            + "回購是<b>消滅</b>這筆面額 —— 兩者都以面額計,與成交價 c 無關" },
  n: { name: "普通股股數", unit: "股",
       def: "這筆操作動到的普通股股數。ATM 是增發,庫藏是回購" },
  x: { name: "比特幣顆數", unit: "BTC", def: "這筆操作買進或賣出的幣" },
  d: { name: "折價率", unit: "—",
       def: "回購時成交價低於面額的幅度,d = 1 − c/F。面額 $100 買在 $73 就是 d = 0.27" },
};

/** 挑幾個符號排成表。keys 的順序就是顯示順序。 */
export function symbolTable(keys: string[]): string {
  return `<div class="symbols">${keys.map((k) => {
    const s = SYMBOLS[k];
    if (!s) throw new Error(`symbols: 沒有定義 ${k}`);
    return `
      <div class="symbol">${tex(k)}
        <div class="symbol-def"><b>${s.name}</b><span class="symbol-unit">${
          s.unit}</span><br>${s.def}</div>
      </div>`;
  }).join("")}</div>`;
}

/** 兩個每股指標的式子。工具與組合的代數全部拿它們當基準,
 *  所以哪一頁用到那些代數,這兩行就要在同一頁看得到。 */
export function perShareDefs(): string {
  return `
    <div class="pershare-defs">
      <div class="pershare-def">
        <div class="pershare-lab">帳面每股含幣量<span>沒有幣價、沒有求償權</span></div>
        ${texBlock("B = \\frac{H}{S}\\times 10^{8}")}
      </div>
      <div class="pershare-def key">
        <div class="pershare-lab">實得每股含幣量<span>扣掉求償權之後</span></div>
        ${texBlock("E = \\frac{\\,H - C/p\\,}{S}\\times 10^{8}")}
      </div>
    </div>`;
}
