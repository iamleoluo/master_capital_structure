# 06 — 系統重建設計圖

這不是現況說明,是**規格**。四層,由下往上,每一層定義:吃什麼、吐什麼、
資料長什麼樣、介面是什麼、**怎麼算通過**。

現在的實作是「寫得出來就好」的版本,它證明了模型成立,但地基撐不住接下來
要蓋的東西。這份文件說明要換掉什麼、為什麼、以及換的順序。

---

## 0. 四層是什麼

```
L4  階段      把時間序加進來:這幾個月的結構效應是什麼,對上股價
L3  資本操作  配對:賣幣+STRC 回購、ATM+STRC 回購、賣幣+USD 儲備
L2  事件      有名義的原子動作:這是一筆 buyback、這是一筆 ATM
L1  採集      SEC 檔案、股價 API —— 原始資料本身
```

往上一層,**資訊減少而意義增加**。L1 是事實,L4 是詮釋。
這個方向不可逆,也不能跳層。

---

## 1. 現在的地基有三個洞

動手之前要先承認問題,否則會在爛地基上蓋新東西。

### 洞一:沒有原始檔案庫

`web/raw/*.json` 存的是**解析結果**,不是原始文件。8-K 的 HTML 從來沒有被
留下來。後果:

- 解析器一有 bug,就得**重新打 SEC** 才能修
- 版型迴歸沒有固定樣本(03-data.md 說「快取讓版型迴歸有固定樣本」,
  那句話其實只對了一半 —— 留下來的是輸出,不是輸入)
- 無法回答「這個數字當初是從哪一份文件的哪一段解出來的」

### 洞二:沒有出處

```json
["2024-09-12", 244800]
```

這是 `btc_holdings_weekly.json` 的一筆。沒有 accession number、沒有 URL、
沒有抓取時間、沒有雜湊。**244,800 這個數字無法被稽核。**

### 洞三:存的是週聚合,不是動作

`atm_weekly.json` 是「這一週各券種合計募了多少」。但使用者要的是
**「這是一筆 ATM」** —— 有日期、有券種、有股數、有價格、有出處的一個動作。

現在「名義」藏在**檔名**裡(`repurchase_weekly.json` 表示這些是回購),
而不在資料裡。所以沒有辦法問「2026 年 8 月有哪些動作」,只能問
「回購檔案裡 8 月那幾週是什麼」。

### 附帶:層次混用

`btc_transactions` 資料表有一欄 `cebe_effect TEXT` —— 那是**解讀**,
卻存在原始資料旁邊。`mnav_readings` 資料表存的是**算出來的值**。
兩者都把 L2/L3 的東西塞進了 L1 的位置,改一次口徑就得回頭改資料庫。

---

## 2. 貫穿四層的三條規則

先定規則,因為它們決定了每一層的形狀。

### 規則一:出處往上流

**L4 的任何一個數字,都要能追到 L1 的一份文件。** 不是「大概來自 8-K」,
是「來自 accession 0001050446-26-000123 的第三張表第七列」。

實作上就是每一層的紀錄都帶著下一層的 id:
`phase → [op_id] → [event_id] → doc_id`。

### 規則二:每層可以獨立重放

刪掉 L2 以上的全部資料,只憑 L1 的檔案庫要能完整重建。
L3 壞了不必重抓 L2,L4 換算法不必重跑 L3。

這條的用處在**反事實**:換一套配對規則,重跑 L3 與 L4,
兩組結果可以直接比較 —— 因為 L1/L2 完全沒動。

### 規則三:信心度單調遞減

| 層 | 性質 | 錯誤長什麼樣 |
|---|---|---|
| L1 | 事實 | 抓漏、抓錯版本 |
| L2 | 解析 | 版型失配、欄位誤判 |
| L3 | **推論** | 配錯對 |
| L4 | 詮釋 | 分期分錯 |

