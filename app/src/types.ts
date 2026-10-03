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
  /** 這一週的數字來自哪一份 8-K 的 EDGAR accession。null = 只有持有量觀測、
   *  沒有對應的活動表那一列(前端就不給連結)。 */
  acc: string | null;
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
  /** atom = 單一狀態轉移(講義 L2);combo = 兩步以上串成(講義 L3) */
  kind: "atom" | "combo";
  /** 經過的位置。原子是兩點(H / U / DL / S / OUT),組合是三點以上,
   *  而且中間那點永遠是 U —— 錢要先變成現金才能往下一步走。 */
  moves: string[];
  /** ↑ / ↓ / — ,由 moves 推出來。
   *  claims 可能是 "?" —— C = D + L − U,募資與償還會讓 DL 與 U 同向移動,
   *  淨效果取決於面額與價金的大小,不是方向問題。那時要看 eq 與 cebe。 */
  claims: string; shares: string; btc: string; cebe: string; note: string;
  /** 代數(LaTeX)。bps = 對帳面每股 B,eq = 對實得每股 E */
  bps: string; eq: string;
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
  /** ΔB 的兩因子拆解(sats／股),加總 = 帳面每股的變化 */
  bpsOps: { held: number; shares: number };
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

export interface Provenance {
  /** L1 檔案庫:每一種表單各歸檔了幾份 */
  docs: { src: string; n: number; lo: string; hi: string; mb: number }[];
  doc_total: number;
  /** L2 事件,按粒度分組('week' | 'quarter' | 'year' | 'instant') */
  events: Record<string, number>;
  event_total: number;
  /** 其中屬於「動作」家族的(其餘是觀測) */
  action_total: number;
  /** 年報買幣經過粒度解析後的殘差 —— 趨近零代表三種粒度對得起來 */
  years: { y: string; stated_b: number; left_b: number; pct: number }[];
  /** 跨文件對不上的粗粒度事件。目前只有成交日 vs 交割日那一筆 */
  conflicts: { kind: string; grp: string; lo: string; hi: string;
               stated_b: number; fine_b: number }[];
  /** 各階段的資金來源與用途對帳。resolvable=false 表示期間比可用粒度還短 */
  recon: { title: string; lo: string; hi: string;
           uses_b: number; sources_b: number; gap_b: number; gap_pct: number;
           prorated_b: number; resolvable: boolean }[];
}

/** L3 的一筆具名資本操作(數值解)。
 *  公式解那一欄的對應物是 formulas.ts 的 Formula ——
 *  同一把工具,一個講代數、一個講這一週實際做了多少。 */
export interface Operation {
  id: string;
  /** toolbox 的工具 id,可以對回 formulas.byId */
  tool: string;
  kind: "atom" | "combo";
  lo: string; hi: string;
  qty: number | null; usd: number | null;
  /** 對兩把尺的效果(sats)。由 toolbox.effect() 算,不是前端算的 */
  dB: number | null; dE: number | null;
  /** true/false = 加分/減分;null = 這把工具結構上恆中性 */
  accretive: boolean | null;
  /** 配對規則與信心度。unpaired = 單一操作,沒有配對 */
  rule: string; conf: number;
  /** 文件原句 —— 配對的依據。沒有配對就是 null */
  quote: string | null;
  /** 來源申報的 EDGAR accession */
  acc: string[];
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
  /** 出處、粒度、資金對帳 —— 資料品質頁的三個區塊,全部由 L1/L2 現算 */
  prov: Provenance;
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
