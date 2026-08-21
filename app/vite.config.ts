import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// 兩種建置模式:
//   預設      → 一般多檔輸出,配 npm run dev 用
//   --mode artifact → 把 JS/CSS/JSON 全部 inline 成單一 HTML,
//                     好讓成果能以 artifact 形式分享(CSP 禁止外部請求)
export default defineConfig(({ mode }) => ({
  base: "./",
  plugins: mode === "artifact" ? [viteSingleFile()] : [],
  build: {
    outDir: mode === "artifact" ? "dist-artifact" : "dist",
    emptyOutDir: true,
    // 資料以 import 靜態帶入,單檔模式下不能拆 chunk
    assetsInlineLimit: mode === "artifact" ? 100_000_000 : 4096,
    chunkSizeWarningLimit: 2000,
  },
}));
