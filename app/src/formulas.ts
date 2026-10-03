/** 公式解的資料入口 —— **講義只准 import 這一個檔案**。
 *
 *  `app/data/formulas.json` 裡沒有任何觀測值:位置、工具、組合、各自的代數
 *  與判準,全部來自 Python 的 `toolbox`。改了幣價也不會變一個字。
 *
 *  為什麼不直接吃 `meta.toolkit`:`meta.json` 裡有大量數值(錨點、findings、
 *  敏感度表),讓講義 import 它就等於把數值解的大門開著。
 *  見 CLAUDE.md 的「公式解 vs 數值解」。 */
import formulasJson from "../data/formulas.json";

export interface Place { id: string; label: string }

export interface Formula {
  id: string; label: string;
  /** atom = 單一狀態轉移(L2);combo = 兩步以上串成(L3) */
  kind: "atom" | "combo";
  /** 經過的位置。原子兩點,組合三點以上、中間永遠是 U */
  moves: string[];
  /** ↑ / ↓ / — 。claims 可能是 "?" —— 見 toolbox.arrows 的說明 */
  btc: string; claims: string; shares: string;
  /** 判準的中文說法 */
  cebe: string;
  note: string;
  /** 代數(LaTeX)。bps = 對帳面每股 B,eq = 對實得每股 E */
  bps: string; eq: string;
}

export interface Formulas {
  places: Place[];
  assets: string[];
  sources: string[];
  tools: Formula[];
}

export const F = formulasJson as unknown as Formulas;

export const PLACE = Object.fromEntries(F.places.map((p) => [p.id, p.label]));
export const atoms = F.tools.filter((t) => t.kind === "atom");
export const combos = F.tools.filter((t) => t.kind === "combo");
export const byId = Object.fromEntries(F.tools.map((t) => [t.id, t]));
