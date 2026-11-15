# 網站規則

頁面的順序、標題、段落、圖的種類可以改。這一頁的規則不能隨那一次改版一起鬆掉。每一條都寫它怎麼**自動**失敗，而不只是寫在文件裡。

層的定義在 [ARCHITECTURE.md](ARCHITECTURE.md)。表在 [DATA_MODEL.md](DATA_MODEL.md)。2026-11-15 的頁面草圖在 [REORG_PLAN.md](REORG_PLAN.md) §3，那是第 7 層的一個例子，不是這些規則的例外。

已經存在、遷移時要接上而不是重寫的守門：

| 守門 | 它已經在做的事 |
|---|---|
| `tests/test_lecture_is_formula_only.py` | 推導頁不得 import 觀測，正文不得出現具體讀數 |
| `tests/test_events.py` | 週表的 accession 重解析後，文件裡真的有那一週 |
| `tests/test_golden_fwp.py` | 釘死的 FWP 情境 |
| `tests/test_scenario.py` 與 `app/test/scenario.test.ts` | Python 與頁面上的情境數學同一組黃金值 |
| `web/build_data.py` 的 `_layers4` | 四層對數和與股價比的差必須 `< 5e-4` |
| `tests/test_reference_links_resolve.py` | 文件之間的連結要指得到 |

---

## 1. 什麼可以改，什麼不能

| 可以改，不必動登錄與黃金值 | 改了就必須在同一份 diff 裡看見定義與黃金值 |
|---|---|
| 路由順序、頁面標題、句子 | 指標的式子、單位、`basis` |
| 一頁要用哪些**已登錄**的指標 | 新增或廢除一個 `metric_id` |
| 圖是線、階梯還是表 | 入庫單位，或 NULL 與 0 的約定 |
| 文章怎麼寫 | 求償權的預設口徑、兩個 mNAV 的定義 |
| 窄螢幕的選單長什麼樣 | 哪一支 Python 函式是該指標的實作 |

判準：這次提交若只改 `app/src/pages/**` 與樣式，指標黃金與 `data/schema.json` 必須原封不動。反向也成立：只改措辭的提交若讓黃金值變了，建置失敗。

---

## 2. 規則

### R1. 頁面跟指標的 id 要數，不跟原始欄位要數

頁面、元件、圖表向指標介面要 `claims.cebe` 這種 id。它們不讀 `daily.debt`、不把兩欄相加。

今天違反的地方：`app/src/components/explorer.ts`（債務 + 優先股，沒減現金）、`app/src/pages/board/quantities.ts`（頁面上再減一次現金）、`app/src/charts/leverage.ts` 的 `latestBasis()`、`web/build_data.py` 的 `_chain_increments`（建置腳本裡的第三份式子）。

**強制。** `app/src/pages/**` 與 `app/src/components/**` 禁止出現 `daily.`、`weekly.` 以及對 `debt`、`pref_total`、`cash`、`held`、`shares` 的運算子。檢查是一支掃原始碼的測試（與講義那支同一種寫法），建置時跑。圖的座標縮放只准出現在 `app/src/lib/scale.ts` 與 `app/src/charts/**`，而且圖表拿到的已經是指標序列，不是原始欄位。`build_data.py` 裡對求償權的運算必須是對 `net_senior_claims_usd` 的呼叫；測試用抽象語法樹或簡單的禁用字串清單擋掉再寫一次 `debt + pref`。

### R2. 一個式子只有一處實作

指標登錄的 `impl` 是唯一的 Python 路徑，例如 `mstr_cebe.core.net_senior_claims_usd`。TypeScript 不另寫一份。

情境滑桿今天是唯一還在瀏覽器裡做金融計算的地方（`leverage.ts`，`REORG_PLAN` §1.1）。它的輸出已經有黃金檔。遷移完成前，這支檔案是登錄裡的**指名例外**，例外清單空了才能刪這條註記。新的滑桿不能再成為第二個例外。