L3 是第一個**不可能被證明**的層 —— 現金是可替代的,你永遠無法證明
「賣幣換到的那筆錢」就是「拿去回購的那筆錢」。所以 L3 的輸出必須帶
信心度,而且前端要看得出某個結論是來自哪一層。

---

## 3. L1 — 採集

### 職責

把外部世界的東西**原封不動**存下來,並記錄它是什麼、什麼時候拿的。
**不解析、不計算、不詮釋。**

### 資料結構

```sql
CREATE TABLE documents (
  doc_id       TEXT PRIMARY KEY,   -- sha256(content) 前 16 碼,內容定址
  source       TEXT NOT NULL,      -- 'sec_8k' | 'sec_xbrl' | 'sec_fwp' | 'binance' | 'yahoo'
  url          TEXT NOT NULL,
  accession    TEXT,               -- SEC 專用,可為 NULL
  filed_at     TEXT,               -- 文件自己宣稱的日期(不是抓取日)
  fetched_at   TEXT NOT NULL,
  media_type   TEXT NOT NULL,      -- 'text/html' | 'application/json'
  sha256       TEXT NOT NULL,
  content      BLOB NOT NULL       -- 原文。壓縮存,不要改寫
);
CREATE INDEX idx_doc_source_filed ON documents(source, filed_at);
```

**內容定址**是關鍵:同一份文件重抓不會產生第二筆,而內容一旦變了
(SEC 有改檔的前例)就會是新的 `doc_id`,舊的留著。歷史因此不可被悄悄改寫。

### 介面

```python
def fetch(source: str, since: date) -> list[DocId]:
    """抓取並歸檔。已經有的不重抓。回傳這次新增的 doc_id。"""

def read(doc_id: str) -> bytes:
    """從檔案庫取原文。解析器只透過這個拿資料,永遠不碰網路。"""
```

### 驗收條件

> **把 L2 以上的資料全部刪掉,只跑解析,能重建出一模一樣的下游。**

這條成立,就代表 L1 真的是完整的;不成立,就代表某個數字其實來自網路
而不是檔案庫。

---

## 4. L2 — 事件

### 職責

把文件解析成**有名義的原子動作**。這一層是「資料」變成「動作」的地方 ——
使用者說的「寫進資料庫,它就有名義了」,指的就是這裡。

### 資料結構

```sql
CREATE TABLE events (
  event_id     TEXT PRIMARY KEY,   -- hash(doc_id, kind, instrument, row_no) 冪等
  kind         TEXT NOT NULL,      -- 見下表
  instrument   TEXT NOT NULL,      -- 'BTC' | 'MSTR' | 'STRC' | 'STRF' | 'CONV_2029' ...
  effective_at TEXT NOT NULL,      -- 動作發生日
  qty          REAL,               -- 股數 / 顆數 / 面額,單位看 unit
  unit         TEXT,               -- 'shares' | 'BTC' | 'USD_par'
  usd          REAL,               -- 現金金額(流入為正、流出為負)
  unit_price   REAL,               -- 可由 usd/qty 推得,存著方便查核
  doc_id       TEXT NOT NULL REFERENCES documents(doc_id),
  locator      TEXT NOT NULL,      -- 文件裡的位置:'table[2].row[7]'
  extraction   TEXT NOT NULL,      -- 'stated' | 'derived'
  confidence   REAL NOT NULL       -- 0..1
);
```

### 事件種類,以及它對應哪一把工具

這張表是 L2 與 `toolbox.py` 的**接點**:

| kind | instrument | 對應 Tool | 參數怎麼來 |
|---|---|---|---|
| `btc_purchase` | BTC | `BUY_BTC` | `c = usd` |
| `btc_sale` | BTC | `SELL_BTC` | `x = qty` |
| `atm_issue` | MSTR | `COMMON_ATM` | `n = qty, P = unit_price` |
| `atm_issue` | STRx | `ISSUE_PREFERRED` | `c = usd, F = qty × 100` |
| `preferred_repurchase` | STRx | `BUYBACK_PREFERRED` | `c = -usd, F = qty × 100` |
| `convert_repurchase` | CONV_* | `BUYBACK_PREFERRED` | `c = -usd, F = qty` |
| `convert_conversion` | CONV_* | `CONVERT_CONVERSION` | `F = qty, n = 轉換股數` |
| `dividend_payment` | STRx | `CARRY` | `c = -usd` |
| `interest_payment` | CONV_* | `CARRY` | `c = -usd` |
| `reserve_change` | USD | (無,是狀態觀測) | — |

