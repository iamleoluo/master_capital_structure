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

## 動手之前先讀 `reference/`

模型的推導、口徑選擇與**走過的彎路**都在那裡。不讀就動,很容易把已經
修掉的錯誤再做一次。

| | |
|---|---|
| [`reference/00-purpose.md`](reference/00-purpose.md) | 這個系統要回答什麼、決策問題對照表、刻意不做的事 |
| [`reference/01-model.md`](reference/01-model.md) | 從四個原始量到四層歸因,逐步推導 |
| [`reference/02-operations.md`](reference/02-operations.md) | 七把工具 + 三個組合的代數 |
| [`reference/03-data.md`](reference/03-data.md) | 實測 / 插值 / 沒有資料的邊界 |
| [`reference/04-decisions.md`](reference/04-decisions.md) | **被換掉的方法與為什麼換** |
| [`reference/05-toolbox.md`](reference/05-toolbox.md) | 系統的建構邏輯:工具 = 狀態轉移 |
| [`reference/06-architecture.md`](reference/06-architecture.md) | **重建設計圖**:採集／事件／資本操作／階段,四層規格與施工順序 |

`MSTR_CEBE_歷史分析_建置規格.md` 是 2026-08 的建置規格(要蓋什麼);
`reference/` 是模型本身(為什麼是這個形狀)。兩者不重複。

---

## 常用指令

```bash
python3 reference/verify.py      # 23 條恆等式對真實資料驗證(改模型必跑)
python3 -m pytest tests/test_toolbox.py -q   # 40 條:代數宣告不能與 apply 不符
python3 -m pytest tests/ -q      # 227 個測試
python3 web/build_data.py        # 重算 app/data/*.json,含兩個黃金錨點
python3 reference/build.py       # reference/*.md → reference/index.html
cd app && npm run build          # 一般建置(Cloudflare 用)
cd app && npm run build:artifact # 單檔 HTML(CSP 禁外部請求)
```

部署:`cd app && npx wrangler pages deploy dist --project-name mstr-capital-structure --branch master`
(生產分支是 `master`;下成 `main` 只會建出 preview)

---

## 硬規則

1. **金融計算一律在 Python 端**,前端只做排版與算術。同一條公式有兩個
   實作就會各自漂移,而 TS 那側沒有測試守著。
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
