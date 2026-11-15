import "./styles/tokens.css";
import "katex/dist/katex.min.css";
import "./styles/app.css";
import { startRouter, topRoutes } from "./router";
import { PAGES } from "./pages/registry";

const routes = PAGES;

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
    <button type="button" class="nav-toggle" id="nav-toggle" aria-expanded="false" aria-controls="nav">選單</button>
    <nav class="nav" id="nav">${topRoutes(routes).map((r) =>
      `<a href="#${r.path}">${r.title}</a>`).join("")}</nav>
    <button class="theme-btn" id="theme" title="切換明暗主題">◐</button>
  </div></div>
  <div class="subnav" id="subnav" hidden></div>
  <main id="main"></main>
  <footer><div class="wrap">
    <p>市場資料:BTC = Binance 日線;MSTR 與五檔優先股（STRF、STRC、STRK、STRD、STRE）= Yahoo 日線。
       STRE 沒有公開報價，表上留空。
       BTC 持有量與逐週買賣、融資來源:SEC 8-K(兩種版型皆解析)。
       其餘資本結構:SEC XBRL 季頻 + 申報文件。持幣只在揭露日跳動；其餘欄位在兩次申報之間依日數比例補上，停住時沿用上一筆。</p>
    <p>恆等式的求償權採 cebetracker 定義(可轉債面額 + 優先股清算優先權 − 資產負債表現金),
       股數用 basic shares。定價頁的官方錨點另採公司定義(扣 USD Reserve、除以 FDSO),兩者刻意不混用。</p>
    <p style="margin:0">本頁為資料分析,不構成投資建議。</p>
  </div></footer>`;

const nav = document.querySelector<HTMLElement>("#nav")!;
const navToggle = document.querySelector<HTMLButtonElement>("#nav-toggle")!;
navToggle.addEventListener("click", () => {
  const open = nav.classList.toggle("open");
  navToggle.setAttribute("aria-expanded", String(open));
});
nav.addEventListener("click", (ev) => {
  if ((ev.target as HTMLElement).closest("a")) {
    nav.classList.remove("open");
    navToggle.setAttribute("aria-expanded", "false");
  }
});

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
