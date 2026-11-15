/** 設計約束：顏色只在 token，方法徽章只有七個名字，圖只從 charts/ 畫。 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { METHOD_LABEL } from "../src/metrics/asof";

const METHODS = ["observed", "step", "carry", "linear", "spliced", "reconstructed", "assumed"];

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(ts|css)$/.test(p)) out.push(p);
  }
  return out;
}

describe("設計 token", () => {
  it("十六進位色碼只出現在 tokens.css", () => {
    const hits: string[] = [];
    for (const file of walk("src")) {
      if (file.endsWith("tokens.css")) continue;
      const text = readFileSync(file, "utf8");
      if (/#[0-9A-Fa-f]{3,8}\b/.test(text)) hits.push(file);
    }
    expect(hits).toEqual([]);
  });

  it("--bad 與 --senti 不同，兩段暗色相同", () => {
    const css = readFileSync("src/styles/tokens.css", "utf8");
    const bad = [...css.matchAll(/--bad:(#[0-9A-Fa-f]{6})/g)].map((m) => m[1]);
    const senti = [...css.matchAll(/--senti:(#[0-9A-Fa-f]{6})/g)].map((m) => m[1]);
    expect(bad).toEqual(["#8E2F3A", "#E07A78", "#E07A78"]);
    expect(senti).toEqual(["#B23E58", "#DE8296", "#DE8296"]);
    for (let i = 0; i < bad.length; i++) expect(bad[i]).not.toBe(senti[i]);
  });
});

describe("方法徽章與圖", () => {
  it("data-method 只有七個方法名", () => {
    expect(Object.keys(METHOD_LABEL).sort()).toEqual([...METHODS].sort());
    const hits: string[] = [];
    for (const file of walk("src")) {
      const text = readFileSync(file, "utf8");
      for (const m of text.matchAll(/data-method="([^"$]+)"/g)) {
        if (!METHODS.includes(m[1]!)) hits.push(`${file}: ${m[1]}`);
      }
    }
    expect(hits).toEqual([]);
  });

  it("金額函式只從 format.ts 匯出", () => {
    const hits: string[] = [];
    for (const file of walk("src")) {
      if (file.endsWith("lib/format.ts")) continue;
      const text = readFileSync(file, "utf8");
      if (/export (const|function) (usd|bn|sats|usd0|mn)\b/.test(text)) hits.push(file);
    }
    expect(hits).toEqual([]);
  });

  it("draw 函式只放在 charts/", () => {
    const hits: string[] = [];
    for (const file of walk("src")) {
      if (file.includes("/charts/")) continue;
      const text = readFileSync(file, "utf8");
      if (/export function draw/.test(text)) hits.push(file);
    }
    expect(hits).toEqual([]);
  });
});
