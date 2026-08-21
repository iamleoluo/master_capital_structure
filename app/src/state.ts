/** 跨頁共用的游標狀態。換頁不重置,回到同一天繼續看。 */
import { N, indexOfDate } from "./data";

type Listener = (idx: number) => void;

const listeners = new Set<Listener>();

export const state = {
  idx: N - 1,
  /** 拆解頁的 A / B 兩個比較錨點 */
  aIdx: 0,
  bIdx: N - 1,
};

export function setIndex(i: number): void {
  const clamped = Math.max(0, Math.min(N - 1, Math.round(i)));
  if (clamped === state.idx) return;
  state.idx = clamped;
  for (const fn of listeners) fn(clamped);
}

/** 訂閱游標變動。回傳取消訂閱函式 —— 換頁時務必呼叫,否則舊圖表會殘留。 */
export function onIndexChange(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function setAnchor(which: "a" | "b", i: number): void {
  if (which === "a") state.aIdx = i;
  else state.bIdx = i;
}

export function jumpToDate(d: string): void {
  setIndex(indexOfDate(d));
}