**強制。** 登錄裡每個 `impl` 必須真的可 import。投影上的該欄與函式輸出逐日比較，容差寫在登錄（恆等式那條用相對誤差，不用「大概」）。`app/src` 裡若出現第二個 `function amplification` 或對 `claims_pct` 做 `1 / (1 - x)`，掃描測試失敗。`core.amplification`（FDSO 與 net reserve）與 `build_data.py` 現在的 `1 / (1 − claims_pct)` 必須是兩個 id，不能共用名字。

### R3. 畫面上的數帶著截至日與出處

讀者看見的每一個金融數字都來自信封，不來自一個裸的 `number`。

```ts
type Unit = "USD" | "EUR" | "BTC" | "sats" | "share" | "ratio" | "year";
type Method =
  | "observed" | "step" | "carry" | "linear"
  | "spliced" | "reconstructed" | "assumed";

interface Value {
  metric: MetricId;          // 登錄產生的聯集，不是 string
  value: number | null;
  unit: Unit;
  asOf: string;              // effective_at
  filedAt: string | null;
  method: Method;
  basis: Readonly<Record<string, string>>;
  sources: readonly string[]; // doc_id 或 event_id；assumed 才准空
}
```

格式化函式的簽名是 `format(v: Value): string`，不接受裸數字。`null` 顯示成空，不顯示成 0。`method` 為 `carry`、`linear`、`spliced`、`reconstructed` 時，元件必須把這個字渲染出來（「沿用 2026-06-30」，而不是一顆蓋住整頁的「±93 天」）。

**強制。** 元件的 props 類型就是 `Value`，`tsc` 擋掉傳 number。另外一支 DOM 契約測試：樣式類 `.metric` 的節點必須有 `data-metric`、`data-as-of`、`data-method`。沒有這些屬性的數字元件編譯不過，因為型別上不存在另一種元件。

### R4. 單位是類型的一部分

入庫與指標用 [DATA_MODEL.md](DATA_MODEL.md) 第 3 節的單位。頁面不把「十億」乘回去再相加，也不把 sats 拿去乘股價。

**強制。** `format` 依 `value.unit` 分支，呼叫端不能指定另一個單位。測試拿 `unit: "BTC"` 的值去走美元格式化，預期型別錯誤。投影若仍暫時用十億美元，登錄的 `scale` 只存在於產生 `Value` 的那一個模組；頁面檔案裡出現 `1e9` 或 `1e8` 即失敗。

### R5. 面額與市價是不同的指標

`pref.STRC.par` 的輸入是清算優先權。`price.STRC` 的輸入是收盤價。沒有一支指標把兩者相加。STRE 沒有 `price.STRE` 的觀測時，該指標是 `null`，不拿 100 填上。

**強制。** 登錄的 `inputs` 列出允許的 `measure`。檢查器拒絕一份 `inputs` 同時含 `liquidation_preference_native` 與 `close`，除非 `impl` 是明確標成「價對面額」的比率（`price.STRC / par` 這種），而且輸出單位是 `ratio`。`stre` 價格欄全為 `null` 的測試維持；出現 0 即失敗。

### R6. 口徑寫在 id 裡

`claims.cebe` 的定義就是 `ClaimsBasis.CEBETRACKER` 與 `CashSource.BALANCE_SHEET`。頁面不傳口徑。要看毛額，用另一個 id `claims.company`，標題由登錄的 `label` 提供，頁面不能另寫一個「求償權合計」。

basic mNAV 與 CEBE mNAV 是 `mnav.basic` 與 `mnav.cebe`。文案可以解釋它們，元件不能有一個叫做 `mnav`、不帶變體的 props。

**強制。** `MetricId` 由登錄生成，沒有裸的 `mnav`。`build_data.py` 呼叫 `mnav(...)` 與 `net_senior_claims_usd(...)` 時必須寫明列舉，禁止依賴預設引數；用一次掃原始碼的測試看呼叫點。投影欄 `mnav_cebe` 若改名或改口徑，`definition_rev` 必須一起變，否則與黃金 diff 的測試失敗。

