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

/** 期初 → 期末 + 變化率。pct 在期初為 0 時是 null。 */
export interface Delta { from: number; to: number; pct: number | null; }

export interface ToolSpec {
  id: string; label: string;
  claims: string; shares: string; btc: string; cebe: string; note: string;
}

/** 大事記的一則。敘述是人工撰寫,數字全部由管線重算。 */
export interface Era {
  id: string; title: string; subtitle: string;
  start: string; end: string | null; ongoing: boolean;
  trigger: string; body: string[]; watch: string;
  /** 對應 daily.date 的索引區間(含頭尾),圖表直接吃 */
  range: [number, number];
  days: number;
  /** 人工標註的主要手法 */
  tools: string[];
  /** 由資料判定實際有動作的工具 */
  toolsActive: string[];
  metrics: {
    btcPrice: Delta; held: Delta; claims: Delta; pref: Delta; shares: Delta;
    cebe: Delta; grossBps: Delta; mnavCebe: Delta; mstrPrice: Delta;
    strcPrice: (Delta & { low: number; lowDate: string }) | null;
  };
  flows: {
    prefRaisedM: number; commonRaisedM: number;
    prefRepurchasedShares: number; prefRepurchasedM: number;
    btcBought: number; btcSold: number;
  };
  events: { d: string; label: string; kind: "policy" | "ipo" }[];
  /** 只有進行中的那一則會有:各回購計畫的剩餘授權(百萬美元) */
  remainingAuthorityM?: Record<string, number>;
}

export interface Meta {
  ipos: Ipo[];
  /** 資本結構工具箱 —— 公司能動用的完整槓桿清單 */
  toolkit: ToolSpec[];
  /** 大事記最上面的整體框架:長期論述 + 全期數字 */
  program: {
    lede: string;
    principles: { t: string; b: string }[];
    span: [string, string];
    metrics: {
      cebe: Delta; held: Delta; btcPrice: Delta; mstrPrice: Delta; claims: Delta;
    };
    btcSoldEver: number; btcBoughtEver: number;
    soldPctOfHoldings: number; reserveYears: number;
  };
  /** 管線偵測到的結構變化提醒 */
  watch: string[];
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
