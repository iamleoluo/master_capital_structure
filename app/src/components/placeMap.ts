/** 四個位置的圖 —— 推導「工具」那一層的主軸。
 *
 *  每一個資本操作都是同一件事:把錢在四個位置之間搬。因為位置只有四個,
 *  **動作就是可窮舉的** —— 這是「工具列得完」這個主張的根據,
 *  而不是「我們想到這幾個」。
 *
 *  ⚠️ U 畫在正中央,但它**不是第四種資本**。除了可轉債轉股,每一條箭頭都
 *  經過它 —— 而那正是它最不值得停留的理由:它是**管道**,不是目的地。
 *  所以 U 用虛線畫,與其餘三個實線方塊區分開。
 *  公司的三層定位(數位資本/股權/信貸)對應的是 H / S / DL,U 不在裡面。
 *
 *  資料來自 formulas.json(公式解),沒有任何觀測值。 */
import { F, PLACE, type Formula } from "../formulas";

/** 位置在圖上的座標。U 在中心 —— 因為它是管道,不是因為它重要。 */
const POS: Record<string, [number, number]> = {
  H: [130, 76], S: [470, 76], U: [300, 190], OUT: [130, 304], DL: [470, 304],
};
const W = 600, HGT = 380, BW = 150, BH = 54;

/** 方塊上只放短名 —— 完整定義在符號表,圖上塞不下也不該塞。 */
const short = (id: string) => (PLACE[id] ?? id).split("(")[0]!;

const box = (id: string, accent: string) => {
  const [x, y] = POS[id]!;
  // U 是管道,不是資本層 —— 用虛線與較低的筆畫權重,避免它看起來與其他三個同級
  const conduit = id === "U";
  return `
    <g>
      <rect x="${x - BW / 2}" y="${y - BH / 2}" width="${BW}" height="${BH}" rx="8"
            fill="var(--surface-2)" stroke="${accent}"
            stroke-width="${conduit ? 1 : 1.5}"
            ${conduit ? 'stroke-dasharray="5 4" opacity="0.75"' : ""}/>
      <text x="${x}" y="${y - 4}" text-anchor="middle"
            style="font:600 13px var(--sans);fill:var(--ink)">${short(id)}</text>
      <text x="${x}" y="${y + 13}" text-anchor="middle"
            style="font:11px var(--mono);fill:var(--ink-3)">${id}</text>
    </g>`;
};

/** 從方塊邊緣到方塊邊緣的直線,兩端各留一點空隙。 */
function edge(a: string, b: string): [number, number, number, number] {
  const [ax, ay] = POS[a]!, [bx, by] = POS[b]!;
  const dx = bx - ax, dy = by - ay;
  const len = Math.hypot(dx, dy);
  // 以方塊的半寬/半高估一個退縮量,避免箭頭插進字裡
  const back = (t: number) => {
    const sx = Math.abs(dx) / len, sy = Math.abs(dy) / len;
    return Math.min(sx ? (BW / 2 + 8) / sx : 1e9, sy ? (BH / 2 + 8) / sy : 1e9) * t;
  };
  const s = back(1) / len, e = back(1) / len;
  return [ax + dx * s, ay + dy * s, bx - dx * e, by - dy * e];
}

/** 一條箭頭。offset 讓同一對位置的來回兩條不重疊。 */
function arrow(t: Formula, offset: number, accent: string): string {
  const [a, b] = [t.moves[0]!, t.moves[t.moves.length - 1]!];
  const [x1, y1, x2, y2] = edge(a, b);
  const nx = -(y2 - y1), ny = x2 - x1;
  const n = Math.hypot(nx, ny) || 1;
  const [ox, oy] = [(nx / n) * offset, (ny / n) * offset];
  return `
    <g class="pm-arrow" data-tool="${t.id}">
      <line x1="${x1 + ox}" y1="${y1 + oy}" x2="${x2 + ox}" y2="${y2 + oy}"
            stroke="${accent}" stroke-width="1.6" marker-end="url(#pm-head)"/>
      <title>${t.label}</title>
    </g>`;
}

export function placeMap(): string {
  const atoms = F.tools.filter((t) => t.kind === "atom");
  const tone = (t: Formula) =>
    t.moves[1] === "OUT" ? "var(--bad)"
      : t.moves.includes("H") ? "var(--btc)" : "var(--equity)";

  // 連接同一對位置的箭頭要錯開,否則會疊成一條。
  // U↔DL 之間有三條(優先股發行、可轉債發行、折價回購),所以不能只分正負。
  const key = (t: Formula) => [t.moves[0], t.moves[t.moves.length - 1]].sort().join("");
  const total = new Map<string, number>();
  atoms.forEach((t) => total.set(key(t), (total.get(key(t)) ?? 0) + 1));
  const seen = new Map<string, number>();
  const arrows = atoms.map((t) => {
    const k = key(t);
    const i = seen.get(k) ?? 0;
    seen.set(k, i + 1);
    const n = total.get(k)!;
    // n 條平均分布在 ±9 之間;單獨一條就走正中間
    const off = n === 1 ? 0 : -9 + (18 * i) / (n - 1);
    return arrow(t, off, tone(t));
  }).join("");

  return `
    <figure class="place-map">
      <svg viewBox="0 0 ${W} ${HGT}" role="img"
           aria-label="四個位置與九條箭頭:資本只在比特幣、美元流動性、求償權、股數之間移動">
        <defs>
          <marker id="pm-head" viewBox="0 0 8 8" refX="7" refY="4"
                  markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0 L8 4 L0 8 z" fill="context-stroke"/>
          </marker>
        </defs>
        ${arrows}
        ${box("H", "var(--btc)")}
        ${box("S", "var(--equity)")}
        ${box("U", "var(--ink-3)")}
        ${box("DL", "var(--convert)")}
        ${box("OUT", "var(--bad)")}
      </svg>
      <figcaption>
        <b>${PLACE["U"]} 是樞紐。</b>除了可轉債轉股(${PLACE["DL"]} → ${PLACE["S"]},
        債主直接換股、沒有現金),每一條箭頭都經過它 ——
        錢要先變成現金,才能往下一步走。
      </figcaption>
    </figure>`;
}