### R7. 新鮮度按欄位走

不發布「這一列最舊的那個欄位」當整列的新鮮度。持幣的預設 `method` 是 `step`。債務在最後一個季報之後是 `carry`。`linear` 只出現在登錄允許插值的指標上。

**強制。** 投影裡若還有 `stale` 這種跨欄位整數，schema 檢查失敗。每個 `metric_value` 的 `as_of <= date`，且 `method` 屬於該指標的允許集合。持幣指標的允許集合不含 `linear`。

### R8. 假設與歷史分層

滑桿的輸出是 `method: "assumed"`，`sources` 為空，視覺上跟歷史讀數分開。預設槓桿下限若不是當天的 `amp`，旁邊的字來自登錄的 `label`，不能看起來像 2026-10-01 的讀數。

**強制。** 同一頁元件若同時接收歷史 `Value` 與假設 `Value`，型別上是兩個 props，不能塞進同一個陣列。假設值的黃金檔沿用 `scenario.test.ts`：改了滑桿公式而沒更新黃金，Vitest 失敗。

### R9. 導覽來自頁面登錄

`app/src/main.ts` 不再手寫路由陣列。登錄一頁一列：

```json
{
  "pages": [
    {
      "id": "now",
      "path": "/",
      "type": "reading",
      "title": "現在",
      "order": 10,
      "question": "今天這家公司長什麼樣",
      "metrics": ["btc.held", "price.mstr", "mnav.basic", "mnav.cebe", "claims.cebe"],
      "redirectFrom": []
    }
  ]
}
```

調整順序只改 `order`。舊路徑寫在 `redirectFrom`，由路由器轉走。未知路徑的行為寫在登錄的預設頁，不隱含「落到陣列第一筆」（這是 `app/src/router.ts` 今天的行為）。

**強制。** 生成路由的測試：登錄裡每個 `path` 唯一；`app/src/pages` 下每個頁面模組的 id 都在登錄裡，登錄裡的 id 都有模組。`redirectFrom` 有一組單元測試，舊 hash 進得了新頁。漏登記的檔案讓 `tsc` 或這支測試失敗。

### R10. 頁面只有四種類型

| `type` | 可以放 | 不可以放 |
|---|---|---|
| `reading` | 登錄裡點名的指標、圖、一句這頁在問什麼 | 自己的加減、沒登記的原始欄位 |
| `method` | toolbox 產生的公式。現有 `pages/lecture/*` | 任何觀測。這就是 `test_lecture_is_formula_only.py` 的對象 |
| `note` | 文章。數字只用釘 | 手打的「$14.76B」這類會過期的字面值 |
| `source` | 文件、粒度、finding、重建清單 | 第二套敘事結論 |

`reading` 頁開頭的三行來自登錄，不由各頁複製貼上：這頁的 `question`、它用到的每個指標的 `asOf` 與 `method`、`claims` 相關指標的 `label`（口徑那句）。算法連結指向 `type = method` 的頁，不佔主導覽的第一個順位，除非登錄的 `order` 把它排到那裡。排到那裡是允許的改動；口徑句子改由頁面作者重寫則不允許。

**強制。** `method` 沿用現有講義測試，目錄改成「登錄裡 `type=method` 的模組」，避免有人換一個資料夾就繞過。`reading` 頁的 `metrics` 必須是 `MetricId` 的子集，多寫一個 id，生成型別失敗。`note` 見 R11。

### R11. 文章裡的數字是釘，不是打字

大事記的指標今天已由 `build_chronicle` 重算，正文不該再嵌一套會過期的數。文章（`posts`、階段的 `body`）若要引用一個數，寫釘：

```text
{{metric:claims.cebe@2026-10-01}}
```

