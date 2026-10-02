# 06 — 四層架構規格

這不是現況說明,是**規格**。四層,由下往上,每一層定義:吃什麼、吐什麼、
資料長什麼樣、介面是什麼、**怎麼算通過**。它描述的形狀不隨進度改變。

> **做到哪裡、每一步撞到什麼、下一步是什麼 → [08-status.md](08-status.md)。**
> 資料夠不夠支撐結論 → [07-data-gaps.md](07-data-gaps.md)。
>
> 以前這裡有「現況 vs 設計圖」與「施工順序」兩節,而 05 與 07 也各有一份 ——
> 三份會各自過時然後互相矛盾,所以合併了。

⚠️ **這份文件的 `L1–L4` 與 [05-toolbox.md](05-toolbox.md) 的分層是兩條不同的軸。**
這裡講**資料怎麼流**(採集 → 事件 → 操作 → 階段),05 講**代數怎麼變成
可執行的宣告**(量 → 尺 → 工具 → 組合 → 歸因)。`L1–L4` 這個編號只在這裡用。

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

### 這四層是**數值解**那一欄

同一個 L1–L4 會被解兩次 —— 這份文件規格化的是**數值解**(代進真實參數),
另一欄是**公式解**(純代數,不帶任何數字),實作在 `mstr_cebe/toolbox.py`:

| 層 | 公式解 | 數值解(本文件) |
|---|---|---|
| L1 量 | $H, C, S, p$ 與 $B, E, m, A, p_0$ 的式子 | `archive` 採集 → 算出今天的值 |
| L2 工具 | 每把工具的 $\Delta B/\Delta E$ 與判準 | `events` 把申報變成具名動作 |
| L3 配對 | 組合的代數(ATM 配買幣、賣幣配回購…) | `operations` 依文件敘述實際配對 |
| L4 時間 | 逐日鏈結、四層歸因的推導 | `phases` 算出實際的歸因與階段 |

**L1–L4 因此不是工程上的任意切分,它就是模型本身的四個層次。**
兩欄走同一條構築線,改了任一欄而另一欄沒跟上,`verify.py` 與
`tests/test_toolbox.py` 會紅 —— 那正是「代數是可以被打臉的宣告」的意思。

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

### 粒度

同一批動作會被三份文件各講一次 —— 8-K 的週表、10-Q 的季表、10-K 的年表。
**描述的是同一批動作,只是粒度不同**,混在一起加總就會重複計算。
所以 `granularity` 是欄位而不是註解,而且 `all_events()` 預設只給週粒度 ——
要季或年的必須明講。

三者之間的優先規則(粗只能補洞)在 [03-data.md §2](03-data.md)。

⚠️ **粒度描述的是流量涵蓋的期間。觀測是瞬時的存量,沒有期間**,
一律是 `'instant'`,由 `Event.__post_init__` 強制,不受粒度過濾器管。
讓觀測繼承同一列流量的粒度是歸類錯誤,而且有實害 —— 見
[03-data.md §5](03-data.md)。

季頻資料來自 SEC 的 XBRL companyfacts,不是硬解 10-Q 的 HTML 表格。
同樣的數字 SEC 已經結構化發布,連期間起訖與來源 accession 都標好了。

**兩個會算錯的陷阱,都寫進 `_discrete_periods()` 並有測試守著:**

1. **大部分事實是年初至今的累計**,不是單季 ——
   `2025-01-01→06-30 $2,948M` 是上半年,不是 Q2。直接加總會把同一筆錢
   算好幾次,所以同年度內要逐筆相減。
2. **有些事實本身就是單季**(起日不是年度起日),與相減出來的期間重疊。
   公司自己報的優先(`extraction='stated'`),相減出來的是 `'derived'`。

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

## 8. 這份設計刻意不做的

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
