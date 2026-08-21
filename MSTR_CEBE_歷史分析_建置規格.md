# MSTR × BTC × mNAV × CEBE 歷史對照系統 — 建置規格書

> 交付給 Claude Code 的實作規格。
> 撰寫日期:2026-08-17
> 目的:建立一套能回答「在某個 BTC 價格下、某個 mNAV 對應到 MSTR 什麼股價」的歷史對照工具,並且把 2025–2026 年優先股大量增發造成的結構性變化明確拆出來。

---

## 0. 為什麼需要接 API(這份文件的定位)

這個分析的資料分成兩類,取得難度完全不同:

| 資料類別 | 取得方式 | 本文件提供 |
|---|---|---|
| 市場價格(BTC 日線、MSTR 日線) | **必須接 API**,免費 API 就夠 | 只提供 API 選擇與端點 |
| 資本結構(優先股餘額、可轉債、股數、現金) | SEC 文件,**部分可用 XBRL API,部分只能人工讀** | ✅ 已人工整理好,見 §5 |
| 驗證錨點 | 公司自己揭露的敏感度表 | ✅ 已反解出精確參數,見 §6 |

**§5 和 §6 是這份文件的核心價值**。市場價格 API 隨便接都有,但資本結構的季度序列如果沒人先整理,你會在 SEC EDGAR 裡面翻很久,而且很容易把「面額 / 清算優先權 / 市值」三種數字搞混。

---

## 1. 專案目標與核心論點

### 1.1 使用者要回答的問題

> 「在 BTC = X 的情況下,mNAV = Y 對應到 MSTR 股價是多少?」

這個對應在 2024 年(沒有優先股的時代)是一個乾淨的函數。2025 年之後被優先股打破了,原因是分子(可分配給普通股的 BTC)被優先求償權切掉一大塊,而且切掉的比例隨 BTC 價格浮動。

### 1.2 必須拆開的兩件事

這是整個專案最重要的分析要求。**這兩件事活在不同的度量上,不能加總成一個圓餅圖**:

1. **市場情緒溢價收縮** — 這是 basic mNAV(市值 ÷ BTC 市值)壓縮的幾乎全部內容。basic mNAV 在數學上**完全看不到優先股**。
2. **資本結構稀釋** — 這**不會出現在 basic mNAV 裡**。它顯示在三個地方:
   - basic mNAV 與 enterprise / CEBE mNAV 之間的楔形差距
   - Gross BPS 與 Net BPS 之間的每股落差
   - CEBE break-even 價格的上升軌跡

如果最後產出的圖把這兩者畫成「壓縮的 X% 來自情緒、Y% 來自稀釋」的堆疊圖,那就是做錯了。正確做法是**畫成兩條並行的軌跡**,讓讀者看到它們是正交的。

### 1.3 已驗證的核心對數分解(可以拿來當實作參考)

basic mNAV 從 2024-11-21 的 ~3.67x 到 2026-08-13 的 ~0.71x:

```
MSTR 股價:      $543 → $97.33        ×0.179   (log −1.72)
BTC 價格:       ~$98,000 → $64,279   ×0.656   (log +0.42, 反而墊高 mNAV)
BTC/share(BPS): ×1.367                        (log −0.31, 稀釋)
────────────────────────────────────────────────────────
淨效果:         ×0.20  →  3.67 × 0.20 ≈ 0.73x  ✓ 對得上
```

結論:**basic mNAV 的崩跌幾乎全部是股價跌得比 BTC NAV/股 快,也就是溢價收縮**;股數稀釋是次要的約 19% 拖累;BTC 價格下跌反而**墊高**了 basic mNAV。優先股的效果完全不在這條式子裡。

---

## 2. 資料來源與 API

### 2.1 BTC 價格歷史

| 選項 | 端點 | 說明 |
|---|---|---|
| **CoinGecko**(推薦起手) | `GET https://api.coingecko.com/api/v3/coins/bitcoin/market_chart/range?vs_currency=usd&from={unix}&to={unix}` | 免費層有 rate limit;超過 365 天需付費層。Demo key 可申請 |
| Binance Klines | `GET https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d&startTime=...&limit=1000` | 免費、無需 key、日線完整,分頁抓即可。**最省事的選項** |
| Coinbase | `GET https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=86400` | 每次上限 300 根 K 棒,要分頁 |
| CryptoCompare | `https://min-api.cryptocompare.com/data/v2/histoday` | 需 free API key |

⚠️ **注意 BTC 價格的定義差異**:cebetracker / Strategy 用的可能是特定時點的 spot,不同交易所收盤價會差 0.1–0.5%。做驗證時要容許誤差。

### 2.2 MSTR 股價歷史

| 選項 | 說明 |
|---|---|
| **yfinance**(Python)| `yf.download("MSTR", start="2024-01-01")` — 最快,已自動做 split 調整 |
| Alpha Vantage | `TIME_SERIES_DAILY_ADJUSTED`,免費 key,25 req/day 限制 |
| Polygon.io | 免費層 5 req/min,資料品質好 |
| Tiingo / EODHD | 需付費但穩定 |

