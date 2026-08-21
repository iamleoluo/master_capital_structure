/** 三張共用同一時間索引的日頻圖:價格、mNAV、USD 河流。
 *  都吃 state.idx,游標標籤由 lib/crosshair 統一渲染。 */
import { daily, meta, N } from "../data";
import { state } from "../state";
import { crosshair, type SeriesLabel } from "../lib/crosshair";
import { axisX, breakLines, CW, frame, gridY, PAD_R } from "../lib/frame";
import { bn, mult, sats, usd, usd0 } from "../lib/format";
import { extent, linear, log } from "../lib/scale";
import { band, line, path, svg, text } from "../lib/svg";

type Geo = { y: ReturnType<typeof log>; extra?: unknown };

// --------------------------------------------------------------- 價格
export function drawPrice(el: HTMLElement, h = 190, range?: [number, number]): Geo & { idx: number[][] } {
  const [lo, hi] = range ?? [0, N - 1];
  const f = frame(h, 16, 24, range);
  const b0 = daily.btc[0]!, m0 = daily.mstr[0]!;
  const bi = daily.btc.map((v) => (v / b0) * 100);
  const mi = daily.mstr.map((v) => (v / m0) * 100);
  const [ylo, yhi] = extent(bi.slice(lo, hi + 1).concat(mi.slice(lo, hi + 1)), 0.85, 1.12);
  const y = log([ylo, yhi], [f.plotBottom, f.plotTop]);
  const pts = (arr: number[]) => {
    const out: Array<[number, number]> = [];
    for (let i = lo; i <= hi; i++) out.push([f.x(i), y(arr[i]!)]);
    return out;
  };

  const parts = [
    line(56, y(100), CW - PAD_R, y(100), { opacity: 0.18 }),
    text(49, y(100) + 3.5, "100", { size: 9, anchor: "end", opacity: 0.5, mono: true }),
    axisX(f),
    `<path d="${path(pts(bi))}" fill="none" stroke="var(--btc)" stroke-width="1.5" opacity=".85"/>`,
    `<path d="${path(pts(mi))}" fill="none" stroke="var(--senti)" stroke-width="1.8"/>`,
    text(CW - PAD_R, y(bi[hi]!) + 3, "BTC", { size: 10, anchor: "end", fill: "var(--btc)", weight: 600 }),
    text(CW - PAD_R, y(mi[hi]!) - 6, "MSTR", { size: 10, anchor: "end", fill: "var(--senti)", weight: 600 }),
  ];
  el.innerHTML = svg(CW, h, parts.join(""), "MSTR 與 BTC 同基期指數化價格,對數座標");
  return { y, idx: [bi, mi] };
}

export function priceLabels(g: { y: ReturnType<typeof log>; idx: number[][] }, i: number): SeriesLabel[] {
  return [
    { label: "MSTR", value: usd(daily.mstr[i]!), color: "var(--senti)", y: g.y(g.idx[1]![i]!) },
    { label: "BTC", value: usd0(daily.btc[i]!), color: "var(--btc)", y: g.y(g.idx[0]![i]!) },
  ];
}

// --------------------------------------------------------------- mNAV
export function drawMnav(el: HTMLElement, h = 190, range?: [number, number]): Geo {
  const [lo, hi] = range ?? [0, N - 1];
  const f = frame(h, 16, 24, range);
  const [ylo, yhi] = extent(
    daily.mnav_basic.slice(lo, hi + 1).concat(daily.mnav_cebe.slice(lo, hi + 1)), 0.85, 1.15);
  const y = log([ylo, yhi], [f.plotBottom, f.plotTop]);
  const pts = (arr: number[]) => {
    const out: Array<[number, number]> = [];
    for (let i = lo; i <= hi; i++) out.push([f.x(i), y(arr[i]!)]);
    return out;
  };

  const parts = [
    line(56, y(1), CW - PAD_R, y(1), { opacity: 0.3, dash: "2,2" }),
    text(49, y(1) + 3.5, "1.0x", { size: 9, anchor: "end", opacity: 0.55, mono: true }),
    axisX(f),
    breakLines(f, meta.breaks),
    `<path d="${path(pts(daily.mnav_basic))}" fill="none" stroke="var(--c3)" stroke-width="1.5" opacity=".85"/>`,
    `<path d="${path(pts(daily.mnav_cebe))}" fill="none" stroke="var(--equity)" stroke-width="1.8"/>`,
    text(CW - PAD_R, y(daily.mnav_basic[hi]!) + 13, "basic", { size: 10, anchor: "end", fill: "var(--c3)", weight: 600 }),
    text(CW - PAD_R, y(daily.mnav_cebe[hi]!) - 6, "CEBE", { size: 10, anchor: "end", fill: "var(--equity)", weight: 600 }),
  ];
  el.innerHTML = svg(CW, h, parts.join(""), "basic mNAV 與 CEBE mNAV,對數座標,1.0x 為參考線");
  return { y };
}