建置把它換成該日的格式化值，並在 HTML 上留下 R3 的 data 屬性。釘指不到的 id 或日期，建置失敗。人想寫一個模型裡沒有的數，必須先登錄指標，或明確標成引用外部句子（出處是 URL，不是 `metric`）。

**強制。** 一支測試掃 `posts` 與 `chronicle` 的正文：出現貨幣或顆數的字面值（`$` 加數字、`顆` 前的數字）且不在釘的白名單裡，即失敗。白名單只放文件引文，每條有 URL。這與講義測試的精神相同，對象是數值解的文章。

### R12. 出處是 id，不是一句話

`sources` 裡的每個 id 必須存在於 manifest 或事件匯出。週表點回 8-K 的行為保留，並擴到每一個 `reading` 上的數：至少能展開到 `doc_id`。行情在原始回應還沒歸檔時，`sources` 允許是 `binance:YYYY-MM-DD` 這種暫定 id，登錄把這類 id 標成 `provisional`。暫定 id 不能用在持幣、債務、現金上。

**強制。** 沿用並加廣 `test_events.py`：投影裡每個非 `assumed`、非 `provisional` 的 source 都能在 manifest 找到，並且抽樣重解析仍得到同一個 `value`。`provisional` 出現在 `btc.held` 或 `claims.*` 上即失敗。

### R13. 重建與接線必須看得見

`method` 為 `reconstructed` 或 `spliced` 的指標，`reading` 頁不能把它渲染成與 `observed` 相同的樣式。`_FX_EUR` 那種單一常數、優先股股數對季末、Reserve 與 Cash 接成一條，都屬於這裡。

**強制。** 快照測試不看像素是否漂亮，只看 DOM：這些指標的節點帶 `data-method="spliced"` 或 `reconstructed`。樣式表若把這兩種畫成與 `observed` 相同的顏色，不在這條規則裡；屬性消失才算失敗。

### R14. 衍生表只由管線寫入

`app/data/*.json` 的作者是 `web/refresh.py` / `web/build_data.py`。人只提交管線產生的結果。頁面 PR 不修改這些檔，除非同一份提交裡輸入 CSV 或模型變了。

**強制。** CI 在乾淨目錄重跑建置，與工作區的 `app/data` 做 diff，必須為空。做不到全量重解析之前（`archive.sqlite` 不在 git），這條的輸入是已進版控的 CSV 與 `web/raw`，範圍寫在腳本裡，不隱含「從 SEC 現抓」。手改 JSON 會讓 diff 失敗。

### R15. 恆等式在建置時關閉

`price.mstr`、`mnav.cebe`、`btc_per_share.cebe`、`price.btc` 四個入庫值滿足 `P = m ×（顆／股）× p`。展示若改用 sats，三個**顯示字串**還原後仍要落在登錄寫明的分差以內（建議一分錢以內）。這條補上今天只守了入庫值、沒守顯示字串的缺口。

**強制。** pytest 掃整條 `metric_value`。另外 Vitest 載入與頁面相同的 `format(Value)`，把格式化結果還原再乘，超過登錄的分差即失敗。格式化函式因此不能只存在於元件的私有閉包裡。

### R16. 一個部署目標

專案名只有一處，例如建置設定裡的一個常數。`CLAUDE.md` 的 Pages 專案 `mstr-capital-structure` 與 GitHub 上的 Workers 專案 `master-capital-structure` 今天是兩個。規則不代替那個選擇，它禁止選擇之後還留著第二個名字。

**強制。** 倉庫裡搜尋部署專案名，必須只命中那一個常數與其說明。CI 的部署步驟讀同一個常數。在選擇完成前，這條測試可以是待辦，但它是規則的一部分，不是文件腳註。

### R17. 已知矛盾放在出處，不放進預設讀數

`FINDING_*` 與 mnav.com 漏掉 STRE 的那種變體，只出現在 `type = source` 或 `method` 的頁。預設的 `reading` 不為它們開第三個 mNAV。