⚠️ **Split 陷阱**:MSTR 在 **2024-08-07 做過 10-for-1 分割**。所有資料源都應該回溯調整,但務必驗證:2024-11-21 的歷史新高應該顯示為 **$543**(已調整)。如果你看到 $5,430,代表沒調整。

### 2.3 SEC 資料(資本結構)

**CIK = `0001050446`**(MicroStrategy / Strategy Inc)

XBRL Frames / Company Concept API,**免費、免 key**,但要在 header 帶 `User-Agent: your-name your@email.com`,否則會被擋:

```
https://data.sec.gov/api/xbrl/companyconcept/CIK0001050446/us-gaap/{tag}.json
https://data.sec.gov/api/xbrl/companyfacts/CIK0001050446.json     ← 一次抓全部,推薦
https://data.sec.gov/submissions/CIK0001050446.json                ← 列出所有申報文件
```

可能有用的 XBRL tag:

| 資料 | tag |
|---|---|
| BTC 持有數量 | `us-gaap:CryptoAssetNumberOfUnits`(ASU 2023-08 之後才有) |
| BTC 公允價值 | `us-gaap:CryptoAssetFairValueDisclosure` |
| 流通普通股 | `dei:EntityCommonStockSharesOutstanding`、`us-gaap:CommonStockSharesOutstanding` |
| 優先股清算優先權 | `us-gaap:TemporaryEquityLiquidationPreference`、`us-gaap:PreferredStockLiquidationPreferenceValue` |
| 長期債務 | `us-gaap:LongTermDebtNoncurrent`、`us-gaap:ConvertibleNotesPayable` |
| 現金 | `us-gaap:CashAndCashEquivalentsAtCarryingValue` |
| 稀釋後加權平均股數 | `us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding` |

⚠️ **XBRL 抓不到的東西**(必須人工讀文件,已在 §5 幫你整理好):
- **各系列優先股分開的餘額**(STRK/STRF/STRD/STRC/STRE)。XBRL 通常只標總數,分系列的數字在 10-Q 的權益附註表格裡,而且 Strategy 用 custom axis 標記,解析成本很高。
- **USD Reserve 餘額**(這不是 GAAP 科目,是管理層自訂的指標,只在 8-K / 新聞稿揭露)
- **可轉債各系列的轉換價與到期日**(在債務附註的敘述文字裡)

### 2.4 每週 BTC 買賣公告

Strategy 每週一發 8-K 公告 BTC 買賣。用 submissions API 篩 `form == "8-K"`,再抓 Exhibit 99.1。這是重建「每筆買幣的融資來源」的唯一途徑,而融資來源決定該筆買幣是 CEBE-accretive 還是 CEBE-neutral(見 §4.5)。

### 2.5 第三方對照(Tier 2,只用來 cross-check,不當事實)

- `cebetracker.io` — CEBE 框架原創者(Bobby Tierney),前端是 JS 動態載入,可以試著找它的 JSON 端點
- `mnav.com/mnav/strategy` — 有 CEBE mNAV 與 naive mNAV 並列
- `bitcointreasuries.net`、`bitcoinquant.co`、`charts.bitbo.io/mstr-nav-premium/`
- `strategy.com` 官方儀表板(有 Investor API,mnav.com 聲稱在用,但我沒驗證過端點)

---

## 3. 資料 Schema 建議

```sql
-- 日頻:市場資料
CREATE TABLE market_daily (
    date            DATE PRIMARY KEY,
    btc_close_usd   NUMERIC,
    mstr_close_usd  NUMERIC,   -- split-adjusted
    mstr_volume     BIGINT
);

-- 事件頻:資本結構(只在有申報/公告時更新,查詢時 forward-fill)
CREATE TABLE capital_structure (
    as_of_date              DATE PRIMARY KEY,
    source_tier             INT,        -- 1=SEC/官方, 2=專業分析, 3=媒體
    source_ref              TEXT,       -- accession number 或 URL
    btc_held                NUMERIC,
    debt_notional_usd       NUMERIC,    -- 可轉債面額
    pref_strk_usd           NUMERIC,    -- 清算優先權,不是市值
    pref_strf_usd           NUMERIC,
    pref_strd_usd           NUMERIC,
    pref_strc_usd           NUMERIC,
    pref_stre_usd           NUMERIC,    -- 歐元計價,存已換算的 USD 並另存匯率
    pref_stre_eur           NUMERIC,
    usd_reserve             NUMERIC,
    cash_and_equiv          NUMERIC,
    shares_basic            NUMERIC,
    shares_fdso             NUMERIC,    -- fully diluted, 用於 Net BPS
    shares_assumed_diluted  NUMERIC,    -- 用於 Gross BPS,跟上面不一樣!見 §8.2
    annual_obligations_usd  NUMERIC,    -- 利息+優先股股利年度總額
    is_estimated            BOOLEAN,    -- 標記推估值
    note                    TEXT
);

-- 每週買賣紀錄(用於融資來源歸因)
CREATE TABLE btc_transactions (
    week_end        DATE,
    btc_delta       NUMERIC,    -- 負數代表賣出
    avg_price_usd   NUMERIC,
    funding_source  TEXT,       -- 'common_atm' | 'preferred_atm' | 'convert' | 'cash' | 'mixed'
    source_8k       TEXT
);
```

