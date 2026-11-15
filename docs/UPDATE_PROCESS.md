# 資料更新

目的還是那一個：看每股後面有多少比特幣。更新要讓日頻與週頻跟得上最新一份 8-K、最新一份 10-Q，以及最後一個交易日的價格。這份文件記的是 **2026-11-15 這次實際跑過的流程**，不是理想中的流程。

## 今天怎麼跑

一支指令：

```bash
python3 web/refresh.py
```

它依序做六件事。順序不能換，下游吃上游的檔案。

1. **SEC 文件**進 `web/archive.sqlite`（這個檔在 `.gitignore`）。預設從 2024-07-01 補 `8-K`、`8-K/A`、`10-Q`、`10-Q/A`、`10-K`、`424B5`、`FWP`。正文沒有買幣表、但 Exhibit 99 有的，另存一份，accession 後面加上 `#檔名`。然後抓一份當下的 XBRL companyfacts。
2. **事件重算**。`python3 -m mstr_cebe.events rebuild` 刪掉事件表，從歸檔的 HTML 重解，寫出 `web/raw/*.json` 與 `data/events.jsonl`。檔案庫是空的就不要跑這步：它會把 `web/raw` 覆寫成空的。
3. **BTC 與 MSTR 日線**進 `mstr_cebe.sqlite`（這個檔有進版控）。BTC 先打 Binance，失敗改 Coinbase。MSTR 打 Yahoo chart。
4. **優先股收盤**（STRC、STRF、STRK、STRD）整段重抓。歷史收盤和舊檔差超過門檻就中止，不覆蓋。STRE 沒有報價。
5. **優先股逐週股數**。已知的季末股數是錨，錨之後用 ATM 減回購往後加。
6. **`web/build_data.py`** 寫 `app/data/*.json`。沒有事件時，`build_meta` 會在 `_grain_facts` 炸掉；只重算日頻與週頻可以用 `web/rebuild_check.py`。

SEC 的 User-Agent 已經寫在 `mstr_cebe/archive.py`：`mstr-cebe-research (contact: iamleo789@gmail.com)`。不要拿掉。

跑完核對：

```bash
python3 reference/verify.py
python3 web/rebuild_check.py
python3 -m pytest tests/ -q
cd app && npm test && npm run build
```

上線是另一條指令，不在 `refresh.py` 裡：`cd app && npm run build && npx wrangler pages deploy dist --project-name mstr-capital-structure --branch master`。專案名是 `deploy_target.DEPLOY_PROJECT`。排程 workflow 只開資料 PR，不部署。

## 機器不會自己改的數字

companyfacts 只進檔案庫，**不會**寫進 `data/obs/*.csv`。下面這些仍是人手對著申報往 CSV 加一列：

| 檔案 | 這次加的 | 出處 |
|---|---|---|
| `data/obs/xbrl_debt.csv` | 2026-09-30 的 $6,715,414,000 | Q3 10-Q，`us-gaap:LongTermDebt`。非流動只剩 $5,669,745,000，另有 $1,045,669,000 被分成一年內到期。accession `0001050446-26-000060` |
| `data/obs/share_counts.csv` | 2026-10-25 基本股數 422,354,607 | 同一份 10-Q 封面：A 股 402,714,357、B 股 19,640,250 |
| `data/obs/preferred_balances.csv` | 2026-09-30 清算優先權 $14,109,839,000 | 同一份 10-Q。STRC 在外 90,964,532 股 |
| `web/build_pref_weekly.py` 的 `KNOWN` | STRC 在 2026-09-30 對齊 90,964,532 | 之後的週用 8-K 回購往下減，2026-11-08 是 80,305,015 |

`data/obs/usd_reserve.csv` 與 `usd_cash.csv` 是 `web/raw/reserve_weekly.json` 的副本。事件重算之後要一起重寫，否則測試裡「兩條加總等於拼接」會對不上。

日頻的 STRE 匯率仍是常數 `884_120 / 775_000`（2026-06-30）。Q3 的隱含匯率是 `879_083 / 775_000 = 1.1343`。沒有日頻匯率可抓。

## 這次實際撞上的問題

計時是 2026-11-15 這次跑的。