**一個事件就是「一把工具 + 參數 + 日期 + 出處」。** 這讓 05 那份工具箱
從代數定義變成可以被資料驅動的東西:

```python
Event  →  (Tool, Params, effective_at, doc_id)
```

`reserve_change` 刻意不對應工具 —— 它是**狀態觀測**而不是動作,
用來校正 L1 沒有直接給的 USD 流動性。把觀測與動作分開,
才不會把「餘額變了」誤當成「公司做了什麼」。

### 冪等性

`event_id = hash(doc_id, kind, instrument, row_no)`。同一份文件重解兩次,
得到同一組 id。解析器改版之後可以整批重跑,不會產生重複。

### 驗收條件

> 每一個事件都能指回一份文件的一個位置;
> 同一批文件重解兩次,輸出逐位元組相同。

---

## 5. L3 — 資本操作

### 職責

把事件**配對成有意圖的操作**。這是使用者說的第三層:
「賣幣 + STRC buyback」是一個操作,不是兩件事。

### 這一層的本質限制

**現金是可替代的。你永遠無法證明賣幣換到的那筆錢就是拿去回購的那筆錢。**

所以 L3 不宣稱事實,它**提出配對並附上證據**。這不是缺陷,是誠實 ——
問題在於必須讓它在介面上看得出來,不能混進 L1/L2 的數字裡假裝同級。

### 資料結構

```sql
CREATE TABLE operations (
  op_id       TEXT PRIMARY KEY,
  combo_id    TEXT NOT NULL,     -- toolbox 的組合 id,或單一工具 id
  window_lo   TEXT NOT NULL,
  window_hi   TEXT NOT NULL,
  params      TEXT NOT NULL,     -- JSON:餵給 Tool 的參數
  confidence  REAL NOT NULL,
  rule        TEXT NOT NULL,     -- 哪一條規則認定的
  evidence    TEXT NOT NULL      -- JSON:為什麼認定它們是一組
);
CREATE TABLE operation_events (
  op_id    TEXT NOT NULL REFERENCES operations(op_id),
  event_id TEXT NOT NULL REFERENCES events(event_id),
  role     TEXT NOT NULL,        -- 'source' | 'use'
  PRIMARY KEY (op_id, event_id)
);
```

### 配對規則

每條規則是「在一個窗口內,找到角色互補、金額對得上的事件」:

| 規則 | 來源事件 | 用途事件 | 對帳條件 |
|---|---|---|---|
| `sell_to_buyback` | `btc_sale` | `preferred_repurchase` | 賣幣所得 ≈ 回購成本 |
| `atm_to_buyback` | `atm_issue(MSTR)` | `preferred_repurchase` | 淨募資 ≈ 回購成本 |
| `preferred_to_btc` | `atm_issue(STRx)` | `btc_purchase` | 淨募資 ≈ 買幣金額 |
| `sell_to_reserve` | `btc_sale` | `reserve_change(+)` | 賣幣所得 ≈ 儲備增加 |

信心度由證據強度決定:

- **高** — 同一份 8-K,金額誤差 < 5%,且敘述句同時提到兩者
- **中** — 同一份 8-K 或同一週,金額誤差 < 15%
- **低** — 只有時間相近

### 三條不可妥協的性質

**單一事件也是一個操作。** 配不到對的不是失敗,它就是一個單工具操作。
這讓下游永遠只需要處理一種型別。

**未配對的必須顯性。** 現金流對不起來的部分留成殘差,
**不准攤進任何一個操作**。這條就是現在 `other` 那一項的正式化 ——
攤進去會讓其他操作的數字看起來比實際精確。

