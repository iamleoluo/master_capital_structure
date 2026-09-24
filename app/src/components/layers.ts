/** 四層報酬歸因 —— 績效歸因與大事記共用同一個口徑與同一段程式碼。
 *
 *  股價恆等式取對數之後三層相加(見資本結構頁):
 *      ln(P₁/P₀) = ln(p₁/p₀) + ln(E₁/E₀) + ln(m₁/m₀)
 *  但中間那層同時裝了「公司的操作」與「求償權被幣價縮放」兩件不同的事,
 *  所以再用逐日鏈結在對數空間切一刀,一共四層。四層相加仍精確等於總報酬。 */

export const LAYER_ORDER = ["btc", "decision", "claims", "mnav"] as const;
export type LayerKey = (typeof LAYER_ORDER)[number];
/** 各層的對數貢獻。 */
export type Layers4 = Record<LayerKey, number>;

/** 只有「公司決策」是公司控制得了的,其餘三層都不是。 */
export const CONTROLLED: LayerKey = "decision";

const LABEL: Record<LayerKey, string> = {
  btc: "比特幣價格",
  decision: "公司決策",
  claims: "求償權縮放",
  mnav: "市場溢價(mNAV)",
};
const NOTE: Record<LayerKey, string> = {
  btc: "底層資產本身漲跌。公司做什麼都改變不了它",
  decision: "增發、回購、買賣幣、付息 —— 唯一真正由公司決定的一層,"
    + "而且每筆都用它發生當下的幣價評價,不含後見之明",
  claims: "求償權面額鎖死在美元,幣價一漲它在幣計價下就自己縮小,"
    + "每股含幣量不用多買一顆就上升。這是槓桿的被動效果,不是決策",
  mnav: "市場願意付幾倍,情緒與流動性。公司只能間接影響",
};
const COLOR: Record<LayerKey, string> = {
  btc: "var(--btc)", decision: "var(--equity)",
  claims: "var(--c3)", mnav: "var(--senti)",
};

const pct1 = (v: number) => (v >= 0 ? "+" : "") + v.toFixed(1) + "%";
/** 對數貢獻 → 這一層自己的漲跌幅。四層相乘 = 總報酬。 */
export const ownPct = (log: number) => (Math.exp(log) - 1) * 100;

export interface LayerStats {
  total: number;        // 四層對數加總 = ln(總報酬比)
  gross: number;        // 各層絕對值加總
  company: number;      // 公司決策那一層
  other: number;        // 其餘三層
  /** 各層互相抵銷得夠嚴重,「佔淨報酬幾%」會爆掉(158%、−100% 這種) */
  offsetting: boolean;
}

export function layerStats(L: Layers4): LayerStats {
  const total = LAYER_ORDER.reduce((a, k) => a + L[k], 0);
  const gross = LAYER_ORDER.reduce((a, k) => a + Math.abs(L[k]), 0);
  return {
    total, gross,
    company: L[CONTROLLED],
    other: total - L[CONTROLLED],
    // 1.6 倍:各層方向大致一致時是 1.0,開始互相吃掉才會拉高
    offsetting: gross > 1.6 * Math.abs(total),
  };
}

/** 「公司做出來的」對上「行情與情緒給的」。兩者相乘 = 總報酬。 */
export function companySplit(st: LayerStats): string {
  return `
    <div class="split-row">
      <div class="split-cell ${st.company >= 0 ? "good" : "bad"}">
        <div class="k">公司決策做出來的</div>
        <div class="v">${pct1(ownPct(st.company))}</div>
        <div class="d">佔變動量 ${
          ((Math.abs(st.company) / Math.max(st.gross, 1e-9)) * 100).toFixed(0)}%</div></div>
      <div class="split-cell muted">
        <div class="k">行情與情緒給的</div>
        <div class="v">${pct1(ownPct(st.other))}</div>
        <div class="d">幣價 + 求償權縮放 + mNAV,公司控制不了</div></div>
      <div class="split-cell">
        <div class="k">相乘 = 總報酬</div>
        <div class="v">${pct1(ownPct(st.total))}</div>
        <div class="d">四層無殘差</div></div>
    </div>`;
}

/** 抵銷時的提醒。不抵銷就不出現。 */
export function offsetNote(L: Layers4, st: LayerStats): string {
  if (!st.offsetting) return "";
  const up = LAYER_ORDER.filter((k) => L[k] > 0);
  const down = LAYER_ORDER.filter((k) => L[k] < 0);
  const name = (ks: LayerKey[]) =>
    ks.map((k) => `${LABEL[k]} ${pct1(ownPct(L[k]))}`).join("、");
  return `
    <div class="note warn" style="margin-top:0">
      <b>這段期間各層互相抵銷,所以「佔總報酬幾 %」不能看。</b>
      ${name(up)} 往上推,${name(down)} 往下拉,
      兩邊大致相消之後總報酬只剩 ${pct1(ownPct(st.total))} ——
      各層絕對值加起來是淨額的 ${(st.gross / Math.abs(st.total)).toFixed(1)} 倍。
      用這種淨額當分母會算出 158%、−100% 這種讀不懂的數字,
      所以下面改標<b>「佔變動量」</b>:各層絕對值佔全部變動的比例,必定落在 0–100%。
      每一層<b>自己的漲跌幅</b>則永遠是精確的,四層相乘就是總報酬。
    </div>`;
}

/** 四條橫條。 */
export function layerBars(L: Layers4, st: LayerStats): string {
  const max = Math.max(...LAYER_ORDER.map((k) => Math.abs(L[k])), 1e-9);
  return `
    <div class="layer-list">
      ${LAYER_ORDER.map((k) => {
        const v = L[k];
        const share = (Math.abs(v) / Math.max(st.gross, 1e-9)) * 100;
        const w = (Math.abs(v) / max) * 100;
        return `
          <div class="layer">
            <div class="layer-head">
              <span class="layer-name"><i class="swatch" style="background:${COLOR[k]}"></i>${
                LABEL[k]}<span class="passive-tag">${
                  k === CONTROLLED ? "公司" : "被動"}</span></span>
              <span class="layer-vals">
                <b class="${v >= 0 ? "up" : "down"}">${pct1(ownPct(v))}</b>
                <span class="layer-share">佔變動量 ${share.toFixed(0)}%</span>
              </span>
            </div>
            <div class="layer-bar"><i style="width:${w.toFixed(1)}%;background:${COLOR[k]};
              ${v < 0 ? "opacity:.45" : ""}"></i></div>
            <div class="layer-note">${NOTE[k]}</div>
          </div>`;
      }).join("")}
    </div>`;
}

/** 完整區塊:總結 + 抵銷提醒 + 四條橫條。 */
export function layersBlock(L: Layers4): string {
  const st = layerStats(L);
  return companySplit(st) + offsetNote(L, st) + layerBars(L, st);
}