export function mnavLabels(g: Geo, i: number): SeriesLabel[] {
  return [
    { label: "CEBE mNAV", value: mult(daily.mnav_cebe[i]!), color: "var(--equity)", y: g.y(daily.mnav_cebe[i]!) },
    { label: "basic mNAV", value: mult(daily.mnav_basic[i]!), color: "var(--c3)", y: g.y(daily.mnav_basic[i]!) },
  ];
}

// --------------------------------------------------------------- 每股 BTC(帳面 vs CEBE)
const cebePerShare = (i: number): number => (daily.common_btc[i]! / (daily.shares[i]! * 1e6)) * 1e8;

export interface PerShareGeo {
  y: ReturnType<typeof log>; yBtc: ReturnType<typeof log>; yMstr: ReturnType<typeof log>;
}

export function drawPerShare(el: HTMLElement, h = 190, range?: [number, number]): PerShareGeo {
  const [lo, hi] = range ?? [0, N - 1];
  const f = frame(h, 16, 24, range);
  const cebe = daily.date.map((_, i) => cebePerShare(i));
  const [ylo, yhi] = extent(daily.bps.slice(lo, hi + 1).concat(cebe.slice(lo, hi + 1)), 0.9, 1.1);
  const y = log([ylo, yhi], [f.plotBottom, f.plotTop]);

  // BTC/MSTR 價格只是參考線,各自獨立的對數尺度(單位、量級都不一樣,
  // 疊在同一張圖上只看得出走勢方向與轉折,精確數值靠游標讀)。
  const [blo, bhi] = extent(daily.btc.slice(lo, hi + 1), 0.85, 1.15);
  const yBtc = log([blo, bhi], [f.plotBottom, f.plotTop]);
  const [mlo, mhi] = extent(daily.mstr.slice(lo, hi + 1), 0.85, 1.15);
  const yMstr = log([mlo, mhi], [f.plotBottom, f.plotTop]);

  const pts = (arr: number[], scale: ReturnType<typeof log>) => {
    const out: Array<[number, number]> = [];
    for (let i = lo; i <= hi; i++) out.push([f.x(i), scale(arr[i]!)]);
    return out;
  };

  const parts = [
    axisX(f),
    breakLines(f, meta.breaks),
    `<path d="${path(pts(daily.btc, yBtc))}" fill="none" stroke="var(--btc)" stroke-width="1.2" stroke-dasharray="3,3" opacity=".4"/>`,
    `<path d="${path(pts(daily.mstr, yMstr))}" fill="none" stroke="var(--senti)" stroke-width="1.2" stroke-dasharray="3,3" opacity=".4"/>`,
    `<path d="${path(pts(daily.bps, y))}" fill="none" stroke="var(--c3)" stroke-width="1.5" opacity=".85"/>`,
    `<path d="${path(pts(cebe, y))}" fill="none" stroke="var(--equity)" stroke-width="1.8"/>`,
    text(f.x(lo) + 4, yBtc(daily.btc[lo]!) - 5, "BTC 價格(參考)", { size: 9, anchor: "start", fill: "var(--btc)", opacity: 0.7 }),
    text(f.x(lo) + 4, yMstr(daily.mstr[lo]!) + 12, "MSTR 股價(參考)", { size: 9, anchor: "start", fill: "var(--senti)", opacity: 0.7 }),
    text(CW - PAD_R, y(daily.bps[hi]!) + 13, "帳面(basic 股數)", { size: 10, anchor: "end", fill: "var(--c3)", weight: 600 }),
    text(CW - PAD_R, y(cebe[hi]!) - 6, "CEBE", { size: 10, anchor: "end", fill: "var(--equity)", weight: 600 }),
  ];

  // 官方揭露的 Gross BPS(用假設稀釋股數,而非 basic 股數)—— 只有最新一期
  // FWP 敏感度表這一個真實錨點,沒有歷史序列,所以畫成單點,不是連續線,
  // 避免假裝有一條「官方歷史曲線」其實是編出來的。
  if (N - 1 >= lo && N - 1 <= hi) {
    const fx = f.x(N - 1), fy = y(meta.fwp.gross_bps);
    parts.push(`<circle cx="${fx.toFixed(1)}" cy="${fy.toFixed(1)}" r="4" fill="var(--paper)" stroke="var(--c1)" stroke-width="2"/>`);
    parts.push(text(fx - 8, fy - 9, `官方 Gross BPS ${meta.fwp.gross_bps.toLocaleString()}(假設稀釋股數)`,
      { size: 9, anchor: "end", fill: "var(--c1)", weight: 600 }));
  }

  el.innerHTML = svg(CW, h, parts.join(""),
    "帳面每股持幣(basic 股數)vs 實際每股持幣(CEBE),對數座標,單位 sats;虛線為 BTC 與 MSTR 價格參考;" +
    "圓點為官方揭露的 Gross BPS(假設稀釋股數口徑,僅最新一期 FWP 有此數字)");
  return { y, yBtc, yMstr };
}