**設計要點**:資本結構是事件頻不是日頻。做日線圖時對 `capital_structure` 做 forward-fill(以最近一次申報為準),並且**在圖上標出申報日**,讓讀者知道哪一段是真實觀測、哪一段是延續假設。

---

## 4. 計算公式

### 4.1 五種 mNAV(全部都要算,不能只算一種)

⚠️ **同一天、同一個股價,這五個數字可以分別落在 1.0x 的兩側**。任何一個 mNAV 數字**必須同時標註變體名稱與日期**,否則無意義。

```python
# (i) basic mNAV — 完全看不到優先股
mnav_basic = market_cap_basic / (btc_held * btc_price)

# (ii) diluted mNAV
mnav_diluted = (mstr_price * shares_fdso) / (btc_held * btc_price)

# (iii) enterprise mNAV
enterprise_value = market_cap + debt_notional + pref_total - cash
mnav_enterprise = enterprise_value / (btc_held * btc_price)

# (iv) 公司自訂(2026-07-23 重新定義後)—— 見 §4.2
mnav_company = mstr_price / net_bps_usd

# (v) CEBE mNAV
cebe_btc_per_share = (btc_held - net_senior_claims_usd / btc_price) / shares_basic
mnav_cebe = mstr_price / (cebe_btc_per_share * btc_price)
```

### 4.2 Strategy 官方公式(2026-08-13 FWP,Tier 1,**已驗證可完全重現**)

這是最可靠的公式,因為公司自己在 SEC 文件裡給了敏感度表可以對答案:

```python
def net_reserve_per_share(btc_price, btc_held, usd_reserve,
                          debt_otm_notional, pref_otm_notional, fdso):
    """
    Strategy 官方 Net Reserve / Share。
    注意 'OTM'(out-of-the-money):價內的可轉債/STRK 應排除在求償權之外,
    因為它們會轉成股權而不是被償還。
    """
    return (btc_held * btc_price
            + usd_reserve
            - debt_otm_notional
            - pref_otm_notional) / fdso

# 2026-08-13 FWP 的確切參數(我已反解驗證)
PARAMS_2026_08_13 = {
    "btc_held":          840_447,
    "usd_reserve":       4.650e9,
    "debt_otm_notional": 6.754e9,
    "pref_otm_notional": 15.239e9,
    "fdso":              398_220_309,   # ← 反解得出,FWP 只寫 "~398.2M"
}

implied_price = target_mnav * net_reserve_per_share(btc_price, **PARAMS)
```

**Gross BPS(不同分母!)**:
```python
gross_bps_sats = btc_held / shares_assumed_diluted * 1e8
# 2026-08-13: 840,447 / 423_838_000 * 1e8 = 198,289 sats ✓
```

### 4.3 CEBE 框架公式(Tier 2,cebetracker.io)

```python
net_senior_claims_btc = (debt + preferred - cash) / btc_price
cebe_sats = (btc_held - net_senior_claims_btc) / shares * 1e8
claims_pct = net_senior_claims_btc / btc_held
common_equity_pct = 1 - claims_pct
break_even_btc = net_senior_claims_usd / btc_held
```

### 4.4 反向映射(使用者要的核心功能)

```python
def implied_mstr_price(btc_price, target_mnav, basis, params):
    """
    basis: 'gross' | 'net' | 'cebe'
    回傳:在該 BTC 價格與該資本結構下,達到 target_mnav 所需的 MSTR 股價
    """
    if basis == "gross":
        per_share = params.btc_held * btc_price / params.shares_assumed_diluted
    elif basis == "net":
        per_share = net_reserve_per_share(btc_price, **params)
    elif basis == "cebe":
        claims_btc = params.net_senior_claims_usd / btc_price
        per_share = (params.btc_held - claims_btc) * btc_price / params.shares_basic
    return target_mnav * per_share
```

### 4.5 融資來源歸因(phantom growth 量化)

```
優先股融資買幣  → CEBE-neutral(新 BTC 完全被新求償權抵銷),但 BPS 上升 → 這就是 phantom growth
普通股增發買幣  → 若發行價 > 1.0x net mNAV 則 CEBE-accretive
可轉債融資買幣  → 暫時性 claims,若後續轉股則「痊癒」
以折價回購優先股 → CEBE-accretive(retirement trade)
```

2026 年至今募得的資金,絕大多數是優先股(光 STRC 就 $7.53B),所以 **2026 年的 BTC 累積大部分是 CEBE-neutral**。這個結論要用 §2.4 的每週 8-K 逐筆驗證。

---

## 5. 資本結構時間軸(人工整理,Tier 1)

> 這一節是本文件最有價值的部分。以下數字全部來自 SEC 申報文件或 strategy.com 官方新聞稿。
> 標記 `[EST]` 的是我的推估,**必須在系統裡標記為推估值**。

