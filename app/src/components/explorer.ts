/** 可拖曳的時間軸探索器 —— 總覽頁的主體。
 *  三張圖共用同一個游標,任何一張上拖曳都會同步其他圖與所有讀值。 */
import { daily, N } from "../data";
import { onIndexChange, setIndex, state } from "../state";
import { attachScrub, frame } from "../lib/frame";
import { bn, btc as fmtBtc, mult, sats, usd, usd0 } from "../lib/format";
import { RANGE_LABEL, rangeIndices, type RangeKey } from "../lib/range";
import {
  drawMnav, drawPrice, drawRiverUsd, mnavLabels, overlay, priceLabels, riverUsdLabels,
} from "../charts/timeseries";
import { drawRiverBtc, riverBtcLabels, type RiverBtcGeo } from "../charts/riverBtc";

const H = { price: 190, mnav: 190, riverUsd: 210, riverBtc: 240 } as const;
type ChartKey = keyof typeof H;

const LABEL: Record<ChartKey, string> = {
  price: "MSTR 與 BTC 價格(同基期指數化,對數軸)",
  mnav: "mNAV — basic(看不到優先股)vs CEBE(扣求償權後)",
  riverUsd: "美元計價:求償權堆疊 + MSTR 市值,虛線是 BTC 總市值",
  riverBtc: "BTC 計價:同樣的結構,但縱軸是「幣的顆數」",
};

/** 放大用的高度 —— 電腦螢幕上把圖拉高,波動才看得清楚。 */
const H_ZOOM: Record<ChartKey, number> = {
  price: 520, mnav: 520, riverUsd: 560, riverBtc: 600,
};

function staleBadge(d: number): { cls: string; txt: string } {
  if (d <= 15) return { cls: "live", txt: `真實觀測 ±${d} 天內` };
  if (d <= 90) return { cls: "near", txt: `中距離插值 ±${d} 天` };
  return { cls: "far", txt: `長距離插值 ±${d} 天` };
}

export interface ExplorerOpts {
  charts?: ChartKey[];
  showIdentity?: boolean;
}

