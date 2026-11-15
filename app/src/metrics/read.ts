/** 從已發布的 daily.json 取出具名指標。金融加減只寫在這個檔案。
 *
 *  金額沿用投影的單位（十億美元）。格式化時再標 B。
 */
import { daily, meta, N } from "../data";
import { METRICS, type MetricId } from "./registry";

export type Method =
  | "published"
  | "observed"
  | "step"
  | "carry"
  | "linear"
  | "spliced"
  | "reconstructed"
  | "assumed";

export interface Value {
  metric: MetricId;
  value: number | null;
  unit: (typeof METRICS)[MetricId]["unit"];
  /** 這一列面板的日期。欄位自己的截至日在下一步才分開。 */
  asOf: string;
  method: Method;
  basis: Readonly<Record<string, string>>;
  sources: readonly string[];
  label: string;
}

function row(metric: MetricId, i: number, value: number | null): Value {
  const def = METRICS[metric];
  return {
    metric,
    value,
    unit: def.unit,
    asOf: daily.date[i]!,
    method: "published",
    basis: def.basis ?? {},
    sources: [],
    label: def.label,
  };
}

/** 淨求償權，十億美元。全站只有這裡做這次加減。 */
export function claimsNetB(i: number): number {
  return daily.debt[i]! + daily.pref_total[i]! - daily.cash[i]!;
}

export function claimsPartsB(i: number): { debt: number; pref: number; cash: number; net: number } {
  const debt = daily.debt[i]!;
  const pref = daily.pref_total[i]!;
  const cash = daily.cash[i]!;
  return { debt, pref, cash, net: debt + pref - cash };
}

const PREF_KEYS = ["strf_lp", "strc_lp", "strk_lp", "strd_lp", "stre_lp"] as const;

/** 現金從可轉債層往上扣。堆疊頂等於 claimsNetB。 */
export function claimsStackB(i: number): { debt: number; prefs: number[]; top: number } {
  let cashLeft = daily.cash[i]!;
  const debt = Math.max(0, daily.debt[i]! - cashLeft);
  cashLeft = Math.max(0, cashLeft - daily.debt[i]!);
  const prefs: number[] = [];
  for (const key of PREF_KEYS) {
    const raw = (daily[key] as number[])[i]!;
    prefs.push(Math.max(0, raw - cashLeft));
    cashLeft = Math.max(0, cashLeft - raw);
  }
  const top = claimsNetB(i);
  const drift = top - (debt + prefs.reduce((s, v) => s + v, 0));
  let k = prefs.length - 1;
  while (k > 0 && prefs[k] === 0) k--;
  prefs[k] = (prefs[k] ?? 0) + drift;
  return { debt, prefs, top };
}

/** 實得每股，單位是比特幣（顆／股），不是 sats。 */
export function btcPerShareCebe(i: number): number {
  const shares = daily.shares[i]! * 1e6;
  return daily.common_btc[i]! / shares;
}

export interface IdentityFactors {
  price: string;
  mnav: string;
  btcPerShare: string;
  btcPrice: string;
  sats: string;
}

/** 畫面上的三個因數。精度讓它們相乘後與顯示股價相差不超過 1 分。 */
export function formatIdentity(i: number): IdentityFactors {
  const price = daily.mstr[i]!;
  const mnav = daily.mnav_cebe[i]!;
  const per = btcPerShareCebe(i);
  const btc = daily.btc[i]!;
  return {
    price: price.toFixed(2),
    mnav: mnav.toFixed(5),
    btcPerShare: per.toFixed(8),
    btcPrice: btc.toFixed(2),
    sats: Math.round(per * 1e8).toLocaleString("en-US"),
  };
}

export function metricAt(id: MetricId, i: number): Value {
  switch (id) {
    case "price.mstr": return row(id, i, daily.mstr[i]!);
    case "price.btc": return row(id, i, daily.btc[i]!);
    case "mnav.basic": return row(id, i, daily.mnav_basic[i]!);
    case "mnav.cebe": return row(id, i, daily.mnav_cebe[i]!);
    case "claims.cebe": return row(id, i, claimsNetB(i));
    case "claims.debt": return row(id, i, daily.debt[i]!);
    case "claims.pref": return row(id, i, daily.pref_total[i]!);
    case "claims.cash": return row(id, i, daily.cash[i]!);
    case "btc.held": return row(id, i, daily.held[i]!);
    case "shares.basic": return row(id, i, daily.shares[i]!);
    case "btc.perShare.basic": return row(id, i, daily.bps[i]!);
    case "btc.perShare.cebe": return row(id, i, btcPerShareCebe(i) * 1e8);
    case "amp.residual": return row(id, i, daily.amp[i] ?? null);
    default: {
      const _never: never = id;
      return _never;
    }
  }
}

export interface RunwayView {
  years: number;
  assetsB: number;
  obligationsB: number;
  assetsAsOf: string;
  numerator: string;
  denominator: string;
}

/** 分子是最新一列的現金欄（投影裡現金已含 8-K 流動性）。分母仍是常數。 */
export function runwayNow(): RunwayView {
  const assetsB = daily.cash[N - 1]!;
  const obligationsB = meta.limits.annualObligationsB;
  const assetsAsOf = daily.date[N - 1]!;
  return {
    years: assetsB / obligationsB,
    assetsB,
    obligationsB,
    assetsAsOf,
    numerator: `美元資產（Reserve + Cash）$${assetsB.toFixed(2)}B，截至 ${assetsAsOf}`,
    denominator: `年化股息與利息 $${obligationsB.toFixed(2)}B，仍是 2026-08-24 的常數，不隨發行更新`,
  };
}

export const LAST = N - 1;