### 5.1 優先股發行帳(IPO,Tier 1)

⚠️ **關鍵區分**:IPO 發行價($80/$85/$90)≠ 清算優先權(stated amount,一律 $100/股,STRE 為 €100/股)。**建模一律用 stated amount × 股數**。

| 系列 | 定價日 | IPO 股數 | 發行價 | Stated | IPO 清算優先權 | 淨募資 | 股利率 | 特性 |
|---|---|---|---|---|---|---|---|---|
| STRK (Strike) | 2025-01-30 | 7,300,000 | $80 | $100 | $730M | $563.4M | 8.00% | **可轉換** 0.1 MSTR/股 |
| STRF (Strife) | 2025-03-20 | 8,500,000 | $85 | $100 | $850M | $711.2M | 10.00% | 累積型,**最優先** |
| STRD (Stride) | 2025-06-05 | 11,764,700 | $85 | $100 | $1,176M | $979.7M | 10.00% | **非累積**、非強制,最劣後 |
| STRC (Stretch) | 2025-07-24 | 28,011,111 | $90 | $100 | $2,801M | $2,474M | 變動 | 2025 年全美最大 IPO |
| STRE (Stream) | 2025-11-06 | 7,750,000 | €80 | €100 | €775M | €608.8M | 10.00% | **歐元計價**,LuxSE |

**清償順位(rank)**:STRF(最優先)→ STRC → STRK → STRD(最劣後)→ 普通股。可轉債在所有優先股之上。

**STRC 股利率變動軌跡**(變動利率,建模時不能寫死):
- 2025-07(IPO):9.00%
- 2026-06-01 起:11.50%
- 2026-08 起的記錄日:12.00%
- 2026-06-08 股東會通過改為**半月配息**(原為月配)

### 5.2 季末優先股餘額(清算優先權,USD 千元)

| 季末 | STRK | STRF | STRD | STRC | STRE | **總計** | 總股數(千股) | 來源 |
|---|---|---|---|---|---|---|---|---|
| 2024-12-31 | 0 | 0 | 0 | 0 | 0 | **0** | 0 | — |
| 2025-03-31 | ~730,000 `[EST]` | ~850,000 `[EST]` | 0 | 0 | 0 | **~1,580,000** `[EST]` | ~15,800 `[EST]` | IPO 加總推估 |
| 2025-06-30 | ~900,000 `[EST]` | ~950,000 `[EST]` | 1,176,000 | 0 | 0 | **~3,026,000** `[EST]` | ~30,300 `[EST]` | 含 ATM 推估 |
| 2025-09-30 | ~1,100,000 `[EST]` | ~1,150,000 `[EST]` | ~1,250,000 `[EST]` | ~2,900,000 `[EST]` | 0 | **~6,400,000** `[EST]` | ~64,000 `[EST]` | 含 ATM 推估 |
| 2025-12-31 | ~1,364,000 `[EST]` | ~1,184,000 `[EST]` | ~1,266,000 `[EST]` | ~3,400,000 | ~818,000 | **8,032,324** ✅ | **78,183** ✅ | 10-K / 8-K |
| 2026-03-31 | — | — | — | **5,024,700** ✅ | — | **10,005,xxx** ✅ | — | Q1 10-Q |
| 2026-06-30 | **1,402,074** ✅ | **1,283,969** ✅ | **1,402,422** ✅ | **10,489,471** ✅ | €775,000 (~885,000) ✅ | **15,462,056** ✅ | **153,529** ✅ | Q2 10-Q |
| 2026-07-24 | — | — | — | ~10,460,000 ✅ | — | — | — | 回購後 |

✅ = 直接引自申報文件。2026-06-30 各系列股數:STRK 14,020,744 / STRF 12,839,689 / STRD 14,024,221 / STRC 104,894,705 / STRE 7,750,000。

**10-Q 原文**(2026-06-30):
> "Series A Perpetual Preferred Stock … 153,529 and 78,183 issued and outstanding at June 30, 2026 and December 31, 2025 … redemption value and liquidation preference of $15,462,056 and $8,032,324 …"

**STRC 成長軌跡**(單一系列就佔了總優先股的 2/3,是整個故事的主角):
```
2025-07 IPO   $2,801M
2025-12-31    ~$3,400M
2026-03-31     $5,025M   (50,247K 股)
2026-06-30    $10,489M   (104,895K 股)   ← 半年翻倍
```
Q2 2026 8-K:2026 年至今光 STRC 就募了 **$7.53B**(成長 254%)。

### 5.3 可轉債

| 時點 | 總面額 | 事件 |
|---|---|---|
| 2025 年底 | $8.21B | — |
| 2026-05 | **$6.71B** | 回購 $1.50B 的 2029 年零息可轉債 |
| 2026-08 | $6.754B(notional) | FWP |

已知系列:0.625% due 2028($1.01B,2024-09 發行)、0% due 2030(2025-02)、0.875% due 2031($603.75M,2024-03)、2.25% due 2032($800M,2024-06)、0% due 2029、2027 notes($1.05B,2025-02 大部分已轉換為 ~7.37M 股)。

