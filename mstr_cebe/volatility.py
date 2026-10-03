"""已實現波動率:把「波動阻尼」從宣稱變成量測。

公司對數位信貸的工程主張是:**用結構化手段把底層資產的權益端年化波動
剝離 50%–70%**,讓優先股變成價格錨定面額的固定收益替代品。

那是一個**可以被打臉的宣稱** —— 我們有五檔優先股、MSTR 與 BTC 的日線,
算一下就知道。這支模組做那件事。

⚠️ 用已實現波動(歷史報酬的標準差),不是隱含波動。
隱含波動要選擇權鏈,我們沒有歸檔;而且這裡要回答的是
「**實際上**抖不抖」,不是「市場預期它會多抖」。

口徑寫下來(規則 4):
  * 對數日報酬,樣本標準差,乘 √365 年化 —— 日曆日而非交易日,
    因為 BTC 七天都在交易,換成 √252 會讓 BTC 與優先股不可比;
  * 視窗內少於 6 個報酬就回 None,不要用 2、3 個點硬算一個標準差;
  * 缺值(停牌、尚未上市)直接跳過,不補值 —— 補值會把波動壓低。
"""
from __future__ import annotations

import math
import statistics
from typing import Dict, List, Optional, Sequence

#: 年化係數的基底。日曆日 —— 見模組 docstring。
DAYS_PER_YEAR = 365

#: 視窗內最少要有幾個報酬才算
MIN_RETURNS = 6


def log_returns(prices: Sequence[Optional[float]]) -> List[float]:
    """相鄰兩個**都有值**的價格之間的對數報酬。"""
    out: List[float] = []
    prev: Optional[float] = None
    for px in prices:
        if px and px > 0:
            if prev:
                out.append(math.log(px / prev))
            prev = px
    return out


def realized_vol(prices: Sequence[Optional[float]],
                 window: int = 30) -> Optional[float]:
    """最後 `window` 天的年化已實現波動率;樣本不足回 None。"""
    rets = log_returns(list(prices)[-(window + 1):])
    if len(rets) < MIN_RETURNS:
        return None
    return statistics.stdev(rets) * math.sqrt(DAYS_PER_YEAR)


def vol_series(prices: Sequence[Optional[float]],
               window: int = 30) -> List[Optional[float]]:
    """逐日的滾動已實現波動率,長度與輸入相同。"""
    return [realized_vol(prices[: i + 1], window) for i in range(len(prices))]


def ladder(series: Dict[str, Sequence[Optional[float]]],
           window: int = 30) -> Dict[str, Optional[float]]:
    """一組代碼 → 最新的年化已實現波動率。"""
    return {k: realized_vol(v, window) for k, v in series.items()}


def damping(instrument_vol: Optional[float],
            equity_vol: Optional[float]) -> Optional[float]:
    """相對普通股剝離掉的波動比例。

    **分母是普通股不是 BTC。** 公司的主張是「剝離權益端的波動」——
    普通股才是那個承接全部剩餘波動的位置。拿 BTC 當分母會低估阻尼效果,
    因為普通股本身就已經把 BTC 的波動放大了。
    """
    if not instrument_vol or not equity_vol:
        return None
    return 1.0 - instrument_vol / equity_vol
