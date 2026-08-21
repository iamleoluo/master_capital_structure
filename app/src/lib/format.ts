export const usd = (v: number, dp = 2): string =>
  "$" + v.toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });

export const usd0 = (v: number): string => "$" + Math.round(v).toLocaleString("en-US");

export const bn = (v: number | null | undefined): string =>
  v == null ? "—" : "$" + v.toFixed(2) + "B";

export const mn = (v: number | null | undefined): string =>
  v == null ? "—" : "$" + v.toFixed(0) + "M";

export const mult = (v: number | null | undefined): string =>
  v == null ? "—" : v.toFixed(2) + "x";

export const pct = (v: number, dp = 1): string => (v * 100).toFixed(dp) + "%";

export const sats = (v: number): string =>
  Math.round(v).toLocaleString("en-US") + " sats";

export const btc = (v: number | null | undefined, dp = 0): string =>
  v == null ? "—" : v.toLocaleString("en-US", { maximumFractionDigits: dp });

export const signed = (v: number, dp = 0): string =>
  (v >= 0 ? "+" : "") + v.toLocaleString("en-US", { maximumFractionDigits: dp });
