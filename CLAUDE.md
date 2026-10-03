# CLAUDE.md

**目的:讓 MSTR 長期贏過比特幣。** 比特幣有限,只有一種贏法 —— 每股含幣量變多。
這個專案存在的理由只有一個:**看懂公司為了那件事做了什麼。**

工具的演進是把風險往外推:抵押借錢(風險在公司)→ 可轉債 → 永續優先股(風險在市場)。

⚠️ **轉嫁出去 ≠ 不用管。** 優先股跌破面額與公司盈虧無關,
但要繼續買幣擴張,就得把它拉回面額。**風險是市場的,約束是公司的。**
於是有這個環:

    折價回購 → 拉回面額 → 重新發行 → 買幣 → 槓桿加大 → 每股含幣量上升

**回購不是為了賺價差,是解鎖下一輪。** 只看當下損益,每一筆操作都會判錯。

量它有兩種口徑,差別只在分母算不算求償權。⚠️ `mNAV` 不要裸用。

| 分母 | 相對市值 | 相對股數 |
|---|---|---|
| 全部持幣 | basic mNAV | 帳面每股 $B$ ← 公司的 BTC Yield |
| 扣求償權 | CEBE mNAV($m$) | 實得每股 $E$ ← 本站 |

$P = m \times E/10^{8} \times p$,誤差 0.000%。

**每一段內容都要能指回最上面那個目的。指不回去的是雜訊,不是細節。**

主線在 [reference/](reference/README.md) 00→04,進度只在 [10-status](reference/10-status.md)。

```bash
python3 -m pytest tests/ -q && python3 reference/verify.py && python3 web/build_data.py
cd app && npm run build && npx wrangler pages deploy dist --project-name mstr-capital-structure --branch master
```
⚠️ Pages 沒接 git,push 不會部署 —— 一定要手動下最後那行。