| 步驟 | 結果 | 時間 |
|---|---|---|
| 檔案庫 | `web/archive.sqlite` 是空的（測試建過 schema，0 份文件）。manifest 只有網址與 sha256，沒有原文，只能重抓 | — |
| 依 manifest 重抓 200 份 | 200 份都抓得到，**200 份雜湊都不符**。HTML 普遍少 16 bytes（最後兩份 8-K 少 4 bytes），是 SEC 頁面上的 script，不是申報正文改了。submissions 與 companyfacts 的網址是活的，舊快照補不回來 | 73 秒 |
| 補 2024-07-01 之後 manifest 沒有的申報 | 40 份：含 Q3 10-Q（2026-11-02）、2026-11-02 的四份 424B5、2026-11-03 的 FWP、8-K 到 2026-11-09 | 16 秒 |
| 事件重算 | 1,136 筆事件。既有週列沒有改值。多出來的週是新 8-K，加上兩份只在 Exhibit 99 裡的週 | 約 22 秒 |
| Exhibit 99 | 正文沒有「Aggregate BTC Holdings」的 8-K 會再抓附件。9 份附件裡有買幣表。2026-10-11 那週（250 顆、持幣 848,250、STRC 回購 1,932,145 股）不抓附件就會消失。accession `0001193125-26-419726` | 含在上面的抓取裡 |
| BTC 日線 | Binance `451`。改走 Coinbase，日線到 2026-11-15（週日有一根，和 MSTR 對齊之後日頻停在 2026-11-13） | 未單獨計時，驗證三項都過 |
| MSTR 與優先股 | Yahoo chart。優先股歷史收盤與舊檔相符，允許覆蓋。四個系列都到 2026-11-13。STRE 仍然沒有 | 優先股 0.4 秒 |
| `build_data.py` | 日頻 597 列（2024-07-01 → 2026-11-13），週頻 108 列。兩個 FWP 黃金錨點仍是 $92.11 與 $118.31 | 與優先股股數重建合計約 65 秒 |

另外三件不是故障，但數字會看錯：

- **股數停在 2026-10-25。** 之後兩週 ATM 又賣了 1,178,552 與 2,051,348 股普通股（accession `0001193125-26-442707`、`0001193125-26-452693`）。日頻沒有把這 323 萬股加進在外股數。
- **STRF 清算優先權是每股 $103.57，日頻仍用 $100 面額。** 差額約 $45.8M。Q2 時兩者還一樣，這是 Q3 才分開的。
- **資產負債表現金 $2,501,456,000（2026-09-30）沒有寫進現金錨。** 週頻的 USD Reserve + USD Cash 是另一個口徑，9 月底約 $6B。把季報現金插進同一條線，會在兩週之間掉到 $2.5B。

`python3 web/refresh.py` 在空檔案庫上先印新鮮度，以前會因 `MAX(filed_at)` 是 NULL 而炸掉。現在空來源印成「空的」，然後繼續抓。

## 已經收進流程的

- `refresh.py` 會抓 10-Q、424B5、FWP，以及 Exhibit 99 與 companyfacts。先前它只抓 8-K。
- `archive backfill` 可以在日期後面加上表格代碼；`8-K/A` 會改回解析器認得的 `sec_8k`。
- Reserve 的「$132.7 million」乘上 1e6 會變成 `132699999.99999999`。現在四捨五入到元。
- `.github/workflows/refresh-data.yml`：每週二 15:00 UTC（以及手動）在乾淨環境跑 `refresh.py`，日頻落後超過 5 天就失敗，否則開一張 PR，附上相對 master 的 diff。**不部署。** 排程只在這支 workflow 進了 master 之後才會跑。用 `GITHUB_TOKEN` 開的 PR 不會再觸發別的 workflow，所以那張 PR 上的 rebuild check 要人手看，或在本機跑 `web/rebuild_check.py`。

## 還沒做、值得做的

1. **XBRL 寫回 CSV 要有人看過再收進版本庫。** 自動把 `LongTermDebtNoncurrent` 接上 Q3 會少記 $1.05B。寫入之前要同時印出非流動與總額，兩筆差超過 $50M 就停下來等人選。
2. **封面股數之後的 ATM。** 10-Q 封面是精確在外股數，其後每週的普通股 ATM 股數已經解得出來。把「封面 + 之後的 ATM」做成帶 `estimated` 標記的錨，比一直停在 10 月 25 日準。不要默默加進現在這條「只收申報期末」的序列。
3. **STRF 的清算優先權與 $100 面額。** 日頻要麼改標成面額，要麼從 2026-09-30 起改用 10-Q 的每股清算優先權。不要兩個口徑共用一個沒有名字的數字。
4. **EUR/USD。** 現在是一顆 Q2 常數。至少每個季末用 10-Q 的 STRE 美元帳面除以歐元面額，季與季之間再內插。不要用一顆新匯率回頭改寫全部歷史。
5. **檔案庫。** 內容定址的 sha256 無法當「再抓一次必須相同」的檢查：SEC 會改 HTML 裡的 script。manifest 仍適合對網址與 accession。sqlite 本體不進 git（一年的 blob 會把歷史撐大）。比較穩的是把當下的 `web/archive.sqlite` 存成 Actions artifact，下一輪先還原再補抓；抓下來的 HTML 雜湊不符時留下新的 doc_id，不要把舊列覆蓋掉。
6. **失敗要叫人。** 排程 PR 沒有人看，或 Binance / Yahoo / SEC 連續失敗，目前只會停在 Actions 日誌。接到既有的通知管道（倉庫的 GitHub notification 就夠）比再造一個警報系統實際。新鮮度門檻已經放在 workflow 裡：日頻落後超過 5 天不開 PR。