**配對不得無中生有。** 規則只能把既有事件綁在一起,不能創造事件。

### 驗收條件

> Σ(所有操作的現金流) + 殘差 = 觀察到的 USD 流動性變化。
>
> 且殘差佔比要能報出來 —— 超過門檻時,下游必須拒絕給操作層級的結論
> (現在 `opsOk` 做的事)。

---

## 6. L4 — 階段

### 職責

加入時間序:**這幾個月的操作組合,產生了什麼結構效應,對應到什麼股價結果。**

### 階段的定義

現在的分期是人工挑日期(`chronicle.ERAS`)。設計圖要換成:

> **階段 = 工具組合的穩定期。邊界在「組合改變」的地方,不在新聞發生的地方。**

這與 00-purpose 的定位一致 —— 這是決策工具,要看的是
「哪一根槓桿在當下是划算的」,不是「公司又被什麼事件打到」。

具體做法:把每週的操作換算成**工具組合向量**
(各工具在該週的資本佔比),當主導成分改變且維持 $k$ 週,
就是一個邊界。`structural_watch()` 已經是這件事的原始版本 ——
它會在求償權大幅變動時示警,那就是組合改變的一個徵兆。

### 每個階段要產出什麼

```python
@dataclass
class Phase:
    lo: date; hi: date
    thesis: str                  # 人工撰寫,唯一允許人工的欄位
    mix: dict[str, float]        # 工具組合佔比
    layers4: dict[str, float]    # 四層歸因(01-model §9)
    efficiency: dict[str, float] # 各操作的資本效率(05 §8)
    price: Delta                 # 股價結果
    residual_pct: float          # 這一段有多少對不起來
```

`thesis` 是唯一人工的欄位,而且它**不准包含數字** ——
數字一律由管線填入,這樣資料更新時敘述不會與圖表打架
(這條規則現在就存在於 `chronicle.py`,設計圖把它保留)。

### 驗收條件

> 階段邊界可以從 L3 重算出來(不是手寫常數);
> 每一段的四層加總 = 該期股價報酬(現在的 `(4.2)` 檢查)。

---

## 7. 層與層之間的型別

```
L1  Document(doc_id, source, filed_at, content)
         │  parse
         ▼
L2  Event(kind, instrument, qty, usd, doc_id, locator, confidence)
         │  ≡ (Tool, Params, date, 出處)
         │  match
         ▼
L3  Operation(combo_id, [event_id], params, rule, evidence, confidence)
         │  ≡ (Tool, Params) —— 組合與單一工具同型
         │  phase
         ▼
L4  Phase(mix, layers4, efficiency, price, residual_pct)
```

**L2 與 L3 最後都收斂成同一個型別 `(Tool, Params)`** ——
這就是 05 那份工具箱「組合在型別上封閉」的用處:
歸因與模擬完全不需要知道手上拿的是一個事件還是一組配對。

---

## 8. 現況 vs 設計圖

> **進度**:第 1–5 步已完成(分支 `rebuild/l1-document-archive`)。
> 160 份 8-K 已歸檔並內容定址,四支解析器改讀檔案庫(斷網可跑),
> 916 個事件由文件推出,週聚合改成視圖。下面的表格反映完成後的狀態。

| 層 | 現況 | 缺口 |
|---|---|---|
| L1 採集 | ✅ 8-K 內容定址歸檔、有出處、解析與抓取已分離 | ⚠️ 報價 API 尚未歸檔 |
| L2 事件 | ✅ 916 個事件、動作／觀測分家、冪等 id、可重放 | ⚠️ locator 是邏輯位置(`repurchase/2026-08-02/STRC`)而非文件內的實體位置 |
| L3 操作 | ✅ 配對器與 `operations` 表;192 個操作,對帳零差額 | ⚠️ 只實作 `sell_to_buyback`;歸因尚未改吃操作(仍是聚合差分) |
| L4 階段 | 四層歸因完整且有斷言 | ⚠️ 分期是手寫常數,不是從組合算出來 |

