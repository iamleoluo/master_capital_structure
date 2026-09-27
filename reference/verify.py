#!/usr/bin/env python3
"""驗證 reference/ 裡每一條編號恆等式,對象是真實資料。

文件會腐爛,可執行的斷言不會。reference/01-model.md 與 02-operations.md 的
每一條式子在這裡都有對應的檢查,編號一致。改了模型卻沒改文件,這支會紅。

    python3 reference/verify.py

不吃任何參數。讀 app/data/*.json —— 也就是前端實際拿到的那份資料,
不是中間產物,所以它驗的是「使用者真正看到的數字」。
"""
from __future__ import annotations

import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "app", "data")

failures: list[str] = []
checks = 0


def check(tag: str, ok: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if ok:
        print(f"  ✓ {tag}")
    else:
        print(f"  ✗ {tag}  {detail}")
        failures.append(tag)


def load(name: str):
    with open(os.path.join(DATA, f"{name}.json"), encoding="utf-8") as f:
        return json.load(f)


daily = load("daily")
strategy = load("strategy")
chronicle = load("chronicle")
meta = load("meta")
N = len(daily["date"])
LAST = N - 1

sats = 1e8


def E_of(i: int) -> float:
    """實得每股含幣量(sats)。分子用 common_btc —— 管線已經扣好求償權。"""
    return daily["common_btc"][i] / (daily["shares"][i] * 1e6) * sats


def B_of(i: int) -> float:
    return daily["held"][i] / (daily["shares"][i] * 1e6) * sats


def C_of(i: int) -> float:
    """求償權(USD)= 可轉債 + 優先股清算優先權 − USD 流動性。"""
    return (daily["debt"][i] + daily["pref_total"][i] - daily["cash"][i]) * 1e9


print("\n§1 資本結構的三條基本式")

# 容差不是隨便抓的,是從 daily.json 的輸出位數推出來的上界:
#   held / common_btc 取整數        → 各 ±0.5 BTC
#   debt / cash / pref_total 取 4 位小數($B)→ 各 ±$50k,三欄合計 ±$150k
# 換算成幣就是 ±1.5e5/p。恆等式本身是精確的,這裡量的是四捨五入殘渣;
# 誤差若超過這個上界,那就不是位數問題而是模型真的錯了。
def tol_btc(i: int) -> float:
    return 1.0 + 1.5e5 / daily["btc"][i]


# (1.1) 求償權換算成幣之後,剛好是帳面與實得的差
worst, bound = 0.0, 0.0
for i in range(N):
    err = abs((B_of(i) - E_of(i))
              - C_of(i) / daily["btc"][i] / (daily["shares"][i] * 1e6) * sats)
    lim = tol_btc(i) / (daily["shares"][i] * 1e6) * sats
    worst, bound = max(worst, err - lim), max(bound, err)
check("(1.1) B − E = C / (p·S) × 1e8", worst <= 0,
      f"最大誤差 {bound:.3f} sats,超出位數上界 {worst:.3e}")

# (1.2) 普通股殘量 = 總持幣 − 求償權換算的幣數
worst, bound = 0.0, 0.0
for i in range(N):
    err = abs(daily["common_btc"][i]
              - (daily["held"][i] - C_of(i) / daily["btc"][i]))
    worst, bound = max(worst, err - tol_btc(i)), max(bound, err)
check("(1.2) 普通股殘量 = H − C/p", worst <= 0,
      f"最大誤差 {bound:.3f} BTC,超出位數上界 {worst:.3e}")

# (1.3) 歸零價:普通股殘量在這個幣價歸零
i = LAST
p0 = C_of(i) / daily["held"][i]
resid = daily["held"][i] - C_of(i) / p0
check("(1.3) p₀ = C/H 時 E = 0", abs(resid) < 1e-6, f"殘量 {resid:.3e} BTC")

print("\n§2 股價恆等式")

# (2.1) 股價 = mNAV × 實得每股 × 幣價 / 1e8
worst = max(abs(daily["mstr"][i]
                - daily["mnav_cebe"][i] * E_of(i) / sats * daily["btc"][i])
            / daily["mstr"][i] for i in range(N))
check("(2.1) P = m × E/1e8 × p", worst < 5e-4, f"最大相對誤差 {worst:.2e}")

# (2.2) 取對數之後三層相加無殘差
lo, hi = 0, LAST
lhs = math.log(daily["mstr"][hi] / daily["mstr"][lo])
rhs = (math.log(daily["btc"][hi] / daily["btc"][lo])
       + math.log(E_of(hi) / E_of(lo))
       + math.log(daily["mnav_cebe"][hi] / daily["mnav_cebe"][lo]))
check("(2.2) ln(P₁/P₀) = ln(p) + ln(E) + ln(m)", abs(lhs - rhs) < 1e-3,
      f"差 {abs(lhs - rhs):.2e}")

print("\n§3 逐日鏈結:決策 vs 行情")

rows = [r for r in strategy["rows"] if r]
# (3.1) sats 口徑:兩者相加 = 期間實現變化
bad = max((abs((r["split"]["market"] + r["split"]["decision"])
               - (strategy["cebeNow"] - r["cebe0"])) for r in rows), default=0)
check("(3.1) 決策 + 行情 = ΔE(sats)", bad <= 1.0, f"最大誤差 {bad} sats")

# (3.2) 對數口徑:兩者相加 = 三層拆解裡的 E 那一層
bad = max((abs(r["splitLog"]["market"] + r["splitLog"]["decision"]
               - r["layers"]["cebe"]) for r in rows), default=0)
check("(3.2) 決策 + 行情 = ln(E₁/E₀)", bad < 1e-3, f"最大誤差 {bad:.2e}")

print("\n§4 四層歸因")

# (4.1) 四層相加 = 實際股價報酬(績效歸因頁的每一列)
worst, worst_at = 0.0, ""
for idx, r in enumerate(strategy["rows"]):
    if not r:
        continue
    four = (r["layers"]["btc"] + r["splitLog"]["decision"]
            + r["splitLog"]["market"] + r["layers"]["mnav"])
    actual = math.log(1 + r["mstrRet"] / 100)
    if abs(four - actual) > worst:
        worst, worst_at = abs(four - actual), daily["date"][idx]
check("(4.1) 四層相加 = ln(MSTR 報酬比)", worst < 6e-3,
      f"最大誤差 {worst:.2e} @ {worst_at}")

# (4.2) 大事記每一則也成立
worst = 0.0
for e in chronicle:
    L = e["layers4"]
    lo, hi = e["range"]
    actual = math.log(daily["mstr"][hi] / daily["mstr"][lo])
    worst = max(worst, abs(sum(L.values()) - actual))
check("(4.2) 大事記四層相加 = 該期報酬", worst < 1e-3, f"最大誤差 {worst:.2e}")

# (4.3) 全期框架同樣成立
L = meta["program"]["layers4"]
actual = math.log(daily["mstr"][LAST] / daily["mstr"][0])
check("(4.3) 全期四層相加 = 全期報酬", abs(sum(L.values()) - actual) < 1e-3,
      f"誤差 {abs(sum(L.values()) - actual):.2e}")

print("\n§5 操作層級拆解")

# (5.1) 八種操作的 Shapley 相加 = ΔE。
# 八項各自取整數輸出 → 加總最壞差 8 × 0.5 = 4 sats,對上兩萬 sats 的變化。
bad = max((abs(sum(r["ops"].values()) - (strategy["cebeNow"] - r["cebe0"]))
           for r in rows), default=0)
check("(5.1) Σ 操作貢獻 = ΔE(sats)", bad <= 4.0, f"最大誤差 {bad} sats(上界 4)")

# (5.2) 兩因子拆解相加 = ΔB
bad = 0.0
for idx, r in enumerate(strategy["rows"]):
    if not r:
        continue
    bad = max(bad, abs(sum(r["bpsOps"].values())
                       - (strategy["bpsNow"] - r["bps0"])))
check("(5.2) 持幣效果 + 股數效果 = ΔB(sats)", bad <= 2.0, f"最大誤差 {bad} sats")

print("\n§6 操作代數(以真實結構代入合成情境)")

i = LAST
H, S, C, p = (daily["held"][i], daily["shares"][i] * 1e6, C_of(i), daily["btc"][i])
E = (H - C / p) / S * sats
B = H / S * sats


def E_after(dH: float = 0.0, dC: float = 0.0, dS: float = 0.0) -> float:
    return (H + dH - (C + dC) / p) / (S + dS) * sats


# (6.1) 用現金買幣:持幣增加 c/p,求償權同額增加 → 淨效果恰好是零
c = 1e9
check("(6.1) 用現金買幣 ΔE = 0", abs(E_after(dH=c / p, dC=c) - E) < 1e-9,
      f"ΔE = {E_after(dH=c / p, dC=c) - E:.3e}")

# (6.2) 折價回購:進得了分子的只有折價本身
F, cost = 1e9, 0.73e9                      # 面額 $1B,用 $0.73B 買回
check("(6.2) 折價回購 ΔE = (F−c)/(p·S)×1e8",
      abs((E_after(dC=cost - F) - E) - (F - cost) / (p * S) * sats) < 1e-9)

# (6.3) 股息債息:純流出,結構上必然為負
check("(6.3) 股息債息 ΔE < 0", E_after(dC=c) - E < 0)

# (6.4) 賣幣進儲備:幣與求償權等量對消,對 E 中性、對 B 為負
x = 1000.0
check("(6.4) 賣幣進儲備 ΔE = 0", abs(E_after(dH=-x, dC=-x * p) - E) < 1e-9)
check("(6.4) 賣幣進儲備 ΔB < 0", (H - x) / S * sats - B < 0)

# (6.5) ATM 增發是否增值 ⟺ mNAV > 1。兩邊各取一個 m 驗證,不是只驗一側。
for m, expect in ((1.20, True), (0.80, False)):
    P = m * E / sats * p                   # 由恆等式反解當下股價
    n = S * 0.01
    accretive = E_after(dC=-n * P, dS=n) > E
    check(f"(6.5) ATM 增發 m={m} → {'加分' if expect else '減分'}",
          accretive is expect)

# (6.6) ATM 增發 + 折價回購 ⟺ mNAV > 1 − d。門檻兩側各驗一次。
d = 0.27
for m, expect in ((1 - d + 0.05, True), (1 - d - 0.05, False)):
    P = m * E / sats * p
    n = S * 0.01
    raised = n * P
    F = raised / (1 - d)                   # 同一筆錢能消滅的面額
    accretive = E_after(dC=-F, dS=n) > E
    check(f"(6.6) ATM→折價回購 d={d} m={m:.2f} → {'加分' if expect else '減分'}",
          accretive is expect)

print("\n§7 口徑偏差")

# (7.1) 優先股按市價扣一定不低於按面額扣的 E(市場標在面額以下時)
PREF = ("strf", "strc", "strk", "strd", "stre")
i = LAST
par = sum(daily[f"{k}_lp"][i] for k in PREF) * 1e9
mkt = sum(daily[f"{k}_lp"][i] * 1e9
          * ((daily[f"{k}_price"][i] / 100) if daily[f"{k}_price"][i] else 1.0)
          for k in PREF)
check("(7.1) 優先股市值 ≤ 面額(目前)", mkt <= par,
      f"市值 ${mkt/1e9:.2f}B vs 面額 ${par/1e9:.2f}B")
e_par = (daily["held"][i] - (C_of(i)) / daily["btc"][i]) / (daily["shares"][i] * 1e6) * sats
e_mkt = (daily["held"][i] - (C_of(i) - (par - mkt)) / daily["btc"][i]) / (daily["shares"][i] * 1e6) * sats
check("(7.1) 面額口徑低估實得每股", e_par <= e_mkt,
      f"面額 {e_par:,.0f} vs 市價 {e_mkt:,.0f} sats")

print(f"\n{'─' * 58}")
if failures:
    print(f"✗ {len(failures)} / {checks} 條不成立:")
    for f in failures:
        print(f"    {f}")
    sys.exit(1)
print(f"✓ {checks} 條恆等式全部成立(資料至 {daily['date'][LAST]})")
