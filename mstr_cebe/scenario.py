r"""定價頁的情境模擬:槓桿下限再融資 + mNAV 溢價 + 溢價增發。

**為什麼這個模組存在**:這三段機制原本只實作在 `app/src/charts/leverage.ts`,
Python 端一行都沒有,reference 也沒有推導 —— 只有一行程式註解聲稱
「已用 20 萬步離散模擬驗證誤差 <0.0001%」,而那個驗證不在倉庫裡。

CLAUDE.md 第一條規則說金融計算一律在 Python 端,理由是「同一條公式有兩個
實作就會各自漂移,而 TS 那側沒有測試守著」。定價頁是**互動模擬器**
(四個連續滑桿 ≈ 2.85 億種組合),不可能預先算好塞進 JSON,所以這裡的做法是:
**Python 是公式的來源與推導處,TS 的實作由黃金樣本釘住**(見 golden_grid())。

三段機制,依序疊加
-------------------

**1. 槓桿下限再融資。** 求償權的面額固定在美元,所以槓桿倍數
$A(p) = Hp/(Hp - C)$ 會隨幣價上升而自然下降。若公司設定 $A$ 不得低於 $L$,
一旦觸價就持續增發、把 $A$ 精確釘在 $L$。

觸發價:$A(p^*) = L \\Rightarrow p^* = \\dfrac{L \\cdot C}{(L-1) \\cdot H}$

觸發之後的普通股殘值 $R$ 依**冪次**成長:

$$R(p) = R(p^*) \\cdot \\left(\\frac{p}{p^*}\\right)^{L}, \\qquad R(p^*) = \\frac{H p^*}{L}$$

推導:釘住 $A = L$ 等價於 $\\text{NAV} = L \\cdot R$ 恆成立。公司把募到的錢
全部買幣,所以 NAV 的變動只有兩個來源 —— 幣價變動與新買的幣。
對 $R$ 微分並代入 $\\text{NAV} = LR$:

$$\\frac{dR}{R} = L \\cdot \\frac{dp}{p} \;\\Longrightarrow\; \\ln R = L \\ln p + c$$

這與固定倍數的槓桿 ETF 是同一個數學結構。`test_scenario.py` 用離散模擬
驗證這條封閉解。

**2. mNAV 溢價。** 市場付的股價 = $m \\times$ 每股殘值。

**3. 溢價增發的複利效果。** 用市價增發 $X$ 比例的股數、募到的錢全部買幣:

$$\\text{新每股殘值} = \\text{舊每股殘值} \\times \\frac{1 + X m}{1 + X}$$

$m = 1$ 時等於 1(增發無感),$m > 1$ 加分,$m < 1$ 稀釋 ——
與 02-operations.md 的 ATM 判準 $m > 1$ 完全一致,只是寫成了比例形式。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from .toolbox import State


@dataclass(frozen=True)
class Params:
    """三個自由參數。對應定價頁的三個滑桿。"""
    leverage_floor: float = 1.0   # ≤1 表示不啟用再融資機制
    mnav: float = 1.0
    atm_dilution: float = 0.0     # 額外增發的股數比例,0–1


@dataclass(frozen=True)
class Result:
    residual_usd: float
    shares: float
    per_share_usd: float
    per_share_sats: float
    market_price: float
    triggered: bool
    trigger_px: float
    amplification: float


def trigger_price(s: State, floor: float) -> float:
    """槓桿下限首次觸發的幣價。floor ≤ 1 視為不啟用,回傳 +inf。"""
    if floor <= 1:
        return math.inf
    return (floor * s.claims) / ((floor - 1) * s.held)


def residual_usd(s: State, px: float) -> float:
    """沒有任何機制介入時的普通股殘值(美元)。求償權吃光就是 0,不會變負。"""
    return max(0.0, s.held * px - s.claims)


def amplification(s: State, px: float) -> float:
    """$A(p) = Hp/(Hp - C)$。殘值歸零時無限大。"""
    nav = s.held * px
    return nav / (nav - s.claims) if nav > s.claims else math.inf


def levered_residual_usd(s: State, px: float, floor: float) -> float:
    """套用槓桿下限機制後的殘值。觸發價以下與不啟用時等同 `residual_usd`。"""
    star = trigger_price(s, floor)
    if not math.isfinite(star) or px <= star:
        return residual_usd(s, px)
    return (s.held * star / floor) * (px / star) ** floor


def apply_atm_accretion(residual: float, shares: float,
                        mnav: float, dilution: float) -> tuple:
    """溢價增發之後的 (殘值, 股數)。dilution ≤ 0 時原樣返回。"""
    if dilution <= 0:
        return residual, shares
    factor = (1 + dilution * mnav) / (1 + dilution)
    new_shares = shares * (1 + dilution)
    return (residual / shares) * factor * new_shares, new_shares


def run(s: State, px: float, p: Params) -> Result:
    """完整情境:給定目標幣價與三個參數,算出市場股價與每股數字。"""
    star = trigger_price(s, p.leverage_floor)
    r0 = levered_residual_usd(s, px, p.leverage_floor)
    r, sh = apply_atm_accretion(r0, s.shares, p.mnav, p.atm_dilution)
    per = r / sh if sh else 0.0
    return Result(
        residual_usd=r, shares=sh, per_share_usd=per,
        per_share_sats=(per / px) * 1e8 if px else 0.0,
        market_price=p.mnav * per,
        triggered=px > star,
        trigger_px=star,
        amplification=p.leverage_floor if px > star else amplification(s, px),
    )


# ---------------------------------------------------------------------------
# 黃金樣本:TS 的實作由這組數字釘住
# ---------------------------------------------------------------------------

# 滑桿的真實範圍(app/src/pages/pricing.ts)。樣本取端點與中段,
# 並刻意跨過觸發價兩側 —— 冪次那一段是最容易寫錯的地方。
GRID_PX = (25_000, 60_000, 86_000, 120_000, 180_000, 300_000)
GRID_FLOOR = (1.0, 1.05, 1.30, 1.60, 2.0)
GRID_MNAV = (0.5, 1.0, 1.21, 2.5)
GRID_DILUTION = (0.0, 0.10, 0.50)


def golden_grid(s: State) -> List[dict]:
    """展開成一組 (輸入, 輸出) 樣本。前端的測試逐筆比對這份。

    360 筆,覆蓋四個滑桿的端點與中段。數量刻意不大 —— 這是**釘住公式**,
    不是取樣整個空間;真正的保證來自 Python 這邊的推導與測試。
    """
    out: List[dict] = []
    for px in GRID_PX:
        for fl in GRID_FLOOR:
            for m in GRID_MNAV:
                for d in GRID_DILUTION:
                    r = run(s, px, Params(fl, m, d))
                    out.append({
                        "px": px, "floor": fl, "mnav": m, "dilution": d,
                        "per_share_usd": round(r.per_share_usd, 6),
                        "per_share_sats": round(r.per_share_sats, 3),
                        "market_price": round(r.market_price, 6),
                        "trigger_px": (None if math.isinf(r.trigger_px)
                                       else round(r.trigger_px, 4)),
                        "amp": (None if math.isinf(r.amplification)
                                else round(r.amplification, 6)),
                    })
    return out
