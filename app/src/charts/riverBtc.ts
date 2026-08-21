/** BTC 計價的資本結構河流圖。
 *
 * 這是整個專案最有說服力的一張:縱軸換成「幣的顆數」而非美元。
 * 求償權的面額固定在美元,所以 BTC 一跌,同一筆求償權就吃掉更多顆幣 ——
 * 公司一直在買幣,但普通股實際分到的量幾乎不動。
 *
 * 堆疊總和精確等於當日總持有量:
 *   淨可轉債 = max(0, (debt − cash) / btc_price)   ← 現金抵減最優先層
 *   各優先股 = lp_usd / btc_price
 *   普通股   = held − 上述總和
 * 現金抵在可轉債層,與 ClaimsBasis.CEBETRACKER 的定義一致,
 * 也讓堆疊剛好收斂到 held(否則會多算或少算一塊)。
 */
import { daily, meta, N } from "../data";
import type { SeriesLabel } from "../lib/crosshair";
import { axisX, breakLines, CW, frame, gridY, PAD_R } from "../lib/frame";
import { btc as fmtBtc, usd0 } from "../lib/format";
import { extent, linear } from "../lib/scale";
import { band, path, svg, text } from "../lib/svg";

const LAYERS: Array<{ key: keyof typeof daily; label: string; color: string }> = [
  { key: "strf_lp", label: "STRF", color: "var(--c1)" },
  { key: "strc_lp", label: "STRC", color: "var(--c2)" },
  { key: "strk_lp", label: "STRK", color: "var(--c3)" },
  { key: "strd_lp", label: "STRD", color: "var(--c4)" },
  { key: "stre_lp", label: "STRE", color: "var(--c5)" },
];

export interface RiverBtcGeo {
  netDebt: number[]; layerTops: number[][]; claimsTop: number[]; held: number[];
  y: ReturnType<typeof linear>;
  yBtc: ReturnType<typeof linear>;
  perShare: boolean;
}

/** per-share 模式的意義:總量看不出股數擴張。
 *  普通股總量幾乎沒變,但股數同期 +30%,所以每股實際是縮水的 —— 
 *  這才是單一股東真正感受到的稀釋。 */
function scaleOf(i: number, perShare: boolean): number {
  return perShare ? 1e8 / (daily.shares[i]! * 1e6) : 1;
}

export function computeRiverBtc(perShare = false): RiverBtcGeo {
  const netDebt: number[] = [];
  const claimsTop: number[] = [];
  const layerTops: number[][] = [];
  const held = daily.held;

  const scaledHeld: number[] = [];
  for (let i = 0; i < N; i++) {
    const px = daily.btc[i]!;
    const k = scaleOf(i, perShare);
    const nd = Math.max(0, ((daily.debt[i]! - daily.cash[i]!) * 1e9) / px) * k;
    let acc = nd;
    const tops: number[] = [];
    for (const l of LAYERS) {
      acc += (((daily[l.key] as number[])[i]! * 1e9) / px) * k;
      tops.push(acc);
    }
    netDebt.push(nd);
    layerTops.push(tops);
    claimsTop.push(acc);
    scaledHeld.push(held[i]! * k);
  }
  return { netDebt, layerTops, claimsTop, held: scaledHeld,
           y: linear([0, 1], [0, 1]), yBtc: linear([0, 1], [0, 1]), perShare };
}

