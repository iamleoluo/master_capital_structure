/** 頁面登錄。導覽與舊網址都從這裡來。 */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { PAGES } from "../src/pages/registry";
import { resolvePath } from "../src/router";

const TYPES = ["reading", "method", "note", "source"] as const;

describe("頁面登錄", () => {
  it("每一頁都有四種型別之一，推導頁是方法頁", () => {
    for (const p of PAGES) expect(TYPES).toContain(p.type);
    for (const p of PAGES.filter((r) => r.path.startsWith("/lecture"))) {
      expect(p.type).toBe("method");
    }
    expect(PAGES.find((p) => p.path === "/provenance")!.type).toBe("source");
    expect(PAGES.find((p) => p.path === "/posts")!.type).toBe("note");
    expect(PAGES.find((p) => p.path === "/")!.type).toBe("reading");
  });

  it("舊路徑導到現在的路徑，而且不撞上正式路徑", () => {
    const paths = new Set(PAGES.map((p) => p.path));
    expect(resolvePath("/overview", PAGES)).toBe("/");
    expect(resolvePath("/dashboard", PAGES)).toBe("/board");
    expect(resolvePath("/sources", PAGES)).toBe("/provenance");
    expect(resolvePath("/pricing", PAGES)).toBe("/pricing");
    for (const p of PAGES) {
      for (const old of p.redirectFrom ?? []) expect(paths.has(old)).toBe(false);
    }
  });

  it("主導覽不是在 main.ts 再寫一份標題", () => {
    const main = readFileSync("src/main.ts", "utf8");
    expect(main).toContain("PAGES");
    expect(main).not.toContain('title: "總覽"');
    expect(main).toContain("nav-toggle");
  });
});
