import "./styles/tokens.css";
import "katex/dist/katex.min.css";
import "./styles/app.css";
import { startRouter, topRoutes, type Route } from "./router";

/** 有 parent 的是子分頁:不進主導覽,只在上層被選中時出現在第二排。
 *  「資本結構」底下分成「買了多少」與「誰排在誰前面」——
 *  同一個題目的兩半,但各自夠長,合成一頁會變成很難找東西的長捲軸。 */
const routes: Route[] = [
  { path: "/", title: "總覽", page: async () => (await import("./pages/overview")).overviewPage },
  { path: "/chronicle", title: "大事記", page: async () => (await import("./pages/chronicle")).chroniclePage },
  { path: "/structure", title: "資本結構", page: async () => (await import("./pages/structure")).structurePage },
  { path: "/structure/holdings", parent: "/structure", title: "持幣與融資", page: async () => (await import("./pages/accumulation")).accumulationPage },
  { path: "/structure/model", parent: "/structure", title: "誰排在誰前面", page: async () => (await import("./pages/structure")).structurePage },
  { path: "/operations", title: "資本操作", page: async () => (await import("./pages/operations")).operationsPage },
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
    <nav class="nav">${topRoutes(routes).map((r) =>
      `<a href="#${r.path}">${r.title}</a>`).join("")}</nav>
    <button class="theme-btn" id="theme" title="切換明暗主題">◐</button>
  </div></div>
  <div class="subnav" id="subnav" hidden></div>
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

// 子分頁列要黏在主導覽正下方。主導覽的高度會隨字級／換行變動,
// 所以量出來寫進 CSS 變數,不要在樣式表裡猜一個數字。
const topbar = document.querySelector<HTMLElement>(".topbar")!;
const syncTopbarHeight = () => {
  document.documentElement.style.setProperty(
    "--topbar-h", `${Math.round(topbar.getBoundingClientRect().height)}px`);
};
syncTopbarHeight();
addEventListener("resize", syncTopbarHeight);

startRouter(document.querySelector<HTMLElement>("#main")!, routes);
