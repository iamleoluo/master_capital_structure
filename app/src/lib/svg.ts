/** SVG 組裝小工具。全部回傳字串,由呼叫端一次 innerHTML 寫入。 */

export const NS = "http://www.w3.org/2000/svg";

export const esc = (s: string): string =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
   .replace(/"/g, "&quot;");

export function path(points: Array<[number, number]>, close = false): string {
  if (!points.length) return "";
  const d = points.map((p, i) => (i === 0 ? "M" : "L") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ");
  return close ? d + " Z" : d;
}

/** 上下兩條邊界線圍成的面積(堆疊圖用)。 */
export function band(top: Array<[number, number]>, bottom: Array<[number, number]>): string {
  if (!top.length) return "";
  const up = top.map((p, i) => (i === 0 ? "M" : "L") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ");
  const down = bottom.slice().reverse()
    .map((p) => "L" + p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ");
  return `${up} ${down} Z`;
}

export function text(x: number, y: number, s: string, opts: {
  size?: number; anchor?: "start" | "middle" | "end"; fill?: string;
  weight?: number | string; opacity?: number; mono?: boolean;
} = {}): string {
  const { size = 10, anchor = "start", fill = "currentColor",
          weight, opacity, mono } = opts;
  const attrs = [
    `x="${x.toFixed(1)}"`, `y="${y.toFixed(1)}"`,
    `font-size="${size}"`, `text-anchor="${anchor}"`, `fill="${fill}"`,
    weight ? `font-weight="${weight}"` : "",
    opacity != null ? `opacity="${opacity}"` : "",
    mono ? `font-family="var(--mono)"` : "",
  ].filter(Boolean).join(" ");
  return `<text ${attrs}>${esc(s)}</text>`;
}

export function line(x1: number, y1: number, x2: number, y2: number, opts: {
  stroke?: string; width?: number; dash?: string; opacity?: number;
} = {}): string {
  const { stroke = "currentColor", width = 1, dash, opacity } = opts;
  return `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" `
    + `stroke="${stroke}" stroke-width="${width}"`
    + (dash ? ` stroke-dasharray="${dash}"` : "")
    + (opacity != null ? ` stroke-opacity="${opacity}"` : "") + "/>";
}

export function rect(x: number, y: number, w: number, h: number, fill: string,
                     opts: { opacity?: number; rx?: number } = {}): string {
  return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(0, w).toFixed(1)}" `
    + `height="${Math.max(0, h).toFixed(1)}" fill="${fill}"`
    + (opts.opacity != null ? ` opacity="${opts.opacity}"` : "")
    + (opts.rx ? ` rx="${opts.rx}"` : "") + "/>";
}

export function svg(w: number, h: number, body: string, label: string): string {
  return `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(label)}" `
    + `preserveAspectRatio="xMidYMid meet">${body}</svg>`;
}
