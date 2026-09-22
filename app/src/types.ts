/** 資料型別 —— 對應 web/build_data.py 的輸出。改後端 schema 時這裡要同步。 */

/** 日頻序列。所有陣列等長,以索引對齊 daily.date。 */
export interface Daily {
  date: string[];
  btc: number[];
  mstr: number[];
  held: number[];
  /** basic 在外股數,單位百萬股 */
  shares: number[];
  /** 以下金額單位一律十億美元 */
  debt: number[];
  cash: number[];
  pref_total: number[];
  mnav_basic: number[];
  mnav_cebe: number[];
  claims_pct: number[];
  /** 每股 BTC,單位 sats */
  bps: number[];
  amp: (number | null)[];
  /** BTC 計價的求償權與普通股殘量,單位「顆」 */
  claims_btc: number[];
  common_btc: number[];
  /** 距離最近一次真實 SEC 觀測點幾天 */
  stale: number[];
  strf_lp: number[]; strc_lp: number[]; strk_lp: number[];
  strd_lp: number[]; stre_lp: number[];
  strf_price: (number | null)[]; strc_price: (number | null)[];
  strk_price: (number | null)[]; strd_price: (number | null)[];
  stre_price: (number | null)[];
}

export type PrefTicker = "STRF" | "STRC" | "STRK" | "STRD" | "STRE";
export type SecurityTicker = PrefTicker | "MSTR";

/** 逐週 8-K 觀測。delta 為負代表賣幣。 */
export interface Week {
  week_end: string;
  week_start: string | null;
  holdings: number | null;
  delta: number | null;
  avg_price: number | null;
  /** 融資券種;空陣列代表未指名。可能來自 8-K 敘述句明示,
   *  也可能由同一份文件的 ATM 表格推得(見 funding_derived)。 */
  funding: SecurityTicker[];
  /** true = 由 ATM 表格推得,不是 8-K 敘述句明示 */
  funding_derived: boolean;
  funding_raw: string;
  sale_use: string;
  source_kind: "named" | "derived" | "unspecified" | "btc_sale" | null;
  /** 該週各券種 ATM 淨募資,單位百萬美元 */
  raised_m: Partial<Record<SecurityTicker, number>>;
  raised_total_m: number | null;
}

export interface Ipo {
  t: PrefTicker; name: string; d: string; lp: number;
  rate: number | null; rank: number; note: string; cur: string;
}

export interface PolicyBreak {
  d: string; title: string; detail: string; hard: boolean;
}

export interface Meta {
  ipos: Ipo[];
  breaks: PolicyBreak[];
  fwp: {
    held: number; btc: number; price: number; fdso: number; basic: number;
    assumed: number; debt: number; reserve: number;
    pref: Record<string, number>;
    gross_bps: number; net_bps: number;
    /** 這組官方數字出自哪一份 FWP */
    date: string;
  };
  sens: { btc: number; off: number; got: number }[];
  be: { k: string; v: number }[];
  anchors: Record<"btc_held" | "shares" | "debt", [string, number][]>;
  findings: { t: string; b: string }[];
}
