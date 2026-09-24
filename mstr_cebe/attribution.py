"""把股價變化拆成「幣價 / 每股含幣量 / 市場溢價」,再把每股含幣量拆成四個驅動因子。

兩層拆解都建立在專案既有的恆等式上,不是新造的模型:

  第一層(乘法,對數拆解後可加,殘差為零):
      MSTR 股價 = CEBE mNAV × CEBE每股(sats) × BTC價格 / 1e8
      → log(股價比) = log(mNAV比) + log(CEBE比) + log(幣價比)
      每一項佔總對數變化的比例,就是該層的貢獻度。

  第二層(CEBE 本身的四個驅動因子,用 Shapley 值拆):
      CEBE = (持幣 − 求償權美元/幣價) / 股數 × 1e8
      四個因子:持幣、求償權、幣價、股數。

為什麼第二層用 Shapley:
    這個式子對四個因子是非線性的(求償權要除以幣價、整體再除以股數),
    所以「一次改一個」的結果會隨著改動順序而不同 —— 先改幣價再改求償權,
    跟反過來,分到的數字不一樣。Shapley 值就是對全部 4! = 24 種順序取平均,
    結果與順序無關,而且四項加總<b>精確</b>等於實際變化量(這點有測試守著)。

⚠️ 解讀時必須同時看到的因果關係:
    「股數增加」與「求償權減少」在這段期間是同一件事的兩面 —— 買回求償權的錢
    就是普通股 ATM 增發募來的。把稀釋單獨拿出來當壞消息、或把回購單獨拿出來當
    好消息,都會得到錯的結論。所以頁面上一定要把「主動操作合計」擺在細項之前。
"""
from __future__ import annotations

import math
from itertools import permutations
from typing import Dict, Iterable, Sequence

FACTORS = ("held", "claims", "price", "shares")
_PERMS = tuple(permutations(FACTORS))


def cebe_sats(held: float, claims_usd: float, price: float, shares: float) -> float:
    """每股實際對應的比特幣(sats)。求償權先用當下幣價換算成幣,再扣掉。"""
    if price <= 0 or shares <= 0:
        raise ValueError("price 與 shares 必須為正")
    return (held - claims_usd / price) / shares * 1e8


def cebe_of(st: Dict[str, float]) -> float:
    """吃 {held, claims, price, shares} 這組狀態,回傳每股含幣量(sats)。"""
    return cebe_sats(st["held"], st["claims"], st["price"], st["shares"])


# 內部仍沿用短名,測試與既有呼叫都指向同一個函式
_cebe = cebe_of


def shapley_cebe(start: Dict[str, float], end: Dict[str, float]) -> Dict[str, float]:
    """四個因子各自對 ΔCEBE 的貢獻(sats)。四項加總精確等於 ΔCEBE。"""
    out = {f: 0.0 for f in FACTORS}
    for order in _PERMS:
        cur = dict(start)
        prev = _cebe(cur)
        for f in order:
            cur[f] = end[f]
            now = _cebe(cur)
            out[f] += now - prev
            prev = now
    return {f: v / len(_PERMS) for f, v in out.items()}


def counterfactual_cebe(start: Dict[str, float], end_price: float) -> float:
    """「什麼都不做」的每股含幣量:結構凍結在期初,只讓幣價走到期末。

    這是使用者要的對照組 —— 求償權的面額固定在美元,所以就算公司完全不動作,
    幣價上漲一樣會讓它在幣計價下縮水、每股含幣量自己上升。
    真正屬於資本操作的貢獻,是實際值減掉這條基準線。
    """
    return cebe_sats(start["held"], start["claims"], end_price, start["shares"])


def price_layers(mnav0: float, cebe0: float, btc0: float,
                 mnav1: float, cebe1: float, btc1: float) -> Dict[str, float]:
    """三層乘法恆等式的對數拆解。回傳每層的對數變化量,三者加總等於總對數變化。

    用對數是因為三個因子是相乘的:log 之後變成相加,拆解沒有殘差、
    也不需要決定誰先誰後。
    """
    for v in (mnav0, cebe0, btc0, mnav1, cebe1, btc1):
        if v <= 0:
            raise ValueError("三層拆解要求所有因子為正")
    return {
        "mnav": math.log(mnav1 / mnav0),
        "cebe": math.log(cebe1 / cebe0),
        "btc": math.log(btc1 / btc0),
    }


def share_of(layers: Dict[str, float]) -> Dict[str, float]:
    """各層佔總變化的百分比。總變化接近零時回傳空 dict,不硬除。"""
    total = sum(layers.values())
    if abs(total) < 1e-9:
        return {}
    return {k: v / total * 100 for k, v in layers.items()}


def flows_between(weekly: Iterable[dict], start: str, end: str) -> Dict[str, float]:
    """區間內的實際動作量,用來佐證歸因的方向(買賣幣、募資)。"""
    rows = [w for w in weekly if start <= w["week_end"] <= end]
    return {
        "btcBought": sum(w["delta"] for w in rows if (w["delta"] or 0) > 0),
        "btcSold": -sum(w["delta"] for w in rows if (w["delta"] or 0) < 0),
        "weeks": len(rows),
    }
