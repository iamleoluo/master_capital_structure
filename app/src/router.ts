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

  const page = await route.page();
  const t = page(mount);
  teardown = typeof t === "function" ? t : null;
  window.scrollTo(0, 0);
}

export function startRouter(el: HTMLElement, defs: Route[]): void {
  mount = el;
  routes = defs;
  window.addEventListener("hashchange", () => void render());
  void render();
}
