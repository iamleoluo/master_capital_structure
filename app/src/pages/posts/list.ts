/** 觀點 —— 大事記與資本結構共用這一份清單。
 *
 *  兩者讀起來像新聞與社論,但那是比喻。結構上真正的差別只有一個:
 *  **資本結構那一類帶「主張」,大事記沒有** —— 因為主張可以被後續的
 *  資料檢驗,事件不行。 */
import { posts } from "../../data";
import { drawEraStrip } from "../../charts/eraStrip";
import type { Post } from "../../types";
import type { PageFn } from "../../router";

const KIND_LABEL = { chronicle: "大事記", structure: "資本結構" } as const;

const LEDE: Record<Post["kind"], string> = {
  chronicle: `某個時間點發生了什麼事,或一段期間裡發生了什麼、大概的原因。
    報導事件本身,不做太深的論述。`,
  structure: `公司營運與資本結構的<b>主張</b> ——
    這個動作對長期價值與本質有什麼影響、為什麼現在做、往後會產生什麼效益。
    需要論述、資料佐證與數據分析。`,
};

/** 空狀態要說清楚「什麼東西該放這裡」,否則讀者只會看到一個死胡同。 */
const EMPTY: Record<Post["kind"], string> = {
  chronicle: `<p class="note">還沒有大事記。</p>`,
  structure: `<div class="note key">
    <b>還沒有資本結構的論述。</b>
    這一類放的是對公司營運與資本結構的<b>主張</b> —— 例如:
    推出一個新券種對長期價值的影響是什麼、為什麼現在做這個資本操作、
    它往後對市場會產生什麼效益、最終目的是什麼。
    <br><br>
    與<a href="#/posts/chronicle">大事記</a>的差別不在深度,在<b>錨點</b>:
    大事記錨在一個事件,資本結構錨在一個<b>可以被後續資料檢驗的主張</b>。
    所以這一類多一個「主張」欄位 —— 寫下來之後,資料會自己去驗它。
  </div>`,
};

function card(p: Post): string {
  return `
    <a class="post-card" href="#/posts/${p.kind}/${p.slug}">
      <div class="post-meta">
        <time>${p.date}</time>
        ${p.author ? `<span class="post-author">${p.author}</span>` : ""}
        ${p.tags.map((t) => `<span class="post-tag">${t}</span>`).join("")}
      </div>
      <h3>${p.title}</h3>
      ${p.claim ? `<p class="post-claim">主張:${p.claim}</p>` : ""}
      <p class="post-lede">${p.lede}…</p>
    </a>`;
}

export function postList(kind: Post["kind"]): PageFn {
  return (root) => {
    const list = posts.filter((p) => p.kind === kind);
    root.innerHTML = `
      <div class="wrap">
        <div class="page-head">
          <p class="eyebrow">觀點 · ${KIND_LABEL[kind]}</p>
          <h1>${kind === "structure" ? "這些數字該怎麼看" : "發生了什麼"}</h1>
          <p class="lede">${LEDE[kind]}</p>
        </div>
        <div class="note" style="margin-bottom:26px">
          <b>這一層是詮釋,不是觀測。</b>
          公式在<a href="#/lecture">講義</a>、數字在<a href="#/board">儀表板</a>,
          只有這裡告訴你怎麼看 —— 所以每一則都標日期與作者。
          引用的數字是<b>寫作當下的快照</b>,旁邊會附上它現在的值。
        </div>
        ${kind === "chronicle"
          ? `<div id="era-strip" class="era-strip"
                 style="margin-bottom:22px"></div>` : ""}
        ${list.length ? list.map(card).join("") : EMPTY[kind]}
      </div>`;

    if (kind !== "chronicle") return;
    const strip = root.querySelector<HTMLElement>("#era-strip");
    if (!strip) return;
    drawEraStrip(strip);
    // 點色塊跳到那一段的那一則 —— 時間軸是導覽,不是裝飾
    const onClick = (ev: Event) => {
      const id = (ev.target as HTMLElement)?.getAttribute?.("data-era");
      const hit = id && posts.find((x) => x.era === id && x.kind === "chronicle");
      if (hit) location.hash = `/posts/chronicle/${hit.slug}`;
    };
    strip.addEventListener("click", onClick);
    return () => strip.removeEventListener("click", onClick);
  };
}

export const postsChroniclePage = postList("chronicle");
export const postsStructurePage = postList("structure");
