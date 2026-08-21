/** 讓任何「畫進一個容器」的圖表都能放大。
 *
 * 用法:zoomable(host, "標題", (el, h) => drawXxx(el, h))
 * 內嵌版與放大版共用同一個 draw 函式,所以兩邊的座標與行為完全一致。
 */
export interface ZoomHandle { close(): void; destroy(): void; }

export function zoomable(
  host: HTMLElement,
  title: string,
  draw: (el: HTMLElement, h: number) => void,
  opts: { inlineHeight: number; zoomHeight: number } = { inlineHeight: 340, zoomHeight: 620 },
): ZoomHandle {
  draw(host, opts.inlineHeight);

  const head = host.closest(".chart-block")?.querySelector(".chart-tools");
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "icon-btn";
  btn.textContent = "⤢ 放大";
  (head ?? host.parentElement!).appendChild(btn);

  const backdrop = document.createElement("div");
  backdrop.className = "zoom-backdrop";
  backdrop.innerHTML = `
    <div class="zoom-panel" role="dialog" aria-modal="true">
      <div class="zoom-head"><h3></h3>
        <button type="button" class="zoom-close" aria-label="關閉">×</button></div>
      <div class="zoom-body"><div id="zc"></div></div>
    </div>`;
  backdrop.querySelector("h3")!.textContent = title;
  document.body.appendChild(backdrop);
  const zc = backdrop.querySelector<HTMLElement>("#zc")!;

  const open = () => {
    draw(zc, opts.zoomHeight);
    backdrop.classList.add("open");
    document.body.style.overflow = "hidden";
  };
  const close = () => {
    backdrop.classList.remove("open");
    document.body.style.overflow = "";
  };

  btn.addEventListener("click", open);
  backdrop.querySelector<HTMLButtonElement>(".zoom-close")!.addEventListener("click", close);
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop) close(); });
  const key = (e: KeyboardEvent) => {
    if (e.key === "Escape" && backdrop.classList.contains("open")) close();
  };
  document.addEventListener("keydown", key);

  return {
    close,
    destroy() {
      close();
      document.removeEventListener("keydown", key);
      backdrop.remove();
      btn.remove();
    },
  };
}