⚠️ **各系列的轉換價與到期日我沒有完整取得**,信心度中等。這需要從某一期 10-Q 的債務附註表格人工抄一次(一次抄完就能用很久,因為債務結構變動不頻繁)。**這是 §5 唯一的重大缺口,建議優先補上**,因為 in-the-money / out-of-the-money 判定直接影響 Net BPS。

2027 notes 轉換價 **$143.25** — cebetracker 指出若 MSTR 回到此價位以上,$1.7B 的 2027 notes 轉股,break-even 會從 $23,270 降到 $20,887。

### 5.4 股數

| 時點 | Class A | Class B | 基本合計 | FDSO | 來源 |
|---|---|---|---|---|---|
| 2024-12-31 | ~248M `[EST]` | — | ~248M `[EST]` | — | 推估 |
| 2025-12-31 | 292.4M ✅ | — | — | — | 10-K |
| 2026-06-30 | 351.96M ✅ | 19.64M ✅ | 371.6M | — | 10-Q |
| 2026-07-24 | 364.6M ✅ | 19.64M ✅ | 384.2M | — | 8-K |
| 2026-08-10 | — | — | ~394.2M(隱含) | **398,220,309** | FWP 反解 |

稀釋後加權平均:192.5M(FY2024)→ 277.7M(FY2025)→ 333.9M(Q1 2026)。
**已反映 2024-08-07 的 10-for-1 分割。**

### 5.5 USD Reserve(非 GAAP,只在 8-K/新聞稿揭露)

2026-06-29 的 Digital Credit Capital Framework 建立:

| 日期 | 餘額 |
|---|---|
| 2026-06-29(啟動)| $2.55B |
| 2026-07-26 | $3.75B |
| 2026-08-09 | $4.65B |
| 2026-08-16 | $4.80B |

⚠️ 這跟資產負債表上的 cash & equivalents($2.45B @ 2026-06-30)**不是同一個東西**,不要混用。Strategy 官方 mNAV 公式用的是 USD Reserve。

### 5.6 年度固定義務

| 時點 | 年度利息+優先股股利 | 來源 |
|---|---|---|
| 2025-11 | ~$750–800M | CEO Phong Le 受訪 (Tier 3) |
| 2026-08-13 | **$1.736B** ✅ | FWP (Tier 1) |

### 5.7 BTC 持有量與重大事件

| 日期 | BTC 持有 | 事件 |
|---|---|---|
| 2024-09-30 | 252,220 | |
| 2024-12-31 | 446,400 | |
| 2025-03-31 | 550,000 | |
| 2026-01 | 709,715 | |
| 2026-04-12 | 780,897 | |
| 2026-04-20 | — | **買進 34,164 BTC**(史上第三大) |
| 2026-05-11 | — | 買進 535 BTC ← 斷崖式縮小 |
| 2026-05 下旬 | — | **2022 年以來首次賣出 BTC**(32 枚) |
| 2026-06-22 | — | 買進 520 BTC |
| 2026-07-05 | 843,775 | |
| 2026-08-03~09 | — | **賣出 1,690 BTC**($108.6M)用來回購 STRC |
| 2026-08-10 | 840,447 | FWP |
| 2026-08-16 | 842,137 | mnav.com |
| 2026-08-10~16 | — | 無買賣 |

**結構性轉折**:融資飛輪已經反轉。從「發溢價股票買幣」變成「賣幣+募資去折價回購優先股」。

### 5.8 政策與定義變更(建模時的斷點)

| 日期 | 事件 | 對建模的影響 |
|---|---|---|
| 2025-08-18 | 8-K 公布 mNAV 政策帶:>4x 積極增發 / 2.5–4x 機會性增發 / <2.5x 戰術性增發付息 / <1x 考慮發債回購 MSTR | 隱含股價 $210 / $600 / $1,000 |
| 2026-06-29 | Digital Credit Capital Framework 取代舊政策帶 | USD Reserve 下限 $1.25B;$1.0B 優先股回購授權;$1.0B MSTR 回購授權;$1.25B BTC 變現授權 |
| **2026-07-23** | **Strategy 重新定義自家 mNAV** 為 price ÷ Net BPS | ⚠️ **時間序列必須在此斷開**。公司明言前後「not comparable」 |

### 5.9 第三方 CEBE 錨點(Tier 2,用於 cross-check)

| 日期 | BTC 價 | 總 BTC | 淨求償權 | Claims % | BPS(sats) | CEBE(sats) | 來源 |
|---|---|---|---|---|---|---|---|
| 2024-Q3 | $63,000 | 252,220 | $1,900M | 12.0% | — | — | cebetracker |
| 2024-Q4 | $95,000 | 446,400 | $1,400M | 3.3% | — | — | cebetracker |
| 2025-Q1 | $85,000 | 550,000 | $8,000M | 17.1% | — | — | cebetracker |
| 2026-01 | $88,348 | 709,715 | $14,324M | 22.8% | — | — | cebetracker |
| 2026-04-12 | ~$97,000 | 780,897 | $17,370M | 22.8% | 195,726 | 151,015 | cebetracker |
| 2026-07-05 | $60,773 | 843,775 | ~$21,000M | 38.3% | 227,057 | 140,200 | cebetracker |
| 2026-08-16 | ~$63,900 | 842,137 | $21,100M | 39.8% | — | 119,309 | mnav.com |

