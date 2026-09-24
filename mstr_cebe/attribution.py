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
import random
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


# ---------------------------------------------------------------------------
# 操作層級拆解 —— 比四因子更接近「公司到底做了什麼決策」
#
# 四因子(持幣/求償權/幣價/股數)拆的是**會計結果**,不是操作:一筆 ATM 增發
# 同時動到「股數」與「求償權」(募到的現金抵減求償權),所以把「股數 −17,357」
# 單獨拿出來看,不對應任何真實決策,而且會得到「增發是壞事」這種錯誤結論。
#
# 改用操作來拆之後,每一種操作對分子(held − claims/price)的效果有明確的代數:
#
#   用現金買幣 $X      持幣 +X/p、現金 −X ⇒ 求償權 +X   ⇒ 分子 +X/p − X/p = 0
#                      「買比特幣」對每股含幣量是<b>中性的</b>,這點最反直覺
#   賣幣換現金 $X      同理,也是 0
#   折價回購優先股      付現金 Y、消滅面額 Z(Z > Y)⇒ 求償權淨減 (Z−Y)
#                      ⇒ 只有<b>折價本身</b>進得了分子,不是整筆回購金額
#   ATM 增發           募資 $X ⇒ 求償權 −X;股數 +ΔS
#                      發行價 > 每股淨值時加分,低於則減分
#   股息與債息          現金流出 ⇒ 求償權增加 ⇒ 純負項(槓桿的持有成本)
#   幣價變動            對期初求償權:分子 +C(1/p₀ − 1/p₁)
#
# 同樣用 Shapley 對所有操作順序取平均,所以六項加總精確等於實際變化。
# ---------------------------------------------------------------------------

def _apply(st: Dict[str, float], op: Dict[str, float]) -> Dict[str, float]:
    n = dict(st)
    n["held"] += op.get("dheld", 0.0)
    n["claims"] += op.get("dclaims", 0.0)
    n["shares"] += op.get("dshares", 0.0)
    if "price" in op:
        n["price"] = op["price"]
    return n


# 超過這個操作數就改用抽樣:8 個操作有 40,320 種排列,乘上每個起始日會跑到不可接受。
_EXACT_MAX_OPS = 7
_SAMPLE_PERMS = 3000


def _orders(keys: Sequence[str]) -> Sequence[Sequence[str]]:
    """枚舉或抽樣排列。

    抽樣不會破壞加總恆等 —— 每一個排列的邊際貢獻本來就 telescoping 到總變化,
    所以任意一組排列取平均,總和仍然精確等於 ΔCEBE。抽樣只影響個別項的精度,
    而 3000 組對 8 個操作已經遠超收斂所需。用固定亂數種子讓建置可重現。
    """
    if len(keys) <= _EXACT_MAX_OPS:
        return list(permutations(keys))
    rng = random.Random(20260924)
    out = []
    for _ in range(_SAMPLE_PERMS):
        o = list(keys)
        rng.shuffle(o)
        out.append(o)
    return out


def shapley_operations(base: Dict[str, float],
                       ops: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    """各操作對 ΔCEBE 的貢獻(sats)。加總精確等於「全部操作套用後」的變化。

    ops 的每一項是一個狀態變換,例如
        {"atm": {"dclaims": -5.16e9, "dshares": 44.8e6}, "price": {"price": 86404}}
    """
    keys = list(ops)
    out = {k: 0.0 for k in keys}
    perms = _orders(keys)
    for order in perms:
        st = dict(base)
        prev = cebe_of(st)
        for k in order:
            st = _apply(st, ops[k])
            now = cebe_of(st)
            out[k] += now - prev
            prev = now
    return {k: v / len(perms) for k, v in out.items()}


def build_operations(*, raised: float, discount: float, obligations: float,
                     btc_bought_usd: float, btc_sold_usd: float,
                     d_held: float, d_shares: float, end_price: float,
                     residual: float,
                     pref_par_issued: float = 0.0, pref_proceeds: float = 0.0,
                     d_debt: float = 0.0) -> Dict[str, Dict[str, float]]:
    """把區間內的資金流組成 shapley_operations 要的操作表。

    residual 是對帳差額(債務贖回、營運支出、STRE 匯率、股數插值誤差、
    ATM 入帳時間差等未建模項)。刻意獨立成一項而不是攤進其他操作 ——
    攤進去會讓那些操作的數字看起來比實際精確。
    """
    return {
        "price": {"price": end_price},
        "atm": {"dclaims": -raised, "dshares": d_shares},
        "buyback": {"dclaims": -discount},
        "btc": {"dclaims": btc_bought_usd - btc_sold_usd, "dheld": d_held},
        "carry": {"dclaims": obligations},
        # 發優先股:拿到 proceeds(現金,抵減求償權),但掛上 par 的清算優先權。
        # IPO 價常低於 $100 面額(例如 STRC 發行價 $90),所以 par > proceeds,
        # 淨效果是求償權增加 —— 這就是 phantom growth 在代數上的樣子。
        "pref_issue": {"dclaims": pref_par_issued - pref_proceeds},
        # 可轉債餘額變動(發行為正、回購或轉股為負)
        "converts": {"dclaims": d_debt},
        "other": {"dclaims": residual},
    }


# ---------------------------------------------------------------------------
# Gross BPS(公司自己的 BTC Yield)—— 公式裡沒有幣價,所以天生乾淨
#
#     Gross BPS = 總持幣 ÷ 股數
#
# 注意這個式子<b>完全沒有幣價這一項</b>,也沒有求償權。所以:
#   優點:幣價怎麼波動都不影響它,想看「公司做了什麼」時不需要額外去污染
#   缺點:它看不見求償權,所以用發優先股的錢買幣會讓它上升 —— phantom growth
#
# 取對數後只剩兩個驅動因子,精確可加、沒有殘差、也不需要 Shapley:
#     log(BPS₁/BPS₀) = log(持幣₁/持幣₀) − log(股數₁/股數₀)
# ---------------------------------------------------------------------------

def gross_bps_layers(held0: float, shares0: float,
                     held1: float, shares1: float) -> Dict[str, float]:
    """兩個因子的對數拆解:持幣效果與股數效果,兩者加總 = log(BPS 比)。"""
    for v in (held0, shares0, held1, shares1):
        if v <= 0:
            raise ValueError("持幣與股數必須為正")
    return {
        "held": math.log(held1 / held0),
        "shares": -math.log(shares1 / shares0),
    }


def cebe_at_fixed_price(held: float, claims_usd: float, shares: float,
                        price: float) -> float:
    """把幣價釘在同一個值來算 CEBE —— 去掉幣價效果,但保留求償權。

    這是三種度量裡最適合衡量「操作績效」的一個:
      Gross BPS      沒有幣價(乾淨)但看不見求償權
      CEBE           看得見求償權但被幣價污染
      CEBE@固定幣價   兩者兼顧

    起點與終點都用同一個幣價代入,兩者相減就是純操作造成的變化。
    數學上這與「實際值 − 反事實(結構凍結、只讓幣價走)」完全相同。
    """
    return cebe_sats(held, claims_usd, price, shares)
