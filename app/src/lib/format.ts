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


/** EDGAR 上這份申報的頁面。accession 去掉破折號就是目錄名。
 *
 *  指向申報索引而不是正文檔案:索引頁會列出全部附件(新聞稿、簡報),
 *  而正文的檔名每一份都不一樣,存進 JSON 會讓 payload 多出好幾 KB。 */
export const CIK = "1050446";
export const edgarUrl = (accession: string): string =>
  `https://www.sec.gov/Archives/edgar/data/${CIK}/`
  + `${accession.replace(/-/g, "")}/${accession}-index.htm`;

/** EDGAR 上這家公司某一種表單的全部申報。給資料品質頁的檔案庫表用。 */
export const edgarFormUrl = (form: string): string =>
  `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${CIK}`
  + `&type=${encodeURIComponent(form)}&dateb=&owner=include&count=40`;
