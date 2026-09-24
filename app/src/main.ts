import "./styles/tokens.css";
import "katex/dist/katex.min.css";
import "./styles/app.css";
import { startRouter, type Route } from "./router";

const routes: Route[] = [
  { path: "/", title: "總覽", page: async () => (await import("./pages/overview")).overviewPage },
  { path: "/chronicle", title: "大事記", page: async () => (await import("./pages/chronicle")).chroniclePage },
  { path: "/accumulation", title: "持幣與融資", page: async () => (await import("./pages/accumulation")).accumulationPage },
  { path: "/structure", title: "資本結構", page: async () => (await import("./pages/structure")).structurePage },
  { path: "/strategy", title: "績效歸因", page: async () => (await import("./pages/strategy")).strategyPage },
  { path: "/pricing", title: "槓桿與定價", page: async () => (await import("./pages/pricing")).pricingPage },
  { path: "/data-quality", title: "資料品質", page: async () => (await import("./pages/dataQuality")).dataQualityPage },
];

const THEME_KEY = "mstr-theme";
function applyTheme(t: string | null): void {
  if (t) document.documentElement.setAttribute("data-theme", t);
  else document.documentElement.removeAttribute("data-theme");
}
applyTheme(localStorage.getItem(THEME_KEY));

const app = document.querySelector<HTMLElement>("#app")!;
app.innerHTML = `
  <div class="topbar"><div class="topbar-inner">
    <span class="brand">MSTR 資本結構</span>
    <nav class="nav">${routes.map((r) =>
      `<a href="#${r.path}">${r.title}</a>`).join("")}</nav>
    <button class="theme-btn" id="theme" title="切換明暗主題">◐</button>
  </div></div>
  <main id="main"></main>
  <footer><div class="wrap">
    <p>市場資料:BTC = Binance 日線;MSTR 與四檔優先股 = Yahoo 日線。
       BTC 持有量與逐週買賣、融資來源:SEC 8-K(兩種版型皆解析)。
       其餘資本結構:SEC XBRL 季頻 + 申報文件人工整理,錨點之間線性插值。</p>
    <p>恆等式的求償權採 cebetracker 定義(可轉債面額 + 優先股清算優先權 − 資產負債表現金),
       股數用 basic shares。定價頁的官方錨點另採公司定義(扣 USD Reserve、除以 FDSO),兩者刻意不混用。</p>
    <p style="margin:0">本頁為資料分析,不構成投資建議。</p>
  </div></footer>`;

document.querySelector<HTMLButtonElement>("#theme")!.addEventListener("click", () => {
  const cur = document.documentElement.getAttribute("data-theme");
  const prefersDark = matchMedia("(prefers-color-scheme: dark)").matches;
  const next = cur ? (cur === "dark" ? "light" : "dark") : (prefersDark ? "light" : "dark");
  applyTheme(next);
  localStorage.setItem(THEME_KEY, next);
});

startRouter(document.querySelector<HTMLElement>("#main")!, routes);