export function perShareLabels(g: PerShareGeo, i: number): SeriesLabel[] {
  const cebe = cebePerShare(i);
  return [
    { label: "CEBE 每股", value: sats(cebe), color: "var(--equity)", y: g.y(cebe) },
    { label: "帳面每股", value: sats(daily.bps[i]!), color: "var(--c3)", y: g.y(daily.bps[i]!) },
    { label: "BTC 價格", value: usd0(daily.btc[i]!), color: "var(--btc)", y: g.yBtc(daily.btc[i]!) },
    { label: "MSTR 股價", value: usd(daily.mstr[i]!), color: "var(--senti)", y: g.yMstr(daily.mstr[i]!) },
  ];
}

// --------------------------------------------------------------- USD 河流
const USD_LAYERS = [
  { key: "strf_lp", color: "var(--c1)" }, { key: "strc_lp", color: "var(--c2)" },
  { key: "strk_lp", color: "var(--c3)" }, { key: "strd_lp", color: "var(--c4)" },
  { key: "stre_lp", color: "var(--c5)" },
] as const;

export interface RiverUsdGeo {
  y: ReturnType<typeof linear>; claimsTop: number[]; stackTop: number[]; nav: number[];
}

export function drawRiverUsd(el: HTMLElement, h = 210, range?: [number, number]): RiverUsdGeo {
  const [lo, hi] = range ?? [0, N - 1];
  const f = frame(h, 18, 26, range);
  const claimsTop: number[] = [], stackTop: number[] = [], nav: number[] = [];
  const layerTops: number[][] = [];

  for (let i = 0; i < N; i++) {
    let acc = daily.debt[i]!;
    const tops: number[] = [];
    for (const l of USD_LAYERS) { acc += (daily[l.key] as number[])[i]!; tops.push(acc); }
    layerTops.push(tops);
    claimsTop.push(acc);
    stackTop.push(acc + (daily.mstr[i]! * daily.shares[i]!) / 1000);
    nav.push((daily.held[i]! * daily.btc[i]!) / 1e9);
  }

  const maxV = Math.max(...stackTop.slice(lo, hi + 1), ...nav.slice(lo, hi + 1)) * 1.07;
  const y = linear([0, maxV], [f.plotBottom, f.plotTop]);
  const px = (i: number) => f.x(i);
  const parts: string[] = [gridY(y, [0, maxV / 3, (maxV * 2) / 3, maxV], (v) => "$" + v.toFixed(0) + "B"), axisX(f)];

  const zero: Array<[number, number]> = [];
  for (let i = lo; i <= hi; i++) zero.push([px(i), y(0)]);
  const debtTop: Array<[number, number]> = [];
  for (let i = lo; i <= hi; i++) debtTop.push([px(i), y(daily.debt[i]!)]);
  parts.push(`<path d="${band(debtTop, zero)}" fill="var(--convert)" opacity=".9"/>`);

  let prev = debtTop;
  USD_LAYERS.forEach((l, li) => {
    const top: Array<[number, number]> = [];
    for (let i = lo; i <= hi; i++) top.push([px(i), y(layerTops[i]![li]!)]);
    parts.push(`<path d="${band(top, prev)}" fill="${l.color}" opacity=".92"/>`);
    prev = top;
  });

  const stack: Array<[number, number]> = [];
  for (let i = lo; i <= hi; i++) stack.push([px(i), y(stackTop[i]!)]);
  parts.push(`<path d="${band(stack, prev)}" fill="var(--equity)" opacity=".5"/>`);

  // 溢價/折價:堆疊頂與 BTC NAV 之間,依正負分色
  const navPts: Array<[number, number]> = [];
  for (let i = lo; i <= hi; i++) navPts.push([px(i), y(nav[i]!)]);
  let run: number[] = [], sign = stackTop[lo]! >= nav[lo]!;
  const flush = () => {
    if (run.length < 2) return;
    const t = run.map((i) => [px(i), y(stackTop[i]!)] as [number, number]);
    const b = run.map((i) => [px(i), y(nav[i]!)] as [number, number]);
    parts.push(`<path d="${band(t, b)}" fill="${sign ? "var(--good)" : "var(--bad)"}" opacity=".35"/>`);
  };
  for (let i = lo; i <= hi; i++) {
    const s = stackTop[i]! >= nav[i]!;
    if (s !== sign) { flush(); run = [i - 1 >= lo ? i - 1 : i]; sign = s; }
    run.push(i);
  }
  flush();

  parts.push(`<path d="${path(navPts)}" fill="none" stroke="var(--btc)" stroke-width="1.6" stroke-dasharray="4,3"/>`);
  parts.push(breakLines(f, meta.breaks));
  parts.push(text(CW - PAD_R, y(nav[hi]!) - 6, "BTC 總市值", { size: 10, anchor: "end", fill: "var(--btc)", weight: 600 }));

  el.innerHTML = svg(CW, h, parts.join(""), "美元計價的資本結構河流圖,求償權堆疊加上 MSTR 市值,虛線為 BTC 總市值");
  return { y, claimsTop, stackTop, nav };
}

