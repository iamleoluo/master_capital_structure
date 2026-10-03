/** 資料入口 —— 靜態 import,讓 dev 與單檔 artifact 兩種模式都能運作。 */
import dailyJson from "../data/daily.json";
import weeklyJson from "../data/weekly.json";
import metaJson from "../data/meta.json";
import chronicleJson from "../data/chronicle.json";
import strategyJson from "../data/strategy.json";
import operationsJson from "../data/operations.json";
import postsJson from "../data/posts.json";
import type { Daily, Era, Meta, Operation, Post, Strategy, Week } from "./types";

export const daily = dailyJson as unknown as Daily;
export const weekly = weeklyJson as unknown as Week[];
export const meta = metaJson as unknown as Meta;
/** 大事記,依時間正序;前端顯示時倒序(最新在上)。 */
export const chronicle = chronicleJson as unknown as Era[];
/** 策略歸因,rows 以 daily.date 的索引對齊 */
export const strategy = strategyJson as unknown as Strategy;

/** L3 的具名資本操作,依期末正序。儀表板的「工具」與「配對」兩頁吃它。 */
export const operations = operationsJson as unknown as Operation[];

/** 觀點,依日期倒序(最新在上)。 */
export const posts = postsJson as unknown as Post[];

export const N = daily.date.length;

/** 日期字串 → 索引。找不到就取第一個不早於它的。 */
export function indexOfDate(d: string): number {
  const i = daily.date.indexOf(d);
  if (i >= 0) return i;
  for (let j = 0; j < N; j++) if (daily.date[j]! >= d) return j;
  return N - 1;
}