**關於 2026-01 與 2026-04 都是 22.8% 的疑問**:我判斷是**真實巧合而非資料過期**(信心度中)。因為 Claims % = BTC 計價的求償權 ÷ BTC 持有量,1 月($88,348、claims $14.3B)到 4 月(~$97K、claims $17.4B)之間,較高的 BTC 價格把求償權在 BTC 單位下壓縮的幅度,剛好抵銷了更大的美元求償權。而且 4 月的 BPS/CEBE 自洽:(195,726 − 151,015) / 195,726 = 22.8% ✓。**推翻條件**:若實際使用的 4 月 BTC 價格明顯低於 ~$95K,則此判斷不成立。

### 5.10 已驗證的 mNAV 歷史讀數

| 日期 | BTC 價 | MSTR 收盤 | mNAV 讀數 | Tier |
|---|---|---|---|---|
| 2024-11-21 | ~$98,000 | **$543(ATH)** | ~3.4x basic(峰值) | 3 |
| 2025-11-30 | ~$91,500 | ~$247 | **0.856x basic / 0.954x diluted / 1.105x enterprise** ← 同日三讀數 | 3 |
| 2025-12-01 | ~$80,000 | ~$155(低點) | — | 3 |
| 2026-06-26 | — | $82.31(52週低) | enterprise 首次 <1.0x(6/27 前後) | 2/3 |
| 2026-08-03 | ~$63,800 | $94.86 | **0.68x basic / 1.02x enterprise** ← 跨越 1.0x 兩側 | 2/3 |
| 2026-08-10 | $64,279 | **$97.33** | **1.06x(公司 net-BPS)/ ~0.71x basic** | **1 (FWP)** |
| 2026-08-16 | ~$63,900 | — | 1.06x naive / 1.12x CEBE;52週區間 0.97–1.43x | 2 |

**2026 年 6–8 月 MSTR 日線**(Tier 2,stockanalysis.com / S&P Global,可直接寫進 fixture 測資):
```
2026-06-04 129.37   2026-06-26  82.31   2026-07-21 101.95   2026-08-05  98.37
2026-06-05 120.44   2026-06-29  92.68   2026-07-22 100.01   2026-08-06  96.85
2026-06-08 127.20   2026-06-30  86.93   2026-07-23  93.63   2026-08-07 100.01
2026-06-09 117.02   2026-07-01  93.39   2026-07-24  91.67   2026-08-10  97.33
2026-06-10 115.35   2026-07-02 100.77   2026-07-27  98.65   2026-08-11  96.09
2026-06-11 120.15   2026-07-07  97.36   2026-07-28  96.16   2026-08-12  94.83
2026-06-12 123.97   2026-07-08  93.87   2026-07-29  93.33   2026-08-13  97.10
2026-06-15 131.14   2026-07-09  93.89   2026-07-30  97.74   2026-08-14  93.04
2026-06-16 122.81   2026-07-10  94.64   2026-07-31  93.28
2026-06-17 116.56   2026-07-13  92.10   2026-08-03  94.86
2026-06-18 112.53   2026-07-14  97.58   2026-08-04  97.65
2026-06-22 109.46   2026-07-15  97.47
2026-06-23 103.84   2026-07-16  94.03
2026-06-24  94.13   2026-07-17  94.85
2026-06-25  85.33   2026-07-20  97.82
```
其他已知:52週高 $414.36(2025-08-11)、52週低 $81.81(2025-06-26 盤中)、2025-07-11 約 $434.58。

---

## 6. 驗證錨點(實作完必須通過的測試)

### 6.1 黃金測試:重現 Strategy 官方敏感度表

來源:2026-08-13 Form FWP(SEC accession `d169243dfwp`)。用 §4.2 的公式與參數,必須**精確**重現:

| BTC 價格 | 官方 Net Reserve/Share | 你的計算 |
|---|---|---|
| $40,000 | **$40.87** | 必須吻合 |
| $50,000 | **$61.97** | 必須吻合 |
| $64,279 | **$92.11** | 必須吻合 |
| $75,000 | **$114.73** | 必須吻合 |
| $100,000 | **$167.49** | 必須吻合 |
| $150,000 | **$273.01** | 必須吻合 |

驗算示範(BTC = $64,279):
```
840,447 × 64,279            =  54,023,092,713
              + 4,650,000,000 =  58,673,092,713
              − 6,754,000,000 =  51,919,092,713
              − 15,239,000,000 =  36,680,092,713
              ÷ 398,220,309   =        $92.115  ✓
```

### 6.2 其他必過檢查(同一份 FWP)