**`toolbox.py` 是唯一已經符合設計圖的部分。** 其餘三層都要重做,
但不是重寫 —— 是把既有的解析邏輯搬到新的資料結構上。

---

## 9. 施工順序

原則:**每一步的驗收條件都是「既有的數字不能變」。**
這讓重構可以隨時停下來,而且錯了會立刻被現有的 23 條恆等式與 227 個測試抓到。

1. ~~**建 `documents` 表,補抓歷史文件。**~~ ✅ **已完成**
   160 份 8-K(18.2 MB 原文壓成 1.7 MB)、內容定址、有出處。
   驗收通過:`build_data.py` 的輸出逐位元組不變。
   那個原本無法稽核的 `["2024-09-12", 244800]`,現在能指回
   accession `0001193125-24-218462` 的原文句子。
   一個當初沒想到的取捨:sqlite 每加一份就整檔重寫,git 存不了差異,
   所以**內容不進版控、稽核軌跡進**(`web/archive/manifest.json`,
   每列有 url 與 sha256,任何人都能自己抓來對)。
2. ~~**解析器改讀檔案庫。**~~ ✅ **已完成**
   四支解析器改用 `archive.iter_8k()`,並刪掉各自重複的候選清單邏輯
   (原本四支各維護一份「抓 submissions → 篩 7.01/8.01 → 組 URL → 下載」)。
   驗收通過:封死 socket 之後仍跑得完,且**五份解析結果與 committed 的
   `web/raw/*.json` 逐筆相同**;下游 `app/data/*.json` 逐位元組不變。
   測試帶一個對照組,確認封鎖本身是有效的 —— 否則那個驗收沒有鑑別力。
   過程中補了一個欄位 `items`(SEC 對該份申報公布的 item 代碼),
   因為四支解析器都靠它篩選;它與 accession 同類,是文件的中繼資料而非衍生值。
3. ~~**建 `events` 表,解析器改吐事件。**~~ ✅ **已完成**
   916 個事件(動作 419、觀測 497),週聚合改成 `weekly_*()` 視圖。
   驗收通過:五份視圖與 `web/raw/*.json` **逐筆相同**,下游逐位元組不變。

   三件實作時才看清楚的事:

   - **動作與觀測必須在 schema 裡分家。** 持有量、USD 儲備、ATM 剩餘額度、
     回購剩餘授權都是**觀測**,沒有對應工具。混進動作就會把「餘額變了」
     讀成「公司做了什麼」。`family` 因此是欄位而不是註解。
   - **「後蓋前」原本藏在 dict 覆寫的順序裡。** 同一週被多份 8-K 提到時取
     最新那份 —— 現在是 `_latest_per_period()`,顯性而且可測試。
   - **`total_m: null` 與「沒有這個欄位」不是同一件事。** 重建視圖時漏掉
     這個區別,70 筆裡有 1 筆對不上。這種等級的差異只有逐筆比對抓得到。

   附帶收穫:資料現在長得讓 L3 看得見配對。2026-08-09 賣幣 \$108,602,780、
   同週回購 \$108,600,000 —— 差 0.0026%,幾乎確定是同一筆操作。
