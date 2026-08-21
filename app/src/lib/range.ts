/** 放大燈箱的時間範圍篩選。全部範圍都是「以最新一天為終點,往回抓 X」——
 *  資料的終點(N-1)永遠不變,只有起點往前推,所以圖表右緣的「今天」標籤
 *  永遠有效,不用因為換範圍而重算。 */
import { daily, N } from "../data";

export type RangeKey = "all" | "2y" | "1y" | "6m" | "3m" | "1m";

export const RANGE_LABEL: Record<RangeKey, string> = {
  all: "全部", "2y": "兩年", "1y": "一年", "6m": "六個月", "3m": "三個月", "1m": "一個月",
};

const RANGE_DAYS: Record<Exclude<RangeKey, "all">, number> = {
  "2y": 730, "1y": 365, "6m": 182, "3m": 91, "1m": 30,
};

/** 回傳 [startIdx, endIdx](含頭尾)。endIdx 永遠是 N-1。 */
export function rangeIndices(key: RangeKey): [number, number] {
  const end = N - 1;
  if (key === "all") return [0, end];
  const days = RANGE_DAYS[key];
  const endDate = new Date(daily.date[end]!).getTime();
  const cutoff = endDate - days * 86_400_000;
  let start = daily.date.findIndex((d) => new Date(d).getTime() >= cutoff);
  if (start < 0) start = 0;
  return [start, end];
}
