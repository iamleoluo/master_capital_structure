/** 座標軸換算。取代先前每張圖各自內嵌一份 y 函式的做法。 */

export interface Scale {
  (v: number): number;
  invert(px: number): number;
  domain: [number, number];
  range: [number, number];
}

function make(fwd: (v: number) => number, inv: (p: number) => number,
              domain: [number, number], range: [number, number]): Scale {
  const s = fwd as Scale;
  s.invert = inv;
  s.domain = domain;
  s.range = range;
  return s;
}

export function linear(domain: [number, number], range: [number, number]): Scale {
  const [d0, d1] = domain, [r0, r1] = range;
  const span = d1 - d0 || 1;
  return make(
    (v) => r0 + ((v - d0) / span) * (r1 - r0),
    (p) => d0 + ((p - r0) / (r1 - r0 || 1)) * span,
    domain, range,
  );
}

export function log(domain: [number, number], range: [number, number]): Scale {
  const lo = Math.max(domain[0], 1e-9), hi = Math.max(domain[1], lo * 1.0001);
  const l0 = Math.log(lo), l1 = Math.log(hi);
  const [r0, r1] = range;
  return make(
    (v) => r0 + ((Math.log(Math.max(v, 1e-9)) - l0) / (l1 - l0)) * (r1 - r0),
    (p) => Math.exp(l0 + ((p - r0) / (r1 - r0 || 1)) * (l1 - l0)),
    [lo, hi], range,
  );
}

/** 資料範圍加上邊距。log 軸用乘法邊距,linear 用加法。 */
export function extent(values: number[], padLo = 0.9, padHi = 1.1): [number, number] {
  let lo = Infinity, hi = -Infinity;
  for (const v of values) {
    if (!Number.isFinite(v)) continue;
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  if (!Number.isFinite(lo)) return [0, 1];
  return [lo * padLo, hi * padHi];
}

/** 產生大致等距的刻度值。 */
export function ticks(lo: number, hi: number, count = 4): number[] {
  const out: number[] = [];
  for (let i = 0; i <= count; i++) out.push(lo + ((hi - lo) * i) / count);
  return out;
}
