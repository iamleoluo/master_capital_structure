import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// 兩種建置模式:
//   預設      → 一般多檔輸出,配 npm run dev 用
//   --mode artifact → 把 JS/CSS/JSON 全部 inline 成單一 HTML,
//                     好讓成果能以 artifact 形式分享(CSP 禁止外部請求)
/** KaTeX 的 @font-face 為每個字型列了 woff2 / woff / ttf 三種來源。
 *  woff2 是所有目標瀏覽器都支援的,另外兩種只是舊瀏覽器的退路,
 *  卻佔掉 876KB(woff2 本身只有 296KB)—— artifact 模式會把它們
 *  全部 base64 inline 進單一 HTML,所以在這裡先剃掉。 */
const katexWoff2Only = {
  name: "katex-woff2-only",
  // pre:一定要趕在 Vite 內建的 css plugin 把 url() 改寫成資產參照之前動手,
  // 否則這裡看到的已經不是原始的 url(fonts/…) 字串了
  enforce: "pre" as const,
  transform(code: string, id: string) {
    if (!id.includes("katex") || !id.includes(".css")) return null;
    return {
      code: code.replace(
        /,url\(([^)]*\.(?:woff|ttf))\) format\("(?:woff|truetype)"\)/g, ""),
      map: null,
    };
  },
};

export default defineConfig(({ mode }) => ({
  base: "./",
  plugins: mode === "artifact"
    ? [katexWoff2Only, viteSingleFile()]
    : [katexWoff2Only],
  build: {
    outDir: mode === "artifact" ? "dist-artifact" : "dist",
    emptyOutDir: true,
    // 資料以 import 靜態帶入,單檔模式下不能拆 chunk
    assetsInlineLimit: mode === "artifact" ? 100_000_000 : 4096,
    chunkSizeWarningLimit: 2000,
  },
}));
