# CLAUDE.md

## 這是什麼

**MSTR 資本框架分析工具 —— 一個決策工具,不是研究報告。**

它把 MSTR 的股價拆成**幣、求償權、股數、情緒**四件事,讓每一次決策可以
指著其中一件說「我是為了這個」。資料每週更新,**但拆解的框架不變** ——
專案真正在維護的是那個框架。

```
每股帳面幣值  B/1e8 × p
− 求償權吃掉  (B−E)/1e8 × p
= 每股殘值    E/1e8 × p
× 市場溢價    m
= 股價        P            ← 拆得開,誤差 0.000%
```

---

## 最核心的結構概念:公式解 vs 數值解

**整個系統是同一個 L1–L4,解兩次。** 這不是前端的呈現方式,是系統結構本身。

| 層 | **公式解**(代數,不帶任何數字) | **數值解**(代進真實參數) |
|---|---|---|
| **L1 量** | $H, C, S, p$ 的定義、$C = D+L-U$、$B, E, m, A, p_0$ 的式子 | 今天各是多少、怎麼從申報算出來 |
| **L2 工具** | 每把工具的 $\Delta B/\Delta E$ 與判準 | 實際用了哪些、各多少錢 |
| **L3 配對** | **組合的公式**:ATM 配買幣、ATM 配回購、賣幣配回購 | 實際配對出來的具名操作 |
| **L4 時間** | 逐日鏈結為什麼沒有殘差、歸因的推導 | 實際的歸因數字與階段 |

> **判準:一句話裡出現具體數字,它就屬於數值解。**

**L1–L4 不是工程上的任意切分,它就是模型本身的四個層次。**
`archive` / `events` / `operations` / `phases` 是數值解那一欄的實作;
`toolbox`(工具與組合的代數)是公式解那一欄的實作。
兩欄走同一條構築線,只是一邊用符號、一邊用數字。

⚠️ 網站的「講義 / 儀表板 / 觀點」**只是呈現方式**(見
[09-site.md](reference/09-site.md)),不要拿它當系統結構 ——
講義呈現公式解、儀表板呈現數值解,但結構是上面那張表。

---

## 動手之前先讀 `reference/`

模型的推導、口徑選擇與**走過的彎路**都在那裡。不讀就動,很容易把已經
修掉的錯誤再做一次。

| | |
|---|---|
| [`reference/00-purpose.md`](reference/00-purpose.md) | 這個系統要回答什麼、決策問題對照表、刻意不做的事 |
| [`reference/01-model.md`](reference/01-model.md) | 從四個原始量到四層歸因,逐步推導 |
| [`reference/02-operations.md`](reference/02-operations.md) | 九把原子工具 + 四個組合的代數 |
| [`reference/03-data.md`](reference/03-data.md) | **資料的血統、粒度與邊界**:三種粒度怎麼不重複計算 |
| [`reference/04-decisions.md`](reference/04-decisions.md) | **被換掉的方法與為什麼換** |
| [`reference/05-toolbox.md`](reference/05-toolbox.md) | 代數怎麼變成可執行的宣告(**另一條軸**,見下) |
| [`reference/06-architecture.md`](reference/06-architecture.md) | **四層架構規格**:L1 採集／L2 事件／L3 操作／L4 階段 |
| [`reference/07-data-gaps.md`](reference/07-data-gaps.md) | 資料缺口:今天的資料夠不夠支撐今天的結論 |
| [`reference/08-status.md`](reference/08-status.md) | **唯一的進度來源**:現況、施工紀錄、下一步 |
| [`reference/09-site.md`](reference/09-site.md) | **網站的設計**:理論／觀測／詮釋三分,以及為什麼不能混 |
| [`reference/10-rebuild-plan.md`](reference/10-rebuild-plan.md) | **前端重排施工計畫**:下一步從這裡接 |

⚠️ **兩條軸都叫「層」。** 06 的 `L1–L4` 是**資料怎麼流**(程式模組
`archive`/`events`/`operations`/`phases` 與所有 commit 用這套);
05 的分層是**一把工具由什麼組成**(量→尺→工具→組合→歸因→判斷→決策),
刻意不用 `L` 編號。`L4` 只有一個意思:階段。

⚠️ **進度只寫在 08。** 不要在 05/06/07 再寫一份現況 —— 以前三份各自過時過。