4. ~~**`build_operations()` 改由事件 + Tool 產生。**~~ ✅ **已完成(但只完成一半,
   而且另一半是這一步的發現)**

   完成的部分:歸因的資金流參數全部改由 `events.flows_between()` 算出來,
   不再讀 `web/raw/*.json`。**559 個起點逐一位元級比對,零差異**,
   五份輸出與 committed 版本逐位元組相同。所以歸因的每一個參數現在都能沿著
   事件 → 文件追回出處。

   沒完成的部分,以及為什麼:**現行的操作表根本不是一組工具套用**,
   它是一組長得像工具的<b>聚合差分</b>。實際改寫時撞到兩堵牆:

   - `atm` 的參數是 (n, P),但這裡只有「整段期間的募資總額」與「股數淨變動」,
     而股數淨變動混了轉股與庫藏,**本來就不等於 ATM 發出的股數**。
     實測有 6 個區間 `d_shares` 為零卻募了上億美元(例如起點 2026-08-21,
     募資 \$2,609M),硬套 `n=0` 會讓求償權的減少整個消失。
   - 即使 `d_shares` 不為零,`n × (raised/n) ≠ raised`,來回一趟就掉精度。
   - `btc` 是買進與賣出的淨額加上獨立觀測到的持幣變動,不是單一動作。

   所以這一步改成:**算術路徑維持精確,工具的對應關係改成可驗證的斷言**
   (`check_operations_against_tools`)。三項參數化精確的(`buyback`、
   `carry`、`pref_issue`)精確驗,符號寫反會被抓到 —— 測試帶反證。

   真正的「由工具產生」要等**逐事件套用**,而那會改變數字,
   所以它屬於第 5 步之後,不屬於這一步。這件事本身就是設計圖該記的東西:
   **聚合差分與工具套用不是同一種東西**,先前把它們看成一樣是判斷錯誤。
5. ~~**建 `operations` 表與配對器。**~~ ✅ **已完成**
   192 個操作。驗收通過:**193 個動作全部被涵蓋、現金流差額 \$0.00、
   沒有重複計算**。

   最重要的決定是規則的依據換了:**配對看文件寫的用途,不看金額相似度。**

   理由是資料說的。把「同一週同時出現賣幣與回購」當訊號,只有 1 週金額對得上
   (2026-08-09,差 0.0026%),其餘來源都遠大於用途 —— 因為一週裡多個來源
   同時供給多個用途。用金額去配等於在猜,那正是 §5 禁止的「無中生有」。

   但 8-K 的敘述句直接寫了用途,有時連金額都逐筆寫:
   *"\$52.4 million ... to fund dividends ... and \$52.3 million ... to fund
   repurchases of STRC Stock"*。那是 `stated`,不是推論。所以分配句式的解析
   放進 L2(文件事實),L3 只讀事件。

   第二個決定來自 2026-08-02:文件寫明 \$52.3M 用於回購,但**那週回購總額
   \$81.2M** —— 賣幣只支應了約 64%,其餘來自 ATM。所以記帳分兩種:

   - **全額支應**(金額差 < 5%)→ 兩邊合併成組合操作,各自不再單獨出現
   - **只支應一部分** → 兩邊維持獨立,文件的說法掛在賣幣那一筆上

   硬合併會吃掉另一個資金來源;讓兩邊各算一次又會重複計算。
   記帳規則因此是**每個動作事件恰好屬於一個操作**。

   用詞修正:原本寫成「部分資助」是錯的 —— 中文的「資助」是贊助、補助,
   而這裡講的是「這筆錢拿去支付那筆開銷」,應該是**支應**。
6. **階段改由組合向量算出。** 先跑出來與現在的四段比對,
   差異要能解釋才換掉。
7. **前端的 `leverage.ts` 改讀 JSON。** 修掉 CLAUDE.md 第一條規則的違反。

前三步只動地基不動結論,**可以先做而不影響任何現有頁面**。

---

## 10. 這份設計刻意不做的

**不做即時。** 8-K 一週一份,沒有任何理由讓這條管線變成串流。
批次 + 重放能力比低延遲有價值得多。

**不做通用 ETL 框架。** 來源就是 SEC 與兩個報價 API。
抽象成外掛式的資料源只會讓解析錯誤更難找。

**不讓 L3 的配對自動進入結論。** 配對是推論,要帶信心度上去,
而且介面要看得出來。寧可顯示「這兩筆可能是一組」,
也不要悄悄把它算成事實。

**不在資料庫裡存算出來的值。** `mnav_readings` 與 `cebe_effect` 是現在的
反例 —— 口徑一改就得回頭改資料。**存事實,算的東西每次重算。**
唯一的例外是 `app/data/*.json`,那是給前端的快照,不是真實來源。