export function drawRiverBtc(el: HTMLElement, h = 300, perShare = false, range?: [number, number]): RiverBtcGeo {
  const [lo, hi] = range ?? [0, N - 1];
  const f = frame(h, 18, 26, range);
  const g = computeRiverBtc(perShare);
  const maxV = Math.max(...g.held.slice(lo, hi + 1)) * 1.06;
  const y = linear([0, maxV], [f.plotBottom, f.plotTop]);
  g.y = y;

  // BTC 價格參考線,獨立尺度(只看走勢與轉折,精確數值靠游標讀)。
  const [blo, bhi] = extent(daily.btc.slice(lo, hi + 1), 0.85, 1.15);
  const yBtc = linear([blo, bhi], [f.plotBottom, f.plotTop]);
  g.yBtc = yBtc;

  const px = (i: number) => f.x(i);
  const parts: string[] = [];

  parts.push(gridY(y, [0, maxV / 3, (maxV * 2) / 3, maxV],
    (v) => perShare ? Math.round(v).toLocaleString() : (v / 1000).toFixed(0) + "K"));
  parts.push(axisX(f));

  // 由下往上堆疊求償權
  const zero: Array<[number, number]> = [];
  for (let i = lo; i <= hi; i++) zero.push([px(i), y(0)]);

  const debtTop: Array<[number, number]> = [];
  for (let i = lo; i <= hi; i++) debtTop.push([px(i), y(g.netDebt[i]!)]);
  parts.push(`<path d="${band(debtTop, zero)}" fill="var(--convert)" opacity=".9"/>`);

  let prev = debtTop;
  LAYERS.forEach((l, li) => {
    const top: Array<[number, number]> = [];
    for (let i = lo; i <= hi; i++) top.push([px(i), y(g.layerTops[i]![li]!)]);
    parts.push(`<path d="${band(top, prev)}" fill="${l.color}" opacity=".92"/>`);
    prev = top;
  });

  // 普通股殘量 —— 求償權之上到總持有量之間
  const heldTop: Array<[number, number]> = [];
  for (let i = lo; i <= hi; i++) heldTop.push([px(i), y(g.held[i]!)]);
  parts.push(`<path d="${band(heldTop, prev)}" fill="var(--equity)" opacity=".62"/>`);

  // 總持有量線壓在最上緣
  parts.push(`<path d="${path(heldTop)}" fill="none" stroke="var(--ink)" stroke-width="1.6"/>`);

  parts.push(breakLines(f, meta.breaks));

  // BTC 價格參考線 —— 標籤放左側起點,避免跟右側原有的堆疊標籤擠在一起
  const btcPts: Array<[number, number]> = [];
  for (let i = lo; i <= hi; i++) btcPts.push([px(i), yBtc(daily.btc[i]!)]);
  parts.push(`<path d="${path(btcPts)}" fill="none" stroke="var(--btc)" stroke-width="1.2" stroke-dasharray="3,3" opacity=".4"/>`);
  parts.push(text(px(lo) + 4, yBtc(daily.btc[lo]!) - 5, "BTC 價格(參考)",
    { size: 9, anchor: "start", fill: "var(--btc)", opacity: 0.7 }));

  const last = hi;
  parts.push(text(CW - PAD_R, y(g.held[last]!) - 7, perShare ? "帳面每股" : "總持有量",
    { size: 10, anchor: "end", weight: 600 }));
  const midCommon = (y(g.claimsTop[last]!) + y(g.held[last]!)) / 2;
  parts.push(text(CW - PAD_R, midCommon + 3, "普通股",
    { size: 10, anchor: "end", fill: "var(--equity)", weight: 600 }));

  el.innerHTML = svg(CW, h, parts.join(""),
    perShare
      ? "以每股 sats 計價的資本結構河流圖,求償權堆疊在下,普通股每股殘量在上,虛線為 BTC 價格參考"
      : "以 BTC 顆數計價的資本結構河流圖,求償權堆疊在下,普通股殘量在上,總和等於總持有量,虛線為 BTC 價格參考");
  return g;
}

/** 給游標圖層用的標籤。 */
export function riverBtcLabels(g: RiverBtcGeo, i: number): SeriesLabel[] {
  const common = g.held[i]! - g.claimsTop[i]!;
  const fmt = (v: number) => g.perShare
    ? Math.round(v).toLocaleString() + " sats" : fmtBtc(v);
  return [
    { label: g.perShare ? "帳面每股" : "總持有", value: fmt(g.held[i]!),
      color: "var(--ink)", y: g.y(g.held[i]!) },
    { label: g.perShare ? "普通股每股" : "普通股", value: fmt(common),
      color: "var(--equity)", y: g.y((g.claimsTop[i]! + g.held[i]!) / 2) },
    { label: "求償權", value: fmt(g.claimsTop[i]!),
      color: "var(--c2)", y: g.y(g.claimsTop[i]! / 2) },
    { label: "BTC 價格", value: usd0(daily.btc[i]!),
      color: "var(--btc)", y: g.yBtc(daily.btc[i]!) },
  ];
}