`MSTR_CEBE_歷史分析_建置規格.md` 是 2026-08 的建置規格(要蓋什麼);
`reference/` 是模型本身(為什麼是這個形狀)。兩者不重複。

---

## 常用指令

```bash
python3 web/refresh.py          # 每週更新:SEC → 事件 → 市場價 → app/data
python3 web/refresh.py --dry-run # 只看各來源的新鮮度
python3 reference/verify.py      # 23 條恆等式對真實資料驗證(改模型必跑)
python3 -m pytest tests/test_toolbox.py -q   # 40 條:代數宣告不能與 apply 不符
python3 -m pytest tests/ -q      # 320 個測試
python3 -m mstr_cebe.archive backfill   # L1:補抓 SEC 文件到 web/archive.sqlite
python3 -m mstr_cebe.archive stats      # 檔案庫現況
python3 -m mstr_cebe.events rebuild    # L2:由文件重算事件 + 寫出 web/raw 視圖
python3 -m mstr_cebe.events export     # 只重寫 web/raw/*.json(事件層的序列化)
python3 -m mstr_cebe.operations rebuild # L3:由事件重算資本操作 + 對帳
python3 -m mstr_cebe.phases            # L4:階段偵測 + 解釋率前提檢查
python3 web/build_data.py        # 重算 app/data/*.json,含兩個黃金錨點
python3 reference/build.py       # reference/*.md → reference/index.html
cd app && npm test               # TS 的情境模擬對 Python 黃金樣本
cd app && npm run build          # 一般建置(含 tsc + npm test)
cd app && npm run build:artifact # 單檔 HTML(CSP 禁外部請求)
```

部署:`cd app && npx wrangler pages deploy dist --project-name mstr-capital-structure --branch master`
(生產分支是 `master`;下成 `main` 只會建出 preview)

---

## 硬規則

1. **金融計算一律在 Python 端**,前端只做排版與算術。同一條公式有兩個
   實作就會各自漂移,而 TS 那側沒有測試守著。

   **唯一的例外是定價頁的情境模擬**(四個連續滑桿 ≈ 2.85 億種組合,
   不可能預先算好塞進 JSON)。它的處理方式是把規則的理由補上:
   公式的來源與推導在 `mstr_cebe/scenario.py`,TS 的實作由 360 筆
   黃金樣本逐筆釘住(`app/test/scenario.test.ts`)。
   **要在前端加新的金融計算,先問能不能預先算完;不能的話就照這個模式配測試。**
2. **加總恆等式要能斷言。** 新增任何拆解,就在 build 時逐列 assert,
   並在 `reference/verify.py` 加同號檢查。
3. **兩個黃金錨點不能動**(\$92.11 / \$118.31)。它們是官方 FWP 的一手資料。
4. **口徑選了就要寫下它偏在哪一邊**,而且寫在使用者看得到的地方
   (資料品質頁),不是只寫在註解裡。
5. **不要用淨額當佔比的分母** —— 各層會互相抵銷,會吐出 158%、−100%。
   用「佔變動量」。

---

## 詞彙(全站統一,不要再發明新的)

| 顯示名稱 | 符號 | 技術名(只在定義處出現) |
|---|---|---|
| 帳面每股含幣量 | $B = H/S \times 10^8$ | Gross BPS / 公司的 BTC Yield |
| 實得每股含幣量 | $E = (H - C/p)/S \times 10^8$ | CEBE |
| 決策 / 行情 | — | 逐日鏈結 |

⚠️ **`mNAV` 不要裸用。** 本站的 $m$ 是 **CEBE mNAV**(分母是殘值),
與一般講的 mNAV(分母是全部持幣)不同 —— 同一天可以一個溢價一個折價。

---

## 網站結構

```
總覽 │ 大事記 │ 資本結構 │ 資本操作 │ 績效歸因 │ 槓桿與定價 │ 資料品質
                └ 持幣與融資 · 求償權與殘值
```

定義收斂在「求償權與殘值」,操作代數收斂在「資本操作」,其他頁以超連結
指回去、不重述。`app/src/components/` 下的 `symbols.ts` / `layers.ts` /
`toolkit.ts` 是跨頁共用的單一來源。

資料管線的視覺化:[`diagrams/data-pipeline.html`](diagrams/data-pipeline.html)
