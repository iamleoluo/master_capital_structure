# CLAUDE.md

**MSTR 資本框架分析工具 —— 一個決策工具,不是研究報告。**
資料每週更新,**但拆解的框架不變**;專案真正在維護的是那個框架。

```
每股帳面幣值  B/1e8 × p
− 求償權吃掉  (B−E)/1e8 × p
= 每股殘值    E/1e8 × p
× 市場溢價    m
= 股價        P            ← 拆得開,誤差 0.000%
```

---

## 最核心的概念:公式解 vs 數值解

**整個系統是同一個 L1–L4,解兩次。** 這是系統結構,不是呈現方式。

| 層 | **公式解**(代數,不帶數字) | **數值解**(代進真實參數) |
|---|---|---|
| L1 量 | $H, C, S, p$ 與 $B, E, m, A, p_0$ 的式子 | 今天各是多少、怎麼從申報算出來 |
| L2 工具 | 每把工具的 $\Delta B/\Delta E$ 與判準 | 實際用了哪些、各多少錢 |
| L3 配對 | 組合的公式(ATM 配買幣、賣幣配回購…) | 實際配對出來的具名操作 |
| L4 時間 | 逐日鏈結為什麼沒有殘差、歸因的推導 | 實際的歸因數字與階段 |

> **判準:一句話裡出現具體數字,它就屬於數值解。**

`toolbox` 是公式解的實作;`archive`/`events`/`operations`/`phases` 是數值解的實作。
**L1–L4 就是模型本身的四個層次**,不是工程上的任意切分。

---

## 動手之前先讀 `reference/`

推導、口徑選擇與**走過的彎路**都在那裡。不讀就動,很容易把修掉的錯誤再做一次。
導覽與編號規則見 [`reference/README.md`](reference/README.md)。

| | |
|---|---|
| [00](reference/00-purpose.md) 目的 | 要回答什麼、刻意不做的事 |
| [01](reference/01-model.md) 模型 | 四個原始量 → 四層歸因,逐步推導 |
| [02](reference/02-operations.md) 操作 | 九把原子工具 + 四個組合的代數 |
| [03](reference/03-data.md) 資料 | 血統、粒度、邊界;三種粒度怎麼不重複計算 |
| [04](reference/04-decisions.md) 彎路 | **被換掉的方法與為什麼換** |
| [05](reference/05-toolbox.md) 工具箱 | 代數怎麼變成可被打臉的宣告 |
| [06](reference/06-architecture.md) 架構 | L1–L4 的規格(數值解那一欄) |
| [07](reference/07-data-gaps.md) 缺口 | 今天的資料夠不夠支撐今天的結論 |
| [08](reference/08-status.md) 現況 | **唯一的進度來源** |
| [09](reference/09-site.md) 網站設計 | 理論／觀測／詮釋三分 |
| [10](reference/10-rebuild-plan.md) 施工計畫 | **下一步從這裡接** |

---

## 常用指令

```bash
python3 web/refresh.py           # 每週更新(--dry-run 只看新鮮度)
python3 -m pytest tests/ -q      # 全部測試
python3 reference/verify.py      # 恆等式對真實資料驗證(改模型必跑)
python3 web/build_data.py        # 重算 app/data/*.json,含兩個黃金錨點
python3 reference/build.py       # reference/*.md → index.html
cd app && npm run build          # 建置(含 tsc + vitest)
```

逐層重跑:`python3 -m mstr_cebe.{archive backfill, events rebuild, operations rebuild, phases}`

部署:`cd app && npx wrangler pages deploy dist --project-name mstr-capital-structure --branch master`
(生產分支是 `master`;下成 `main` 只會建出 preview)

---

## 硬規則

1. **金融計算一律在 Python 端。** 同一條公式有兩個實作就會各自漂移。
   唯一的例外是定價頁的情境模擬(連續滑桿無法預先算),它由 360 筆黃金樣本
   釘住 —— 要在前端加新計算,先問能不能預先算完,不能就照那個模式配測試。
2. **加總恆等式要能斷言。** 新增任何拆解就在 build 時逐列 assert,
   並在 `verify.py` 加同號檢查。
3. **兩個黃金錨點不能動**(\$92.11 / \$118.31,官方 FWP 一手資料)。
4. **口徑選了就要寫下它偏在哪一邊**,而且寫在使用者看得到的地方。
5. **不要用淨額當佔比的分母** —— 各層會互相抵銷,會吐出 158%、−100%。

---

## 詞彙(不要再發明新的)

| 顯示名稱 | 符號 | 技術名(只在定義處出現) |
|---|---|---|
| 帳面每股含幣量 | $B = H/S \times 10^8$ | Gross BPS / 公司的 BTC Yield |
| 實得每股含幣量 | $E = (H - C/p)/S \times 10^8$ | CEBE |
| 決策 / 行情 | — | 逐日鏈結 |

⚠️ **`mNAV` 不要裸用。** 本站的 $m$ 是 **CEBE mNAV**(分母是殘值),
與一般講的 mNAV(分母是全部持幣)不同 —— 同一天可以一個溢價一個折價。

網站結構正在依 [10](reference/10-rebuild-plan.md) 重排,現況見該文件 §1。
