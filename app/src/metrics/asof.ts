/** 每個欄位自己的截至日與方法。不讀 daily.stale（那是各欄位裡最舊的那一個）。
 *
 *  持幣用 weekly.json 的階梯。其餘資產負債欄位看日頻數列：
 *  數值沒變是沿用，日斜率一段不變是依日數比例補上，市場報價是當日。
 */
import { daily, weekly } from "../data";
import type { MetricId } from "./registry";
import type { Method } from "./read";

export const METHOD_LABEL: Record<Method, string> = {
  observed: "當日",
  step: "階梯",
  carry: "沿用",
  linear: "比例",
  spliced: "拼接",
  reconstructed: "推得",
  assumed: "假設",
};

export interface Freshness {
  method: Method;
  asOf: string;
  note: string;
  /** 持幣改走階梯後的顯示值。其他欄位是 null，呼叫端用原序列。 */
  value: number | null;
}

const NOTE: Record<Method, string> = {
  observed: "這一列就是觀測日",
  step: "只在揭露日跳動，中間沿用上一筆",
  carry: "沿用上一筆申報，中間沒有補點",
  linear: "兩次申報之間依日數比例補上",
  spliced: "兩段不同定義接在同一條線上",
  reconstructed: "由其他欄位推得，截至日取其中最舊的",
  assumed: "第一筆揭露之前，沒有階梯可沿用",
};

function daysBetween(a: string, b: string): number {
  const ms = Date.parse(a) - Date.parse(b);
  return Math.max(1, Math.round(ms / 86_400_000));
}

interface Seg { start: number; flat: boolean }

function segments(values: number[]): Seg[] {
  const dates = daily.date;
  let max = 0;
  for (const v of values) max = Math.max(max, Math.abs(v));
  const tol = Math.max(max * 5e-5, 1e-4);
  const segs: Seg[] = [];
  let start = 0;
  let slope = 0;
  for (let i = 1; i < values.length; i++) {
    const s = (values[i]! - values[i - 1]!) / daysBetween(dates[i]!, dates[i - 1]!);
    if (i > 1 && Math.abs(s - slope) > tol) {
      segs.push({ start, flat: Math.abs(slope) <= tol });
      start = i - 1;
    }
    slope = s;
  }
  segs.push({ start, flat: Math.abs(slope) <= tol });
  return segs;
}

function indexAt(segs: Seg[], i: number): Seg {
  let hit = segs[0]!;
  for (const s of segs) {
    if (s.start <= i) hit = s;
    else break;
  }
  return hit;
}

function fromSeries(values: number[], i: number, market: boolean): Freshness {
  const dates = daily.date;
  if (market) {
    let j = i;
    while (j > 0 && values[j] === values[j - 1]) j--;
    const method: Method = j === i ? "observed" : "carry";
    return { method, asOf: dates[j]!, note: NOTE[method], value: null };
  }
  const seg = indexAt(segments(values), i);
  if (seg.flat && i === seg.start) {
    return { method: "observed", asOf: dates[i]!, note: NOTE.observed, value: null };
  }
  if (seg.flat) {
    return { method: "carry", asOf: dates[seg.start]!, note: NOTE.carry, value: null };
  }
  if (i === seg.start) {
    return { method: "observed", asOf: dates[i]!, note: NOTE.observed, value: null };
  }
  return { method: "linear", asOf: dates[seg.start]!, note: NOTE.linear, value: null };
}

interface Hold { date: string; value: number }

const holds: Hold[] = weekly
  .filter((w) => w.holdings != null)
  .map((w) => ({ date: w.week_end, value: w.holdings! }))
  .sort((a, b) => a.date < b.date ? -1 : 1);

function heldAt(i: number): Freshness {
  const d = daily.date[i]!;
  let hit: Hold | null = null;
  for (const h of holds) {
    if (h.date <= d) hit = h;
    else break;
  }
  if (!hit) {
    return { method: "assumed", asOf: d, note: NOTE.assumed, value: daily.held[i]! };
  }
  return { method: "step", asOf: hit.date, note: NOTE.step, value: hit.value };
}

const BALANCE: Partial<Record<MetricId, number[]>> = {
  "claims.debt": daily.debt,
  "claims.pref": daily.pref_total,
  "shares.basic": daily.shares,
};

const MARKET: MetricId[] = ["price.mstr", "price.btc"];

const DERIVED: Partial<Record<MetricId, MetricId[]>> = {
  "claims.cebe": ["claims.debt", "claims.pref", "claims.cash"],
  "mnav.basic": ["btc.held", "shares.basic", "price.btc", "price.mstr"],
  "mnav.cebe": ["btc.held", "claims.cebe", "shares.basic", "price.btc", "price.mstr"],
  "btc.perShare.basic": ["btc.held", "shares.basic"],
  "btc.perShare.cebe": ["btc.held", "claims.cebe", "shares.basic"],
  "amp.residual": ["claims.cebe"],
};

const cache: Freshness[][] = [];

function at(id: MetricId, i: number): Freshness {
  if (id === "btc.held") return heldAt(i);
  if (id === "claims.cash") {
    const base = fromSeries(daily.cash, i, false);
    return {
      ...base,
      method: "spliced",
      note: "2026-08-30 起的週點是 Reserve + Cash；更早的週點只有 Reserve，底層仍有資產負債表現金。這條線的數字沒有因拆開而改寫。",
    };
  }
  const bal = BALANCE[id];
  if (bal) return fromSeries(bal, i, false);
  if (MARKET.includes(id)) return fromSeries(daily[id === "price.mstr" ? "mstr" : "btc"], i, true);
  const parts = DERIVED[id];
  if (parts) {
    const kids = parts.map((p) => at(p, i));
    const asOf = kids.map((k) => k.asOf).sort()[0]!;
    return { method: "reconstructed", asOf, note: NOTE.reconstructed, value: null };
  }
  return { method: "observed", asOf: daily.date[i]!, note: NOTE.observed, value: null };
}

export function freshness(id: MetricId, i: number): Freshness {
  let row = cache[i];
  if (!row) {
    row = [];
    cache[i] = row;
  }
  // 指標不多，線性找。
  const idx = BADGE_ORDER.indexOf(id);
  if (idx >= 0 && row[idx]) return row[idx]!;
  const f = at(id, i);
  if (idx >= 0) row[idx] = f;
  return f;
}

export const BADGE_ORDER: MetricId[] = [
  "btc.held", "claims.debt", "claims.pref", "claims.cash", "shares.basic",
  "price.mstr", "price.btc",
];

export function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export const FIELD_LABEL: Record<string, string> = {
  "btc.held": "持幣",
  "claims.debt": "可轉債",
  "claims.pref": "優先股面額",
  "claims.cash": "美元資產",
  "shares.basic": "股數",
  "price.mstr": "MSTR",
  "price.btc": "BTC",
};
