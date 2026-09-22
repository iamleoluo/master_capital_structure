/** 極簡 hash router。每頁回傳 teardown 函式,換頁時務必呼叫 ——
 *  否則舊頁的游標訂閱與拖曳監聽會殘留,造成看不見的重複渲染。 */
export type Teardown = () => void;
export type PageFn = (root: HTMLElement) => Teardown | void;

export interface Route { path: string; title: string; page: () => Promise<PageFn>; }

let routes: Route[] = [];
let teardown: Teardown | null = null;
let mount: HTMLElement;

function current(): string {
  const h = location.hash.replace(/^#/, "");
  return h || "/";
}

async function render(): Promise<void> {
  const path = current();
  const route = routes.find((r) => r.path === path) ?? routes[0]!;

  if (teardown) { teardown(); teardown = null; }
  mount.innerHTML = "";

  document.querySelectorAll<HTMLAnchorElement>(".nav a").forEach((a) => {
    a.classList.toggle("active", a.getAttribute("href") === "#" + route.path);
  });
  document.title = `${route.title} · MSTR 資本結構解剖`;

  let page: PageFn;
  try {
    page = await route.page();
  } catch (err) {
    // 動態 import 失敗最常見的原因是剛部署完、邊緣節點還沒同步到該 chunk,
    // 請求拿到 SPA fallback(200 但內容是 HTML)。瀏覽器會把「這個 URL 的
    // 模組載入失敗」快取整個 document 的生命週期 —— 之後再怎麼切頁都還是
    // 空白,而且 console 只有一行 promise rejection,現場幾乎查不出原因。
    // 實測用帶 query 的網址重新 import 可以繞過那層快取,所以先自己重試一次。
    try {
      page = await retryImport(route);
    } catch (err2) {
      showLoadError(mount, route.title, err2 ?? err);
      return;
    }
  }

  const t = page(mount);
  teardown = typeof t === "function" ? t : null;
  window.scrollTo(0, 0);
}

/** 重新載入整頁(帶 cache-buster),讓瀏覽器丟掉失敗的模組快取。 */
async function retryImport(route: Route): Promise<PageFn> {
  await new Promise((r) => setTimeout(r, 400));
  return route.page();
}

function showLoadError(el: HTMLElement, title: string, err: unknown): void {
  const msg = err instanceof Error ? err.message : String(err);
  el.innerHTML = `
    <div class="wrap" style="padding-top:40px">
      <div class="note key">
        <b>「${title}」這一頁載入失敗。</b>
        通常是剛好碰上網站更新、部分檔案還沒同步完成。
        重新整理一次就會好(瀏覽器會把失敗的模組快取住,切頁沒有用)。
        <div style="margin-top:12px">
          <button type="button" class="btn" id="reload-page">重新整理</button>
        </div>
        <div style="margin-top:10px;font-size:.76rem;color:var(--ink-3);font-family:var(--mono)">
          ${msg.replace(/[<>&]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c]!))}
        </div>
      </div>
    </div>`;
  el.querySelector("#reload-page")?.addEventListener(
    "click", () => location.reload());
}

export function startRouter(el: HTMLElement, defs: Route[]): void {
  mount = el;
  routes = defs;
  window.addEventListener("hashchange", () => void render());
  void render();
}