| 指標 | 官方值 | 公式 |
|---|---|---|
| mNAV | 1.06x | $97.33 ÷ $92.11 = 1.0567 ✓ |
| Gross BPS | 198,289 sats | 840,447 ÷ 423.838M × 1e8 |
| Net BPS | 143,292 sats | $92.11 ÷ $64,279 × 1e8 = 143,280(誤差 <0.01%)✓ |
| Gross BPS ($) | $127.46 | 198,289 sats × $64,279 |
| Net BPS ($) | $92.11 | ✓ |
| Amplification | 1.47x | 54.023B ÷ 36.680B = 1.4728 ✓ |
| 市值 | $38.368B | |
| 企業價值 | $55.710B | |
| BTC ARR breakeven | 3.21% | $1.736B ÷ $54.023B = 3.214% ✓ |
| BTC ARR floor | −11.53% | |
| BTC ARR hurdle | 10.77% | |
| 30D 波動率 | 64% | |
| 1Y 波動率 | 74% | |

### 6.3 Break-even 的三種算法(全部都要實作,並在 UI 標明差異)

| 定義 | 公式 | 結果 |
|---|---|---|
| Strategy 官方(扣 USD Reserve) | (21.993B − 4.65B) ÷ 840,447 | **$20,635** |
| cebetracker | 19.63B ÷ 843,775 | **$23,270** |
| mnav.com(毛額,不扣現金) | 21.05B ÷ 840,447 | **$25,054** |

⚠️ 這三個數字**都對**,只是求償權的定義不同。系統不能只顯示一個。
歷史軌跡:2020 年 $9,224 → 2026 年 $20,635–$25,054(約 2.5 倍)。

---

## 7. 圖表規格

### 7.1 主圖:三軌歷史對照(這是使用者最想要的)

X 軸為時間(2024-07 至今),**單一 Y 軸不可能容納**,所以用三個垂直堆疊的子圖共用 X 軸:

```
┌─────────────────────────────────────────────────┐
│ 子圖 1:BTC 價格($)與 MSTR 股價($)            │
│   兩條線,indexed to 100 @ 2024-11-21           │
│   → 看發散                                       │
├─────────────────────────────────────────────────┤
│ 子圖 2:mNAV 各變體(basic / enterprise / CEBE)│
│   1.0x 畫一條水平參考線                          │
│   2026-07-23 畫垂直虛線標「公司定義變更」        │
│   → 看三條線何時分岔、何時跨越 1.0x             │
├─────────────────────────────────────────────────┤
│ 子圖 3:資本結構堆疊面積圖                       │
│   converts / STRK / STRF / STRD / STRC / STRE   │
│   右軸疊 Claims % 折線                           │
│   → 看優先股何時開始吃掉普通股                   │
└─────────────────────────────────────────────────┘
   下方標記各 IPO 日期的垂直註記線
```

**顏色編碼要求**:優先股各系列用**同一色系的深淺漸層,依清償順位排序**(STRF 最深 → STRD 最淺),因為順位是真實資訊。可轉債用另一色系。普通股權益用對比色。**不要用彩虹配色**。

### 7.2 副圖

1. **Gross BPS vs Net BPS(sats/share)雙線** — 兩線之間的面積就是 phantom growth,直接視覺化。
2. **Break-even 軌跡** — 三種定義三條線,底下疊 BTC 實際價格,看緩衝空間怎麼縮小。
3. **等值線圖(contour)** — X = BTC 價格,Y = MSTR 股價,等高線 = mNAV。**畫兩張:2024-Q4 資本結構 vs 2026-Q2 資本結構**,並排對照。這一張最能直接回答「同樣的 BTC 價格,優先股讓 mNAV 地圖怎麼位移」。
4. **每季買幣的融資來源堆疊柱** — 標出哪些是 CEBE-accretive、哪些是 neutral。

### 7.3 對照表

在任一選定日期,輸出:

| mNAV 目標 | Basic 基準隱含股價 | Net/CEBE 基準隱含股價 |
|---|---|---|
| 1.0x | | |
| 1.25x | | |
| 1.5x | | |
| 2.0x | | |

2026-08-13 的正確答案(可拿來對):Net 基準 1.0x → $92.11、1.25x → $115.14、1.5x → $138.17、2.0x → $184.22、3.0x → $276.33。Basic 基準 1.0x → ~$137、1.5x → ~$206、2.0x → ~$274。

---

## 8. 已知陷阱

### 8.1 mNAV 沒有標準定義
同一天可以有 0.68x 和 1.02x 兩個「正確」答案。**每個 mNAV 值都必須攜帶 variant + date 兩個 metadata**,資料庫欄位就該這樣設計。絕對不要把公司自訂 mNAV 跟第三方 basic mNAV 混在同一條線上畫。

### 8.2 兩個不同的股數分母
Strategy 自己的 Gross BPS 用 ~423.8M「assumed diluted shares」,Net BPS 用 ~398.2M FDSO。**同一份文件裡的兩個指標用不同分母**。不要用同一個 FDSO 算兩者,會對不上官方數字。

### 8.3 面額 / 清算優先權 / 市值 三者不同
優先股必須用 **stated amount × 股數**(STRK/STRF/STRD/STRC 為 $100,STRE 為 €100),不是 IPO 發行價,也不是市價。STRC 在 2026-06-17 曾跌到 $89(低於面額 11%),市值與清算優先權差很多。

