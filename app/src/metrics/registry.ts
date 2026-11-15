/** 具名指標。頁面只准引用這裡的 id。式子的數值在 read.ts，且只有那裡。 */

export const METRIC_IDS = [
  "price.mstr",
  "price.btc",
  "mnav.basic",
  "mnav.cebe",
  "claims.cebe",
  "claims.debt",
  "claims.pref",
  "claims.cash",
  "btc.held",
  "shares.basic",
  "btc.perShare.basic",
  "btc.perShare.cebe",
  "amp.residual",
] as const;

export type MetricId = (typeof METRIC_IDS)[number];

export type Unit = "USD" | "USDb" | "BTC" | "sats" | "shareM" | "ratio" | "year";

export interface MetricDef {
  id: MetricId;
  label: string;
  unit: Unit;
  basis?: Readonly<Record<string, string>>;
}

export const METRICS: Record<MetricId, MetricDef> = {
  "price.mstr": { id: "price.mstr", label: "MSTR 股價", unit: "USD" },
  "price.btc": { id: "price.btc", label: "比特幣價格", unit: "USD" },
  "mnav.basic": {
    id: "mnav.basic", label: "basic mNAV", unit: "ratio",
    basis: { mnav: "basic", shares: "basic" },
  },
  "mnav.cebe": {
    id: "mnav.cebe", label: "CEBE mNAV", unit: "ratio",
    basis: { mnav: "cebe", claims: "cebetracker", shares: "basic" },
  },
  "claims.cebe": {
    id: "claims.cebe",
    label: "淨求償權（可轉債面額 + 優先股清算優先權 − 現金）",
    unit: "USDb",
    basis: { claims: "cebetracker", cash: "balance_sheet" },
  },
  "claims.debt": { id: "claims.debt", label: "可轉債面額", unit: "USDb" },
  "claims.pref": { id: "claims.pref", label: "優先股清算優先權", unit: "USDb" },
  "claims.cash": { id: "claims.cash", label: "現金", unit: "USDb" },
  "btc.held": { id: "btc.held", label: "持幣", unit: "BTC" },
  "shares.basic": { id: "shares.basic", label: "basic 股數", unit: "shareM" },
  "btc.perShare.basic": { id: "btc.perShare.basic", label: "帳面每股", unit: "sats" },
  "btc.perShare.cebe": {
    id: "btc.perShare.cebe", label: "實得每股", unit: "sats",
    basis: { claims: "cebetracker", shares: "basic" },
  },
  "amp.residual": {
    id: "amp.residual", label: "槓桿倍數", unit: "ratio",
    basis: { claims: "cebetracker" },
  },
};

export function isMetricId(s: string): s is MetricId {
  return (METRIC_IDS as readonly string[]).includes(s);
}
