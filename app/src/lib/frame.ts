/** 時間軸圖表的共用骨架:座標系、格線、月份刻度、拖曳。 */
import { daily, N } from "../data";
import { setIndex } from "../state";
import { line, text } from "./svg";
import type { Scale } from "./scale";

export const CW = 880;          // SVG 內部座標寬(實際由 CSS 縮放)
export const PAD_L = 56;
export const PAD_R = 16;

export interface Frame {
  w: number; h: number;
  padT: number; padB: number;
  plotTop: number; plotBottom: number;
  /** 目前顯示的資料索引區間(含頭尾)。預設是全部。 */
  lo: number; hi: number;
  x(i: number): number;
  /** 螢幕像素 → 資料索引 */
  indexAt(px: number, elWidth: number): number;
}

/** range 省略時等同全部資料([0, N-1])。放大燈箱的範圍篩選用 range 縮小視窗 ——
 *  終點恆為 N-1(所有範圍都是「往回抓 X」,不是任意區間),所以只有 lo 會變。 */
export function frame(h: number, padT = 16, padB = 24, range?: [number, number]): Frame {
  const [lo, hi] = range ?? [0, N - 1];
  const span = Math.max(1, hi - lo);
  const plotW = CW - PAD_L - PAD_R;
  return {
    w: CW, h, padT, padB, lo, hi,
    plotTop: padT,
    plotBottom: h - padB,
    x: (i) => PAD_L + (plotW * (i - lo)) / span,
    indexAt: (px, elWidth) => {
      const svgX = (px / elWidth) * CW;
      const frac = (svgX - PAD_L) / plotW;
      return Math.max(lo, Math.min(hi, Math.round(lo + frac * span)));
    },
  };
}

/** 水平格線 + 左側刻度標籤。 */
export function gridY(y: Scale, values: number[],
                      fmt: (v: number) => string): string {
  return values.map((v) => {
    const gy = y(v);
    return line(PAD_L, gy, CW - PAD_R, gy, { opacity: 0.08 })
      + text(PAD_L - 7, gy + 3.5, fmt(v),
             { size: 9, anchor: "end", opacity: 0.55, mono: true });
  }).join("");
}

/** 月份/週刻度,密度依可視範圍的天數自動調整 —— 兩年的範圍每半年標一次會
 *  糊成一團,一個月的範圍每半年標一次則整張圖可能一條刻度線都沒有。 */
export function axisX(f: Frame): string {
  const spanDays = f.hi - f.lo;
  const out: string[] = [];

  if (spanDays > 420) {
    // 超過 14 個月:每半年(1 月、7 月)
    const seen = new Set<string>();
    for (let i = f.lo; i <= f.hi; i++) {
      const d = daily.date[i]!;
      const ym = d.slice(0, 7), mm = ym.slice(5, 7);
      if (d.slice(8, 10) !== "01" || seen.has(ym)) continue;
      if (mm !== "01" && mm !== "07") continue;
      seen.add(ym);
      out.push(line(f.x(i), f.plotTop, f.x(i), f.plotBottom, { opacity: 0.06 }));
      out.push(text(f.x(i), f.plotBottom + 14, ym,
        { size: 9, anchor: "middle", opacity: 0.5, mono: true }));
    }
  } else if (spanDays > 75) {
    // 3–14 個月:每月初
    const seen = new Set<string>();
    for (let i = f.lo; i <= f.hi; i++) {
      const d = daily.date[i]!;
      const ym = d.slice(0, 7);
      if (d.slice(8, 10) !== "01" || seen.has(ym)) continue;
      seen.add(ym);
      out.push(line(f.x(i), f.plotTop, f.x(i), f.plotBottom, { opacity: 0.06 }));
      out.push(text(f.x(i), f.plotBottom + 14, ym,
        { size: 9, anchor: "middle", opacity: 0.5, mono: true }));
    }
  } else {
    // 3 個月以內:每週一次,標「MM-DD」
    const stepDays = spanDays > 35 ? 14 : 7;
    let lastTick = -Infinity;
    for (let i = f.lo; i <= f.hi; i++) {
      if (i - lastTick < stepDays) continue;
      lastTick = i;
      const d = daily.date[i]!.slice(5);
      out.push(line(f.x(i), f.plotTop, f.x(i), f.plotBottom, { opacity: 0.06 }));
      out.push(text(f.x(i), f.plotBottom + 14, d,
        { size: 9, anchor: "middle", opacity: 0.5, mono: true }));
    }
  }
  return out.join("");
}

/** 政策/定義斷點的垂直註記線,只畫落在可視範圍內的。 */
export function breakLines(f: Frame, breaks: { d: string; hard: boolean }[]): string {
  return breaks.filter((b) => b.hard).map((b) => {
    const i = daily.date.findIndex((d) => d >= b.d);
    if (i < f.lo || i > f.hi) return "";
    return line(f.x(i), f.plotTop, f.x(i), f.plotBottom,
      { stroke: "var(--c1)", dash: "2,3", opacity: 0.7 });
  }).join("");
}

/** 讓元素可拖曳掃描時間軸。回傳解除綁定函式。 */
export function attachScrub(el: HTMLElement, f: Frame): () => void {
  let dragging = false;
  const move = (clientX: number) => {
    const r = el.getBoundingClientRect();
    setIndex(f.indexAt(clientX - r.left, r.width));
  };
  const down = (e: PointerEvent) => {
    dragging = true;
    el.setPointerCapture(e.pointerId);
    move(e.clientX);
  };
  const drag = (e: PointerEvent) => { if (dragging) move(e.clientX); };
  const up = () => { dragging = false; };

  el.addEventListener("pointerdown", down);
  el.addEventListener("pointermove", drag);
  el.addEventListener("pointerup", up);
  el.addEventListener("pointercancel", up);
  return () => {
    el.removeEventListener("pointerdown", down);
    el.removeEventListener("pointermove", drag);
    el.removeEventListener("pointerup", up);
    el.removeEventListener("pointercancel", up);
  };
}