### 8.4 三個不同的「求償權總額」都在流通
- $17.4B(cebetracker,扣現金與公司持有的 STRC)
- $21.1B(mnav.com,毛額但**漏掉 STRE**)
- $22.0B(公司,毛額含 STRE:$6.754B 債 + $15.239B 優先股)

這些是定義差異不是錯誤。系統要明確選定一種並註明。

### 8.5 2026-07-23 的定義斷點
公司自己的 mNAV 在此日重新定義,官方明言前後不可比。任何用公司 mNAV 建的時間序列**必須在此斷開**,不能接成一條線。

### 8.6 STRE 的匯率風險
歐元計價的求償權,在 BTC 計價下的縮放速度受 EUR/USD 影響。需要接匯率 API(如 ECB 或 exchangerate.host)並存 as-of 匯率,不能用當前匯率回溯套用。

### 8.7 STRC 是變動利率
年度義務不能寫死。9.00%(2025-07)→ 11.50%(2026-06)→ 12.00%(2026-08)。且 2026-06-08 起改半月配息。

### 8.8 STRK 是可轉換的
STRK 可按 0.1 MSTR/股 轉換。在 Net BPS 公式裡,**價內的 STRK 應排除在求償權之外**(公司公式明言 "excluding in-the-money STRK")。這是 in/out-of-the-money 判定,需要即時股價才能決定,不是靜態參數。

### 8.9 Split
2024-08-07 的 10-for-1 分割。驗證方式:2024-11-21 ATH 應為 $543。

### 8.10 不要編故事
關於「為什麼」公司在 2026-07-23 改定義、為什麼在 1x 附近增發——除非有具名來源的直接引述,否則標記為「不知道」。已知的具名引述:
- Phong Le(*What Bitcoin Did*,2025-11-29 前後):在 mNAV 低於 1 且融資管道斷絕時,會賣 BTC 支付股利;「我不想當那個賣比特幣的公司」。
- Phong Le(X,2026-07-28):升級後的指標「為 MSTR 的增值性增發建立 1.0x 門檻」。

---

## 9. 建議實作順序

1. **先做 §6.1 的黃金測試**。把 FWP 參數寫死,實作 `net_reserve_per_share()`,確認六個 BTC 價格點全部吻合。這一步不過,後面全部白做。
2. 接 BTC 與 MSTR 日線 API,存進 `market_daily`。用 §5.10 的 MSTR 日線當 fixture 驗證資料源正確。
3. 把 §5 的資本結構表手動 seed 進 `capital_structure`,`is_estimated` 標好。
4. 實作五種 mNAV,對 §5.10 的歷史讀數做 cross-check。對不上的先找定義差異,不要急著調參數。
5. 補 §5.3 的可轉債各系列細節(從 10-Q 債務附註人工抄一次)。
6. 畫 §7.1 主圖。
7. 做 §7.2.3 的等值線對照圖 —— 這是回答核心問題的關鍵視覺。
8. (可選)接每週 8-K 做融資來源歸因。

### 給 Claude Code 的起手 prompt 建議

```
讀 MSTR_CEBE_歷史分析_建置規格.md。

先只做第一步:實作 §4.2 的 net_reserve_per_share(),用 §5 的 FWP 參數,
寫一組 pytest 驗證 §6.1 表格的六個 BTC 價格點與 §6.2 的所有衍生指標。
不要碰 API,不要畫圖,先把數學對起來。

注意 §8.2:Gross BPS 和 Net BPS 用不同的股數分母,不要共用。
```

---

## 附錄:資料可信度總表

| 資料 | Tier | 信心 | 缺口 |
|---|---|---|---|
| FWP 敏感度表與參數(§6)| 1 | 高 | 無 —— 已完全反解驗證 |
| 2026-06-30 各系列優先股餘額(§5.2)| 1 | 高 | 無 |
| 優先股 IPO 條件(§5.1)| 1 | 高 | 無 |
| USD Reserve 軌跡(§5.5)| 1 | 高 | 僅四個時點 |
| 2025 年三季優先股餘額 | 2 | **低** | 標 `[EST]`,需從各季 10-Q 補 |
| 可轉債各系列轉換價/到期日(§5.3)| — | **低** | **最大缺口,建議優先補** |
| 2024-12-31 股數 ~248M | 2 | 中 | 需從 2024 10-K 確認 |
| CEBE 錨點(§5.9)| 2 | 中 | cebetracker 自有方法論,非申報事實 |
| 歷史 mNAV 讀數(§5.10)| 2/3 | 中 | 多數未回溯至一手 |
| 2026 年 6–8 月 MSTR 日線(§5.10)| 2 | 高 | S&P Global 供資,可信 |
| BTC 各季末價格 | 2 | 中 | cebetracker 引用,建議用 API 重抓 |

**不在本文件範圍、也不建議納入模型的**:分析師目標價、對公司動機的推測、匿名消息來源的報導。