**強制。** `reading` 頁的 `metrics` 若含 `mnav_com` 或任一 `finding` 的 id，登錄驗證失敗。出處頁必須能列出 `data/ref/findings.jsonl`，漏列由 R12 的存在性檢查一起擋住。

---

## 3. 登錄長什麼樣

這是契約的範例，不是已經生成的檔。真正的檔案以後放在 `data/metrics.json`，由測試載入。

```json
{
  "metrics": [
    {
      "id": "btc.held",
      "label": "持幣",
      "unit": "BTC",
      "method": "step",
      "impl": "mstr_cebe.core.btc_held",
      "definition_rev": 1,
      "asOf": "latest_observation",
      "inputs": [{ "measure": "btc_held", "instrument": "BTC" }]
    },
    {
      "id": "claims.cebe",
      "label": "淨求償權（可轉債面額 + 優先股清算優先權 − 現金）",
      "unit": "USD",
      "method": "from_inputs",
      "impl": "mstr_cebe.core.net_senior_claims_usd",
      "basis": { "claims": "cebetracker", "cash": "balance_sheet" },
      "definition_rev": 1,
      "inputs": [
        { "measure": "notional", "instrument": "CONV_*" },
        { "measure": "liquidation_preference_native", "instrument": "STR*" },
        { "measure": "usd_cash", "instrument": "USD_CASH" }
      ]
    },
    {
      "id": "mnav.cebe",
      "label": "CEBE mNAV",
      "unit": "ratio",
      "impl": "mstr_cebe.core.mnav",
      "basis": { "mnav": "cebe", "claims": "cebetracker", "shares": "basic" },
      "definition_rev": 1
    },
    {
      "id": "mnav.basic",
      "label": "basic mNAV",
      "unit": "ratio",
      "impl": "mstr_cebe.core.mnav",
      "basis": { "mnav": "basic", "shares": "basic" },
      "definition_rev": 1
    }
  ]
}
```

`impl` 為 `mnav` 的兩列靠 `basis` 區分。頁面 import 的型別由這份檔生成：

```ts
export type MetricId = "btc.held" | "claims.cebe" | "mnav.cebe" | "mnav.basic";

export interface MetricDef {
  id: MetricId;
  unit: "USD" | "EUR" | "BTC" | "sats" | "share" | "ratio" | "year";
  basis?: Readonly<Record<string, string>>;
}
```

頁面寫 `metrics.get("claims.cebe", "2026-10-01")`，回傳第 2 節的 `Value`。拼錯 id 時 `tsc` 失敗。

---

## 4. 這些規則擋住的就是現在的那些頁

| 今天的現象 | 會先失敗的規則 |
|---|---|
| 總覽 $20.78B、儀表板 $14.76B | R1、R2、R6 |
| 畫面上四個因數乘不起股價 | R15 |
| 「距申報 93 天」貼在持幣上 | R3、R7 |
| 日頻持幣是斜線、週圖是階梯，頁面不說明 | R7、R13 |
| 跑道 $6.69B 叫成儲備 | R3、R6、R13。分子若仍是 FWP 情境，`asOf` 是 2026-08-24，不能渲染成最新一天 |
| 頁尾寫四檔優先股，STRE 沒有價 | R5。五檔來自 `instrument` 列的筆數，不是頁尾的句子 |
| 儀表板兩段相同的插值說明、出處兩段檔案庫說明 | R10。那句話由信封的 `method` 產生一次 |
| 窄螢幕導覽被裁掉 | 第 7 層的版面，規則不管。R9 只要求登錄裡的頁都進得了選單的資料，樣式另測 |
| 推導頁混進今天的數字 | 已有的講義測試，R10 把它綁到 `type=method` |
| 兩個 Cloudflare 專案名 | R16 |

頁面因此可以整份重寫，只要新頁仍向同一組 id 要數。