export function riverUsdLabels(g: RiverUsdGeo, i: number): SeriesLabel[] {
  const mcap = (daily.mstr[i]! * daily.shares[i]!) / 1000;
  return [
    { label: "BTC 總市值", value: bn(g.nav[i]!), color: "var(--btc)", y: g.y(g.nav[i]!) },
    { label: "股+求償權", value: bn(g.stackTop[i]!), color: "var(--equity)", y: g.y(g.stackTop[i]!) },
    { label: "MSTR 市值", value: bn(mcap), color: "var(--senti)", y: g.y(g.claimsTop[i]! + mcap / 2) },
    { label: "求償權", value: bn(g.claimsTop[i]!), color: "var(--c2)", y: g.y(g.claimsTop[i]! / 2) },
  ];
}

/** 通用:把標籤組渲染成游標圖層並塞進既有 SVG。 */
export function overlay(el: HTMLElement, labels: SeriesLabel[], h: number,
                        padT = 16, padB = 24, range?: [number, number]): void {
  const f = frame(h, padT, padB, range);
  const i = state.idx;
  const svgEl = el.querySelector("svg");
  if (!svgEl) return;
  svgEl.querySelector(".crosshair")?.remove();
  svgEl.insertAdjacentHTML("beforeend", crosshair(labels, {
    x: f.x(i), plotTop: f.plotTop, plotBottom: f.plotBottom,
    chartWidth: CW, header: daily.date[i]!,
  }));
}
