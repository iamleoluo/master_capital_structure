/** 資料入口 —— 靜態 import,讓 dev 與單檔 artifact 兩種模式都能運作。 */
import dailyJson from "../data/daily.json";
import weeklyJson from "../data/weekly.json";
import metaJson from "../data/meta.json";
import chronicleJson from "../data/chronicle.json";
import type { Daily, Era, Meta, Week } from "./types";

export const daily = dailyJson as unknown as Daily;
export const weekly = weeklyJson as unknown as Week[];
export const meta = metaJson as unknown as Meta;
/** 大事記,依時間正序;前端顯示時倒序(最新在上)。 */
export const chronicle = chronicleJson as unknown as Era[];

export const N = daily.date.length;

/** 日期字串 → 索引。找不到就取第一個不早於它的。 */
export function indexOfDate(d: string): number {
  const i = daily.date.indexOf(d);
  if (i >= 0) return i;
  for (let j = 0; j < N; j++) if (daily.date[j]! >= d) return j;
  return N - 1;
}