export function explorer(root: HTMLElement, opts: ExplorerOpts = {}): () => void {
  const charts = opts.charts ?? (["price", "mnav", "riverUsd"] as ChartKey[]);
  const showIdentity = opts.showIdentity ?? true;

  root.innerHTML = `
    <div class="card flush">
      <div style="padding:20px 24px 0;display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap">
        <div>
          <div style="font-family:var(--serif);font-size:1.5rem;font-weight:600" id="ex-date">—</div>
          <div style="font-size:.8rem;color:var(--ink-3);margin-top:2px" id="ex-sub">—</div>
        </div>
        <div class="badge" id="ex-badge"><i class="dot"></i><span id="ex-badge-txt">—</span></div>
      </div>

      <div style="padding:16px 24px 0">
        <div class="reading-grid">
          <div class="reading"><div class="k">MSTR 股價</div><div class="v" id="r-mstr">—</div></div>
          <div class="reading"><div class="k">BTC 價格</div><div class="v" id="r-btc">—</div></div>
          <div class="reading"><div class="k">basic mNAV</div><div class="v" id="r-basic">—</div></div>
          <div class="reading"><div class="k">CEBE mNAV</div><div class="v accent" id="r-cebe">—</div></div>
          <div class="reading"><div class="k">求償權合計</div><div class="v" id="r-claims">—</div></div>
          <div class="reading"><div class="k">槓桿倍數</div><div class="v" id="r-amp">—</div></div>
        </div>
      </div>

      ${showIdentity ? `
      <div style="padding:16px 24px 0">
        <div class="card" style="padding:18px 20px">
          <div class="eq">
            <div class="eq-term result"><div class="eq-lab">MSTR 股價</div><div class="eq-val" id="id-price">—</div></div>
            <div class="eq-op">=</div>
            <div class="eq-term"><div class="eq-lab"><i class="swatch" style="background:var(--senti)"></i>情緒溢價</div>
              <div class="eq-val" id="id-mnav">—</div><div class="eq-sub">CEBE mNAV</div></div>
            <div class="eq-op">×</div>
            <div class="eq-term"><div class="eq-lab"><i class="swatch" style="background:var(--equity)"></i>每股 BTC</div>
              <div class="eq-val" id="id-bps">—</div><div class="eq-sub">sats／股</div></div>
            <div class="eq-op">×</div>
            <div class="eq-term"><div class="eq-lab"><i class="swatch" style="background:var(--btc)"></i>BTC 價格</div>
              <div class="eq-val" id="id-btc">—</div></div>
            <div class="eq-op">×</div>
            <div class="eq-term"><div class="eq-lab"><i class="swatch" style="background:var(--c3)"></i>普通股殘值率</div>
              <div class="eq-val" id="id-lev">—</div><div class="eq-sub">1 − 求償權佔比</div></div>
          </div>
        </div>
      </div>` : ""}

      <div style="padding:18px 24px 4px">
        ${charts.map((c) => `
          <div class="chart-block">
            <div class="chart-head">
              <div class="chart-label" id="label-${c}">${LABEL[c]}</div>
              <div class="chart-tools">
                ${c === "riverBtc" ? `<button type="button" class="icon-btn" data-pershare="${c}" aria-pressed="false">每股</button>` : ""}
                <button type="button" class="icon-btn" data-zoom="${c}">⤢ 放大</button>
              </div>
            </div>
            <div class="scrubbable" id="chart-${c}"></div>
          </div>`).join("")}
      </div>

      <div style="padding:4px 24px 18px">
        <input type="range" class="date-scrub" id="scrub" min="0" max="${N - 1}" value="${state.idx}" aria-label="選擇日期" />
      </div>

      <div style="padding:0 24px 18px;display:flex;justify-content:space-between;align-items:center;
                  gap:12px;flex-wrap:wrap;border-top:1px solid var(--line);padding-top:14px">
        <button type="button" class="btn" id="play">▶ 自動播放</button>
        <span style="font-size:.76rem;color:var(--ink-3)">拖曳任一張圖或下方滑桿;方向鍵 ← → 可逐日移動</span>
      </div>
    </div>`;

  const el = (id: string) => root.querySelector<HTMLElement>("#" + id)!;
  const detach: Array<() => void> = [];
  let gPrice: ReturnType<typeof drawPrice> | null = null;
  let gMnav: ReturnType<typeof drawMnav> | null = null;
  let gRiverUsd: ReturnType<typeof drawRiverUsd> | null = null;
  let gRiverBtc: RiverBtcGeo | null = null;
  let perShare = false;
  let zoomRange: RangeKey = "all";

  const padded = (c: ChartKey) => c === "riverUsd" || c === "riverBtc";

  /** 把某張圖畫進指定容器。放大燈箱與內嵌版共用這條路徑,
   *  所以兩邊的座標、標籤、游標行為完全一致。range 只在放大燈箱裡用,
   *  內嵌版永遠是全部範圍。 */
  function render(c: ChartKey, host: HTMLElement, h: number, range?: [number, number]): void {
    if (c === "price") gPrice = drawPrice(host, h, range);
    if (c === "mnav") gMnav = drawMnav(host, h, range);
    if (c === "riverUsd") gRiverUsd = drawRiverUsd(host, h, range);
    if (c === "riverBtc") gRiverBtc = drawRiverBtc(host, h, perShare, range);
  }

  for (const c of charts) {
    const host = el("chart-" + c);
    render(c, host, H[c]);
    detach.push(attachScrub(host, frame(H[c], padded(c) ? 18 : 16, padded(c) ? 26 : 24)));
  }

  const scrub = root.querySelector<HTMLInputElement>("#scrub")!;
  scrub.addEventListener("input", () => setIndex(+scrub.value));

  function paint(i: number): void {
    el("ex-date").textContent = daily.date[i]!;
    el("ex-sub").textContent =
      `BTC 持有 ${fmtBtc(daily.held[i]!)} 顆 · basic 股數 ${daily.shares[i]!.toFixed(1)}M`;
    const b = staleBadge(daily.stale[i]!);
    el("ex-badge").className = "badge " + b.cls;
    el("ex-badge-txt").textContent = b.txt;

    el("r-mstr").textContent = usd(daily.mstr[i]!);
    el("r-btc").textContent = usd0(daily.btc[i]!);
    el("r-basic").textContent = mult(daily.mnav_basic[i]!);
    el("r-cebe").textContent = mult(daily.mnav_cebe[i]!);
    el("r-claims").textContent = bn(daily.debt[i]! + daily.pref_total[i]!);
    el("r-amp").textContent = mult(daily.amp[i]);

    if (showIdentity) {
      el("id-price").textContent = usd(daily.mstr[i]!);
      el("id-mnav").textContent = mult(daily.mnav_cebe[i]!);
      el("id-bps").textContent = sats(daily.bps[i]!);
      el("id-btc").textContent = usd0(daily.btc[i]!);
      el("id-lev").textContent = (1 - daily.claims_pct[i]!).toFixed(3);
    }
    scrub.value = String(i);

    for (const c of charts) overlayFor(c, el("chart-" + c), H[c]);
    if (zoomed) {
      const host = document.getElementById("zoom-chart");
      if (host) overlayFor(zoomed, host, H_ZOOM[zoomed], rangeIndices(zoomRange));
    }
  }

  /** 依圖表種類把對應的標籤組畫上去。內嵌版與放大版共用。 */
  function overlayFor(c: ChartKey, host: HTMLElement, h: number, range?: [number, number]): void {
    const i = state.idx;
    const pT = padded(c) ? 18 : 16, pB = padded(c) ? 26 : 24;
    if (c === "price" && gPrice) overlay(host, priceLabels(gPrice, i), h, pT, pB, range);
    if (c === "mnav" && gMnav) overlay(host, mnavLabels(gMnav, i), h, pT, pB, range);
    if (c === "riverUsd" && gRiverUsd) overlay(host, riverUsdLabels(gRiverUsd, i), h, pT, pB, range);
    if (c === "riverBtc" && gRiverBtc) overlay(host, riverBtcLabels(gRiverBtc, i), h, pT, pB, range);
  }

  // ---- 每股切換(只有 BTC 河流圖有)----
  root.querySelectorAll<HTMLButtonElement>("[data-pershare]").forEach((btn) => {
    btn.addEventListener("click", () => {
      perShare = !perShare;
      btn.setAttribute("aria-pressed", String(perShare));
      const c = btn.dataset.pershare as ChartKey;
      el("label-" + c).textContent = perShare
        ? "每股計價:同樣的結構,但除以在外股數(sats／股)"
        : LABEL[c];
      render(c, el("chart-" + c), H[c]);
      if (zoomed === c) {
        const host = document.getElementById("zoom-chart");
        if (host) render(c, host, H_ZOOM[c], rangeIndices(zoomRange));
      }
      paint(state.idx);
    });
  });

  // ---- 放大燈箱 ----
  let zoomed: ChartKey | null = null;
  let zoomDetach: (() => void) | null = null;
  const backdrop = document.createElement("div");
  backdrop.className = "zoom-backdrop";
  backdrop.innerHTML = `
    <div class="zoom-panel" role="dialog" aria-modal="true" aria-labelledby="zoom-title">
      <div class="zoom-head">
        <h3 id="zoom-title"></h3>
        <button type="button" class="zoom-close" aria-label="關閉">×</button>
      </div>
      <div class="zoom-body">
        <div class="zoom-range" id="zoom-range-row">
          ${(Object.keys(RANGE_LABEL) as RangeKey[]).map((k) =>
            `<button type="button" class="range-btn${k === "all" ? " active" : ""}" data-range="${k}">${RANGE_LABEL[k]}</button>`
          ).join("")}
        </div>
        <div class="scrubbable" id="zoom-chart"></div>
        <input type="range" class="date-scrub" id="zoom-scrub" min="0" max="${N - 1}" style="margin-top:14px" aria-label="選擇日期" />
        <p style="font-size:.78rem;color:var(--ink-3);margin:8px 0 0">
          拖曳圖表或滑桿、方向鍵 ← → 都能換日期,與背景頁面同步。按 Esc 或點外面關閉。</p>
      </div>
    </div>`;
  document.body.appendChild(backdrop);
  const zoomScrub = backdrop.querySelector<HTMLInputElement>("#zoom-scrub")!;
  const zoomHost = backdrop.querySelector<HTMLElement>("#zoom-chart")!;
  const rangeRow = backdrop.querySelector<HTMLElement>("#zoom-range-row")!;

  /** 重畫放大圖(套用目前的 zoomRange),同步滑桿邊界與游標。 */
  function renderZoom(): void {
    if (!zoomed) return;
    const c = zoomed;
    const [lo, hi] = rangeIndices(zoomRange);
    render(c, zoomHost, H_ZOOM[c], [lo, hi]);
    zoomDetach?.();
    zoomDetach = attachScrub(zoomHost, frame(H_ZOOM[c], padded(c) ? 18 : 16, padded(c) ? 26 : 24, [lo, hi]));
    zoomScrub.min = String(lo);
    zoomScrub.max = String(hi);
    if (state.idx < lo || state.idx > hi) setIndex(Math.max(lo, Math.min(hi, state.idx)));
    else paint(state.idx);
  }

  function openZoom(c: ChartKey): void {
    zoomed = c;
    zoomRange = "all";
    rangeRow.querySelectorAll<HTMLButtonElement>("[data-range]").forEach((b) =>
      b.classList.toggle("active", b.dataset.range === "all"));
    backdrop.querySelector<HTMLElement>("#zoom-title")!.textContent =
      c === "riverBtc" && perShare
        ? "每股計價:同樣的結構,但除以在外股數(sats／股)" : LABEL[c];
    backdrop.classList.add("open");
    document.body.style.overflow = "hidden";
    renderZoom();
  }
  function closeZoom(): void {
    backdrop.classList.remove("open");
    document.body.style.overflow = "";
    zoomed = null;
    zoomDetach?.();
    zoomDetach = null;
    zoomScrub.min = "0";
    zoomScrub.max = String(N - 1);
    // 關閉後把內嵌版重畫回來(放大時 geo 被燈箱的高度覆寫過)
    for (const c of charts) render(c, el("chart-" + c), H[c]);
    paint(state.idx);
  }
  root.querySelectorAll<HTMLButtonElement>("[data-zoom]").forEach((btn) => {
    btn.addEventListener("click", () => openZoom(btn.dataset.zoom as ChartKey));
  });
  backdrop.querySelector<HTMLButtonElement>(".zoom-close")!
    .addEventListener("click", closeZoom);
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop) closeZoom(); });
  zoomScrub.addEventListener("input", () => setIndex(+zoomScrub.value));
  rangeRow.querySelectorAll<HTMLButtonElement>("[data-range]").forEach((btn) => {
    btn.addEventListener("click", () => {
      zoomRange = btn.dataset.range as RangeKey;
      rangeRow.querySelectorAll<HTMLButtonElement>("[data-range]").forEach((b) =>
        b.classList.toggle("active", b === btn));
      renderZoom();
    });
  });

  const off = onIndexChange((i) => { zoomScrub.value = String(i); paint(i); });
  paint(state.idx);

  let timer: number | null = null;
  const play = root.querySelector<HTMLButtonElement>("#play")!;
  play.addEventListener("click", () => {
    if (timer != null) {
      clearInterval(timer); timer = null; play.textContent = "▶ 自動播放"; return;
    }
    if (state.idx >= N - 1) setIndex(0);
    play.textContent = "⏸ 暫停";
    timer = window.setInterval(() => {
      if (state.idx >= N - 1) {
        clearInterval(timer!); timer = null; play.textContent = "▶ 自動播放"; return;
      }
      setIndex(state.idx + 2);
    }, 45);
  });

  const key = (e: KeyboardEvent) => {
    if (e.key === "Escape" && zoomed) { closeZoom(); return; }
    if (e.key === "ArrowLeft") { setIndex(state.idx - 1); e.preventDefault(); }
    if (e.key === "ArrowRight") { setIndex(state.idx + 1); e.preventDefault(); }
  };
  document.addEventListener("keydown", key);

  return () => {
    off();
    detach.forEach((fn) => fn());
    zoomDetach?.();
    document.removeEventListener("keydown", key);
    document.body.style.overflow = "";
    backdrop.remove();
    if (timer != null) clearInterval(timer);
  };
}
