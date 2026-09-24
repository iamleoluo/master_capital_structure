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
    cebe: Delta;
    grossBps: Delta; mnavCebe: Delta; mstrPrice: Delta;
    strcPrice: (Delta & { low: number; lowDate: string }) | null;
  };
  /** 逐日鏈結:決策用當下幣價評價,不含後見之明。兩項加總 = 實現的 ΔCEBE */
  split: { market: number; decision: number };
  /** 四層對數歸因,與績效歸因頁同一個口徑。四項相加 = ln(MSTR 報酬比) */
  layers4: { btc: number; decision: number; claims: number; mnav: number };
  flows: {
    prefRaisedM: number; commonRaisedM: number;
    prefRepurchasedShares: number; prefRepurchasedM: number;
    btcBought: number; btcSold: number;
  };
  events: { d: string; label: string; kind: "policy" | "ipo" }[];
  /** 只有進行中的那一則會有:各回購計畫的剩餘授權(百萬美元) */
  remainingAuthorityM?: Record<string, number>;
}

/** 策略歸因的單一起始日結果(終點恆為最新一天)。 */
export interface StrategyRow {
  cebe0: number;
  /** 三層乘法恆等式的對數拆解,三者加總 = log(股價比) */
  layers: { mnav: number; cebe: number; btc: number };
  /** 總變化太小時佔比會失真,此旗標為 false 時改顯示各層自身漲跌 */
  mstrRet: number; btcRet: number;
  bought: number; sold: number;
  /** 操作層級拆解,各項加總 = ΔCEBE */
  ops: {
    price: number; atm: number; pref_issue: number; buyback: number;
    converts: number; btc: number; carry: number; other: number;
  };
  opMeta: {
    raisedM: number; discountM: number; carryM: number;
    prefParM: number; prefProceedsM: number; debtM: number; residualM: number;
  };
  /** 逐日鏈結:行情 vs 決策(決策用當下幣價評價,無後見之明),單位 sats／股 */
  split: { market: number; decision: number };
  /** 同一個拆解但在對數空間,兩項相加 = layers.cebe */
  splitLog: { market: number; decision: number };
  /** Gross BPS(公司的 BTC Yield):公式無幣價項 */
  bps0: number;
  /** 資金流揭露是否完整到足以下結論(殘差 ≤ 總變化的 25%) */
  opsOk: boolean;
}

export interface Strategy {
  end: string;
  cebeNow: number;
  bpsNow: number;
  priceNow: number;
  rows: (StrategyRow | null)[];
  presets: { id: string; label: string; date: string }[];
}

export interface Meta {
  ipos: Ipo[];
  /** 資本結構工具箱 —— 公司能動用的完整槓桿清單 */
  toolkit: ToolSpec[];
  /** 大事記最上面的整體框架:長期論述 + 全期數字 */
  program: {
    lede: string;
    /** 全期的決策 vs 行情 */
    split: { market: number; decision: number };
    /** 全期四層對數歸因,與績效歸因頁同一個口徑 */
    layers4: { btc: number; decision: number; claims: number; mnav: number };
    principles: { t: string; b: string }[];
    span: [string, string];
    metrics: {
      cebe: Delta;
      held: Delta; btcPrice: Delta; mstrPrice: Delta; claims: Delta;
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
