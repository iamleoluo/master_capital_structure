"""資本操作工具箱 —— 把公式、程式碼與判斷條件包成同一個物件。

設計論述在 reference/05-toolbox.md,這裡是實作。

核心觀察:整個系統早就有一個狀態

    x = (H, C, S) 加上當下幣價 p

而**每一把資本操作都只是這個狀態的一個轉移**。既然如此,一把工具就不該
散成三份互不相干的東西(LaTeX 一份、delta dict 一份、抽參數一份),
而該是一個物件:

    Tool.apply       狀態轉移 —— 唯一的真實語意
    Tool.accretive   加分條件 —— 可以拿 apply 去驗證它
    Tool.latex_e     代數 —— 文件與網頁共用同一份字串

`accretive` 能被 `apply` 驗證,是這個設計最重要的性質:代數不再是註解,
而是**會被測試打臉的宣告**(見 tests/test_toolbox.py)。

組合在型別上封閉 —— `compose()` 回傳的還是 `Tool`,所以組合可以再組合。
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Mapping, Optional, Sequence, Tuple

SATS = 1e8


# ---------------------------------------------------------------------------
# 狀態:四個量就足以決定一切
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class State:
    """資本結構在某一個瞬間的樣子。

    held   H — 總持幣(BTC)
    claims C — 求償權(USD),= 可轉債 + 優先股清算優先權 − USD 流動性
    shares S — 在外股數(basic)
    price  p — 幣價(USD)

    刻意不帶日期。工具不該知道時間 —— 時間是歸因層的事,
    工具只回答「這個動作把狀態變成什麼樣」。
    """
    held: float
    claims: float
    shares: float
    price: float


# ---------------------------------------------------------------------------
# 尺:狀態的純函數,沒有歷史、沒有副作用
# ---------------------------------------------------------------------------

def gross_bps(s: State) -> float:
    """帳面每股含幣量 B(sats)。式子裡沒有 p 也沒有 C。"""
    return s.held / s.shares * SATS


def cebe(s: State) -> float:
    """實得每股含幣量 E(sats)。扣掉求償權之後真正屬於普通股的。"""
    return (s.held - s.claims / s.price) / s.shares * SATS


def claims_per_share(s: State) -> float:
    """求償權吃掉的每股含幣量,恆等於 B − E。"""
    return s.claims / (s.price * s.shares) * SATS


def mnav(s: State, share_price: float) -> float:
    """CEBE mNAV —— 分母是**殘值**,不是全部持幣。

    這是股價恆等式 P = m × E/1e8 × p 裡的 m。與一般講的 mNAV 不是同一個數,
    見 reference/04-decisions.md。
    """
    return share_price / (cebe(s) / SATS * s.price)


def leverage(s: State) -> float:
    """每股殘值(美元)對幣價的彈性 A(p) = Hp/(Hp − C)。

    每股含幣量的彈性則是 A(p) − 1 —— 兩者剛好差一個 1。
    """
    nav = s.held * s.price
    return nav / (nav - s.claims) if nav > s.claims else float("inf")


def wipeout_price(s: State) -> float:
    """普通股殘值歸零的幣價 p₀ = C/H,也就是平均每顆幣背了多少美元求償權。"""
    return s.claims / s.held


# ---------------------------------------------------------------------------
# 工具:狀態轉移
# ---------------------------------------------------------------------------

Params = Mapping[str, float]
Apply = Callable[[State, Params], State]
Predicate = Callable[[State, Params], bool]


@dataclass(frozen=True)
class Tool:
    """一把資本操作。

    params      這把工具吃哪些輸入。c 美元金額、F 面額、n 股數、x 幣數、
                P 每股成交價 —— 符號與 reference/ 一致。
    apply       狀態轉移。唯一的真實語意,其餘欄位都是對它的描述或宣告。
    accretive   「這個動作讓 E 上升嗎」的判斷式。None 表示結構上恆中性。
                測試會拿 apply 去驗它,所以它不能說謊。
    latex_b/e   代數。網頁與 reference/ 共用這一份,不另外抄。
    """
    id: str
    label: str
    params: Tuple[str, ...]
    apply: Apply
    latex_b: str
    latex_e: str
    accretive: Optional[Predicate] = None
    note: str = ""

    def __call__(self, s: State, **kw: float) -> State:
        missing = [p for p in self.params if p not in kw]
        if missing:
            raise TypeError(f"{self.id} 缺少參數 {missing}(需要 {list(self.params)})")
        return self.apply(s, kw)


def effect(tool: Tool, s: State, **kw: float) -> dict:
    """這把工具對兩把尺各自做了什麼(sats／股)。

    兩欄要並排看 —— 不一致的地方就是這家公司最常被誤讀的地方。
    """
    after = tool(s, **kw)
    return {
        "dB": gross_bps(after) - gross_bps(s),
        "dE": cebe(after) - cebe(s),
    }


def efficiency(tool: Tool, s: State, capital: float, **kw: float) -> float:
    """資本效率:每投入一單位資本,換到多少實得每股含幣量。

    分母是「投入的美元換算成每股的聰」,所以回傳值是無單位的報酬率。
    折價回購的理論值是 d/(1−d) —— 折價 27% 就是 37% 的報酬,
    而用現金買幣是 0。這是決策層真正要比較的東西。
    """
    if capital <= 0:
        raise ValueError("capital 必須為正 —— 沒有投入就談不上效率")
    deployed = capital / (s.price * s.shares) * SATS
    return effect(tool, s, **kw)["dE"] / deployed


# --- 七把單一工具 ----------------------------------------------------------

BUY_BTC = Tool(
    id="buy_btc", label="用現金買幣", params=("c",),
    # 持幣增加 c/p,但美元流動性同額減少 ⇒ 求償權增加 c。分子兩項對消。
    apply=lambda s, k: replace(s, held=s.held + k["c"] / s.price,
                               claims=s.claims + k["c"]),
    accretive=None,                       # 結構上恆為零,不是「有時候」
    latex_b=r"\Delta B = \frac{c}{p\,S}\times 10^{8} > 0",
    latex_e=r"\Delta\!\left(H - \frac{C}{p}\right) = \frac{c}{p} - \frac{c}{p} = 0",
    note="買幣本身不創造價值。B 上升純粹因為它看不到錢是哪來的。",
)

SELL_BTC = Tool(
    id="sell_btc", label="賣幣進儲備", params=("x",),
    apply=lambda s, k: replace(s, held=s.held - k["x"],
                               claims=s.claims - k["x"] * s.price),
    accretive=None,
    latex_b=r"\Delta B = -\frac{x}{S}\times 10^{8} < 0",
    latex_e=r"\Delta E = \frac{-x + xp/p}{S}\times 10^{8} = 0",
    note="賣幣本身不會讓股東變窮。決定好壞的是那筆美元接下來拿去做什麼。",
)

ISSUE_PREFERRED = Tool(
    id="issue_preferred", label="優先股發行", params=("c", "F"),
    # 拿到 c 現金(求償權 −c),掛上面額 F 的清算優先權(求償權 +F)
    apply=lambda s, k: replace(s, claims=s.claims + k["F"] - k["c"]),
    accretive=lambda s, k: k["c"] > k["F"],      # 溢價發行才加分,實務上罕見
    latex_b=r"\Delta B = \frac{c}{p\,S}\times 10^{8} > 0",
    latex_e=r"\Delta E = \frac{c - F}{p\,S}\times 10^{8} \le 0",
    note="與 BUY_BTC 串起來就是 phantom growth:B 上升而 E 下降。",
)

BUYBACK_PREFERRED = Tool(
    id="buyback_preferred", label="折價回購求償權", params=("c", "F"),
    # 付 c 現金(求償權 +c),消滅面額 F(求償權 −F)
    apply=lambda s, k: replace(s, claims=s.claims + k["c"] - k["F"]),
    accretive=lambda s, k: k["c"] < k["F"],
    latex_b=r"\Delta B = 0",
    latex_e=r"\Delta E = \frac{F - c}{p\,S}\times 10^{8} > 0 \quad (c < F)",
    note="ΔB = 0 不是四捨五入,是結構上的零 —— B 的式子裡沒有求償權這一項。",
)

CARRY = Tool(
    id="carry", label="股息與債息", params=("c",),
    apply=lambda s, k: replace(s, claims=s.claims + k["c"]),
    accretive=lambda s, k: False,          # 唯一無條件為負的一項
    latex_b=r"\Delta B = 0",
    latex_e=r"\Delta E = -\frac{c}{p\,S}\times 10^{8} < 0",
    note="其餘每一種操作的正負都取決於價格條件,只有這一項無條件為負。",
)

COMMON_ATM = Tool(
    id="common_atm", label="普通股 ATM 增發", params=("n", "P"),
    apply=lambda s, k: replace(s, shares=s.shares + k["n"],
                               claims=s.claims - k["n"] * k["P"]),
    # 推導見 reference/02-operations.md §3:化簡到底就是 m > 1
    accretive=lambda s, k: mnav(s, k["P"]) > 1,
    latex_b=r"\Delta B > 0 \iff \frac{P}{p}\times 10^{8} > B",
    latex_e=r"\Delta E > 0 \iff \frac{P}{p}\times 10^{8} > E \iff m > 1",
    note="B 的門檻比 E 高(因為 B > E 恆成立),所以一次增發可以對 E 加分、"
         "同時對 B 減分。",
)

COMMON_BUYBACK = Tool(
    id="common_buyback", label="普通股回購", params=("n", "P"),
    apply=lambda s, k: replace(s, shares=s.shares - k["n"],
                               claims=s.claims + k["n"] * k["P"]),
    accretive=lambda s, k: mnav(s, k["P"]) < 1,
    latex_b=r"\Delta B = H\left(\frac{1}{S-n} - \frac{1}{S}\right)\times 10^{8} > 0",
    latex_e=r"\Delta E > 0 \iff \frac{P}{p}\times 10^{8} < E \iff m < 1",
    note="B 無條件上升但 m > 1 時 E 下降 —— 兩個指標正面打架。",
)

CONVERT_CONVERSION = Tool(
    id="convert_conversion", label="可轉債轉股", params=("F", "n"),
    apply=lambda s, k: replace(s, shares=s.shares + k["n"],
                               claims=s.claims - k["F"]),
    accretive=lambda s, k: mnav(s, k["F"] / k["n"]) > 1,   # 轉換價代替發行價
    latex_b=r"\Delta B = H\left(\frac{1}{S+n} - \frac{1}{S}\right)\times 10^{8} < 0",
    latex_e=r"\Delta E > 0 \iff \frac{F/n}{p}\times 10^{8} > E",
    note="求償權整筆消失,但沒有多出任何一顆幣,所以 B 被稀釋。",
)

TOOLS: Tuple[Tool, ...] = (
    BUY_BTC, SELL_BTC, ISSUE_PREFERRED, BUYBACK_PREFERRED,
    CARRY, COMMON_ATM, COMMON_BUYBACK, CONVERT_CONVERSION,
)


# ---------------------------------------------------------------------------
# 組合:在型別上封閉,所以組合可以再組合
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Step:
    """組合裡的一步:一把工具,加上「組合參數怎麼配到它」的接線。

    wire 收得到**那一步當下的狀態**,不只是參數 —— 因為有些接線需要它:
    賣幣換到多少現金要看幣價,而且後面那一步看到的應該是前一步之後的狀態。
    """
    tool: Tool
    wire: Callable[[State, Params], Params]


def compose(*, id: str, label: str, params: Tuple[str, ...],
            steps: Sequence[Step], latex_b: str, latex_e: str,
            accretive: Optional[Predicate] = None, note: str = "") -> Tool:
    """把數把工具串成一把。回傳的仍然是 Tool —— 這就是封閉性的意思。

    錢要先從某處來才能往某處去,所以真實世界的動作幾乎都是組合。
    串起來的語意就是依序套用,沒有別的魔法。
    """
    def apply(s: State, k: Params) -> State:
        for step in steps:
            s = step.tool(s, **step.wire(s, k))
        return s

    return Tool(id=id, label=label, params=params, apply=apply,
                latex_b=latex_b, latex_e=latex_e, accretive=accretive, note=note)


SELL_TO_BUYBACK = compose(
    id="sell_to_buyback", label="賣幣 → 折價回購優先股",
    params=("x", "F"),
    steps=(
        Step(SELL_BTC, lambda s, k: {"x": k["x"]}),
        # 賣幣換到的現金全部拿去回購,所以 c 由 x 與幣價決定,不是獨立參數
        Step(BUYBACK_PREFERRED,
             lambda s, k: {"c": k["x"] * s.price, "F": k["F"]}),
    ),
    accretive=lambda s, k: k["x"] * s.price < k["F"],
    latex_b=r"\Delta B = -\frac{x}{S}\times 10^{8} < 0",
    latex_e=r"\Delta E = \frac{F - c}{p\,S}\times 10^{8} > 0,\quad c = xp",
    note="賣幣那一步是中性的,回購那一步把折價收進來。所以整個組合的加分"
         "恰好等於折價本身,跟賣了多少幣無關。",
)

PREFERRED_TO_BTC = compose(
    id="preferred_to_btc", label="發優先股 → 買幣",
    params=("c", "F"),
    steps=(
        Step(ISSUE_PREFERRED, lambda s, k: {"c": k["c"], "F": k["F"]}),
        Step(BUY_BTC, lambda s, k: {"c": k["c"]}),
    ),
    accretive=lambda s, k: k["c"] > k["F"],
    latex_b=r"\Delta B = \frac{c}{p\,S}\times 10^{8} > 0",
    latex_e=r"\Delta E = \frac{c - F}{p\,S}\times 10^{8} \le 0",
    note="phantom growth 的完整形狀:B 漂亮地上升,而那些幣是借來的。",
)

ATM_TO_BUYBACK = compose(
    id="atm_to_buyback", label="ATM 增發 → 折價回購優先股",
    params=("n", "P", "d"),
    steps=(
        Step(COMMON_ATM, lambda s, k: {"n": k["n"], "P": k["P"]}),
        # ATM 那一步已經用募得的錢抵減求償權,這一步把那筆錢真的花掉去買回
        # 面額 F —— 兩步加總的淨效果是求償權 −F、股數 +n。
        # 折價 d 下同一筆錢能消滅的面額:c = F(1−d) ⇒ F = c/(1−d)
        Step(BUYBACK_PREFERRED,
             lambda s, k: {"c": k["n"] * k["P"],
                           "F": k["n"] * k["P"] / (1 - k["d"])}),
    ),
    # 門檻從 m > 1 降到 m > 1 − d,折價越深適用區間越寬
    accretive=lambda s, k: mnav(s, k["P"]) > 1 - k["d"],
    latex_b=r"\Delta B = H\left(\frac{1}{S+n} - \frac{1}{S}\right)\times 10^{8} < 0",
    latex_e=r"\Delta E > 0 \iff \frac{F/n}{p}\times 10^{8} > E \iff m > 1 - d",
    note="單純增發要 m > 1;錢拿去折價 d 買回優先股,門檻就降到 m > 1 − d。"
         "優先股被打到 73 折時門檻掉到 0.73 —— 即使普通股在折價交易,"
         "增發去買回優先股仍然加分。",
)

COMBOS: Tuple[Tool, ...] = (SELL_TO_BUYBACK, PREFERRED_TO_BTC, ATM_TO_BUYBACK)

BY_ID = {t.id: t for t in TOOLS + COMBOS}
