#!/usr/bin/env python3
"""把 reference/*.md 編成單一檔案的 HTML。

    python3 reference/build.py

為什麼要有 HTML 版:markdown 讀起來是一條線,但這份文件的核心其實是
**一張拆解圖**(股價 → 幣 / 求償權 / 溢價)。那張圖用文字講很費力,
畫出來三秒就懂,而且它的數字每次資料更新都會變 —— 所以它是在這裡
從 app/data/*.json 現算現畫的,不是貼上去的靜態圖。

自成一檔:KaTeX 的 CSS/JS 與 woff2 字型全部 inline,離線可讀,
沒有任何外部請求。字型只留 woff2(見 app/vite.config.ts 的同款取捨)。

Markdown 只支援這份文件用得到的子集,刻意不裝 markdown 套件 ——
這個專案的 Python 端到目前為止零第三方相依,不想為了一份文件破例。
"""
from __future__ import annotations

import base64
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "reference")
DATA = os.path.join(ROOT, "app", "data")
KATEX = os.path.join(ROOT, "app", "node_modules", "katex", "dist")

ORDER = [
    ("00-purpose.md", "這個系統是拿來做什麼的"),
    ("01-model.md", "模型怎麼一步一步長出來"),
    ("02-operations.md", "每一種操作的代數"),
    ("03-data.md", "資料的血統、粒度與邊界"),
    ("04-decisions.md", "走過的彎路"),
    ("05-toolbox.md", "工具箱:代數怎麼變成可執行的宣告"),
    ("06-architecture.md", "四層架構規格"),
    ("07-data-gaps.md", "資料缺口清單"),
    ("08-status.md", "現況與施工紀錄"),
    ("09-site.md", "網站的設計:理論／觀測／詮釋"),
]


# --------------------------------------------------------------- 股價拆解圖

def price_breakdown() -> dict:
    """從前端實際拿到的那份資料,現算當下的股價拆解。"""
    with open(os.path.join(DATA, "daily.json"), encoding="utf-8") as f:
        d = json.load(f)
    i = len(d["date"]) - 1
    shares = d["shares"][i] * 1e6
    p = d["btc"][i]
    claims_usd = (d["debt"][i] + d["pref_total"][i] - d["cash"][i]) * 1e9
    gross_sats = d["held"][i] / shares * 1e8
    net_sats = d["common_btc"][i] / shares * 1e8

    layers = [("可轉債", d["debt"][i]), ("STRC", d["strc_lp"][i]),
              ("STRF", d["strf_lp"][i]), ("STRK", d["strk_lp"][i]),
              ("STRD", d["strd_lp"][i]), ("STRE", d["stre_lp"][i]),
              ("USD 流動性", -d["cash"][i])]
    return {
        "date": d["date"][i],
        "mstr": d["mstr"][i],
        "btc": p,
        "shares": shares,
        "mnav": d["mnav_cebe"][i],
        "gross": gross_sats / 1e8 * p,          # 每股帳面幣值
        "eaten": (gross_sats - net_sats) / 1e8 * p,
        "resid": net_sats / 1e8 * p,            # 每股殘值
        "claims_b": claims_usd / 1e9,
        "layers": [(name, v, v * 1e9 / shares) for name, v in layers],
    }


def breakdown_svg(b: dict) -> str:
    """瀑布圖:帳面幣值 → 扣求償權 → 殘值 → 乘溢價 → 股價。

    每一段的高度與金額成正比,所以「求償權吃掉多少」是用看的,不是用讀的。
    """
    W, H = 760, 300
    base, top = 250, 40                      # 基線與頂端
    scale = (base - top) / max(b["gross"], b["mstr"]) * 0.92

    def h(v: float) -> float:
        return v * scale

    cols = [
        ("每股帳面幣值", b["gross"], 0.0, "var(--btc)",
         f"{b['gross']:,.2f}"),
        ("求償權吃掉", -b["eaten"], b["resid"], "var(--bad)",
         f"−{b['eaten']:,.2f}"),
        ("每股殘值", b["resid"], 0.0, "var(--equity)",
         f"{b['resid']:,.2f}"),
        ("市場溢價", b["mstr"] - b["resid"], b["resid"], "var(--senti)",
         f"+{b['mstr'] - b['resid']:,.2f}"),
        ("股價", b["mstr"], 0.0, "var(--ink)", f"{b['mstr']:,.2f}"),
    ]
    bw, gap = 96, 44
    x0 = (W - (len(cols) * bw + (len(cols) - 1) * gap)) / 2

    parts = [f'<line x1="20" y1="{base}" x2="{W-20}" y2="{base}" '
             f'stroke="var(--line-2)" stroke-width="1"/>']
    for k, (label, val, floor, color, txt) in enumerate(cols):
        x = x0 + k * (bw + gap)
        height = abs(h(val))
        y = base - h(floor) - height
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw}" height="{height:.1f}" '
            f'rx="3" fill="{color}" opacity="{0.34 if val < 0 else 0.82}"/>')
        parts.append(
            f'<text x="{x + bw/2:.1f}" y="{y - 9:.1f}" text-anchor="middle" '
            f'class="amt">${txt}</text>')
        parts.append(
            f'<text x="{x + bw/2:.1f}" y="{base + 21:.1f}" text-anchor="middle" '
            f'class="cap">{html.escape(label)}</text>')
        # 連接線:讓「減掉」與「乘上」的動作看得出是接續的
        if k in (0, 2) and k + 1 < len(cols):
            nxt = x + bw + gap
            ly = base - h(cols[k + 1][2] + max(cols[k + 1][1], 0))
            parts.append(f'<line x1="{x + bw:.1f}" y1="{y:.1f}" x2="{nxt:.1f}" '
                         f'y2="{y:.1f}" stroke="var(--line-2)" '
                         f'stroke-dasharray="3,3"/>' if k == 0 else
                         f'<line x1="{x + bw:.1f}" y1="{y:.1f}" x2="{nxt:.1f}" '
                         f'y2="{ly:.1f}" stroke="var(--line-2)" '
                         f'stroke-dasharray="3,3"/>')
    parts.append(
        f'<text x="{W/2:.1f}" y="{base + 48:.1f}" text-anchor="middle" '
        f'class="cap">× mNAV {b["mnav"]:.3f}x　·　BTC ${b["btc"]:,.0f}'
        f'　·　{b["shares"]/1e6:.1f}M 股　·　{b["date"]}</text>')
    return (f'<svg viewBox="0 0 {W} {H}" role="img" '
            f'aria-label="MSTR 股價拆解瀑布圖">{"".join(parts)}</svg>')


# --------------------------------------------------------------- markdown

INLINE = [
    (re.compile(r"\*\*(.+?)\*\*", re.S), r"<b>\1</b>"),
    (re.compile(r"`([^`]+)`"), r"<code>\1</code>"),
    (re.compile(r"\[([^\]]+)\]\(([^)]+)\)"), r'<a href="\2">\1</a>'),
]


def inline(text: str) -> str:
    """行內標記。數學留給 KaTeX 的 auto-render 在瀏覽器裡處理,
    所以 $…$ 區段要先抽出來,免得底線被當成 markdown。"""
    stash: list[str] = []

    def keep(m: re.Match) -> str:
        stash.append(m.group(0))
        return f"\x00{len(stash)-1}\x00"

    # 先把跳脫過的錢字號收起來,否則下一行的數學正則會把 \$10…\$14 當成一段公式。
    # 還原時包一層 .nomath,讓瀏覽器端的 auto-render 跳過它(見 ignoredClasses)。
    def keep_dollar(_m: re.Match) -> str:
        stash.append('<span class="nomath">$</span>')
        return f"\x00{len(stash)-1}\x00"

    text = re.sub(r"\\\$", keep_dollar, text)
    text = re.sub(r"\$\$.+?\$\$|\$[^$\n]+\$", keep, text, flags=re.S)
    text = html.escape(text, quote=False)
    for pat, rep in INLINE:
        text = pat.sub(rep, text)
    # 連結是我們自己產生的,還原被跳脫的引號
    text = text.replace("&amp;", "&")
    return re.sub(r"\x00(\d+)\x00", lambda m: stash[int(m.group(1))], text)


def md_to_html(src: str, slug: str) -> tuple[str, list[tuple[str, str]]]:
    """只支援這份文件用得到的子集:h1-h3、段落、清單、表格、引言、程式碼塊、$$。"""
    out: list[str] = []
    toc: list[tuple[str, str]] = []
    lines = src.split("\n")
    i, n = 0, len(lines)

    while i < n:
        ln = lines[i]

        if ln.startswith("```"):
            body = []
            i += 1
            while i < n and not lines[i].startswith("```"):
                body.append(lines[i])
                i += 1
            i += 1
            out.append(f"<pre><code>{html.escape(chr(10).join(body))}</code></pre>")
            continue

        if ln.startswith("$$"):
            body = [ln]
            i += 1
            while i < n and not lines[i - 1].rstrip().endswith("$$"):
                body.append(lines[i])
                i += 1
            out.append(f'<div class="eq">{chr(10).join(body)}</div>')
            continue

        if ln.startswith("|") and i + 1 < n and set(lines[i + 1].replace("|", "").strip()) <= set("-: "):
            head = [c.strip() for c in ln.strip("|").split("|")]
            i += 2
            rows = []
            while i < n and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            th = "".join(f"<th>{inline(c)}</th>" for c in head)
            tb = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r)
                         + "</tr>" for r in rows)
            out.append(f"<table><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table>")
            continue

        m = re.match(r"^(#{1,3})\s+(.*)$", ln)
        if m:
            lvl, text = len(m.group(1)), m.group(2)
            anchor = f"{slug}-{len(toc)}"
            if lvl <= 2:
                toc.append((anchor, re.sub(r"[*`$]", "", text)))
            out.append(f'<h{lvl} id="{anchor}">{inline(text)}</h{lvl}>')
            i += 1
            continue

        if ln.startswith("> "):
            body = []
            while i < n and lines[i].startswith(">"):
                body.append(lines[i].lstrip("> ").rstrip())
                i += 1
            out.append(f'<blockquote>{inline(" ".join(body))}</blockquote>')
            continue

        if re.match(r"^\s*[-*]\s+", ln):
            items = []
            while i < n and re.match(r"^\s*[-*]\s+", lines[i]):
                item = [re.sub(r"^\s*[-*]\s+", "", lines[i])]
                i += 1
                while i < n and lines[i].startswith("  ") and lines[i].strip():
                    item.append(lines[i].strip())
                    i += 1
                items.append(" ".join(item))
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
            continue

        if ln.startswith("---") and set(ln.strip()) == {"-"}:
            out.append("<hr>")
            i += 1
            continue

        if not ln.strip():
            i += 1
            continue

        para = []
        while i < n and lines[i].strip() and not re.match(
                r"^(#{1,3}\s|\||>|```|\$\$|\s*[-*]\s|---+$)", lines[i]):
            para.append(lines[i].strip())
            i += 1
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")

    return "\n".join(out), toc


# --------------------------------------------------------------- 組裝

def read(path: str, binary: bool = False):
    mode = "rb" if binary else "r"
    kw = {} if binary else {"encoding": "utf-8"}
    with open(path, mode, **kw) as f:
        return f.read()


def katex_assets() -> tuple[str, str]:
    """把 KaTeX 的 CSS(字型 inline 成 data URI)與 JS 讀進來。"""
    if not os.path.isdir(KATEX):
        print("  ✗ 找不到 KaTeX,先在 app/ 跑 npm install", file=sys.stderr)
        sys.exit(1)
    css = read(os.path.join(KATEX, "katex.min.css"))
    # 只留 woff2:woff/ttf 是舊瀏覽器退路,佔了三倍體積卻到不了任何目標瀏覽器
    css = re.sub(r",url\([^)]*\.(?:woff|ttf)\)\s*format\([^)]*\)", "", css)

    def embed(m: re.Match) -> str:
        name = m.group(1)
        raw = read(os.path.join(KATEX, "fonts", name), binary=True)
        return f"url(data:font/woff2;base64,{base64.b64encode(raw).decode()})"

    css = re.sub(r"url\(fonts/([^)]+\.woff2)\)", embed, css)
    js = read(os.path.join(KATEX, "katex.min.js"))
    auto = read(os.path.join(KATEX, "contrib", "auto-render.min.js"))
    return css, js + "\n" + auto


def main() -> None:
    b = price_breakdown()
    sections, toc_all = [], []
    for fname, title in ORDER:
        slug = fname.split("-")[0]
        body, toc = md_to_html(read(os.path.join(HERE, fname)), slug)
        sections.append(f'<section id="sec-{slug}">{body}</section>')
        toc_all.append((slug, title, toc))

    nav = "".join(
        f'<div class="nav-group"><a class="nav-top" href="#sec-{slug}">'
        f'<span class="nav-n">{slug}</span>{html.escape(title)}</a>'
        + "".join(f'<a class="nav-sub" href="#{a}">{html.escape(t)}</a>'
                  for a, t in toc[1:])
        + "</div>"
        for slug, title, toc in toc_all)

    css, js = katex_assets()
    out = TEMPLATE.format(
        katex_css=css, katex_js=js, nav=nav,
        svg=breakdown_svg(b), date=b["date"],
        sections="\n".join(sections))
    path = os.path.join(HERE, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"  ✓ reference/index.html  {os.path.getsize(path)//1024} KB"
          f"  (資料至 {b['date']})")


TEMPLATE = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MSTR 資本結構 — 模型推導與決策紀錄</title>
<style>{katex_css}</style>
<style>
:root{{
  --paper:#fbfaf8; --surface:#fff; --surface-2:#f4f2ee; --ink:#16150f;
  --ink-2:#565247; --ink-3:#8a8478; --line:#e6e2da; --line-2:#cfc9bd;
  --btc:#c8811f; --equity:#1f7a5a; --senti:#6b57b5; --bad:#b4442e;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,monospace;
}}
@media(prefers-color-scheme:dark){{:root:not([data-theme="light"]){{
  --paper:#0d0f11; --surface:#14171a; --surface-2:#1b1f23; --ink:#e9e6df;
  --ink-2:#a8a296; --ink-3:#77726a; --line:#242a30; --line-2:#333b43;
  --btc:#e0a04a; --equity:#3fbf90; --senti:#9d8ae0; --bad:#e0705a;
}}}}
:root[data-theme="dark"]{{
  --paper:#0d0f11; --surface:#14171a; --surface-2:#1b1f23; --ink:#e9e6df;
  --ink-2:#a8a296; --ink-3:#77726a; --line:#242a30; --line-2:#333b43;
  --btc:#e0a04a; --equity:#3fbf90; --senti:#9d8ae0; --bad:#e0705a;
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--paper);color:var(--ink);
  font:15px/1.75 -apple-system,BlinkMacSystemFont,"Noto Sans TC",sans-serif;
  -webkit-font-smoothing:antialiased}}
.shell{{display:grid;grid-template-columns:250px minmax(0,1fr);
  max-width:1180px;margin:0 auto;gap:40px;padding:0 24px}}
nav{{position:sticky;top:0;align-self:start;max-height:100vh;overflow-y:auto;
  padding:28px 0 40px;border-right:1px solid var(--line)}}
.brand{{font-weight:700;font-size:.94rem;letter-spacing:-.01em;
  padding:0 14px 14px;border-bottom:1px solid var(--line);margin-bottom:12px}}
.brand span{{display:block;font-weight:400;font-size:.72rem;color:var(--ink-3);
  margin-top:4px;font-family:var(--mono)}}
.nav-group{{margin-bottom:9px}}
nav a{{display:block;text-decoration:none;color:var(--ink-2);padding:4px 14px;
  border-left:2px solid transparent;font-size:.83rem}}
nav a:hover{{color:var(--ink);background:var(--surface-2)}}
.nav-top{{font-weight:600;color:var(--ink);font-size:.87rem}}
.nav-n{{font-family:var(--mono);font-size:.68rem;color:var(--ink-3);
  margin-right:7px}}
.nav-sub{{font-size:.79rem;padding-left:35px}}
main{{padding:30px 0 100px;min-width:0}}
.hero{{border:1px solid var(--line);border-radius:6px;background:var(--surface);
  padding:24px 26px;margin-bottom:34px}}
.hero h1{{font-size:1.32rem;margin:0 0 4px;letter-spacing:-.015em}}
.hero p{{margin:0;color:var(--ink-2);font-size:.9rem}}
.hero svg{{width:100%;height:auto;margin-top:18px;display:block}}
.hero .amt{{font-family:var(--mono);font-size:12px;fill:var(--ink);font-weight:600}}
.hero .cap{{font-size:11px;fill:var(--ink-3)}}
section{{border-top:1px solid var(--line);padding-top:26px;margin-top:38px}}
section:first-of-type{{border-top:0;margin-top:0;padding-top:0}}
h1,h2,h3{{letter-spacing:-.012em;line-height:1.35}}
h1{{font-size:1.52rem;margin:0 0 18px}}
h2{{font-size:1.16rem;margin:38px 0 12px}}
h3{{font-size:.99rem;margin:26px 0 8px}}
p{{margin:0 0 14px;max-width:74ch}}
ul{{margin:0 0 14px;padding-left:22px;max-width:74ch}}
li{{margin-bottom:6px}}
a{{color:var(--equity)}}
code{{font-family:var(--mono);font-size:.86em;background:var(--surface-2);
  padding:1px 5px;border-radius:3px}}
pre{{background:var(--surface-2);border:1px solid var(--line);border-radius:5px;
  padding:14px 16px;overflow-x:auto;margin:0 0 16px}}
pre code{{background:0;padding:0;font-size:.82rem;line-height:1.65}}
blockquote{{margin:0 0 16px;padding:11px 16px;border-left:3px solid var(--btc);
  background:var(--surface-2);color:var(--ink-2);font-size:.9rem;
  border-radius:0 4px 4px 0}}
table{{border-collapse:collapse;width:100%;margin:0 0 18px;font-size:.87rem;
  display:block;overflow-x:auto}}
th{{text-align:left;font-size:.74rem;color:var(--ink-2);font-weight:600;
  border-bottom:1px solid var(--line-2);padding:8px 12px 7px;white-space:nowrap}}
td{{border-bottom:1px solid var(--line);padding:9px 12px;vertical-align:top}}
tbody tr:last-child td{{border-bottom:0}}
hr{{border:0;border-top:1px solid var(--line);margin:30px 0}}
.eq{{margin:0 0 18px;overflow-x:auto;overflow-y:hidden;padding:4px 0}}
.katex{{color:var(--ink)}}
.katex-display{{margin:.5em 0}}
.theme{{position:fixed;top:14px;right:18px;z-index:9;background:var(--surface);
  border:1px solid var(--line-2);color:var(--ink-2);border-radius:5px;
  padding:5px 11px;cursor:pointer;font-size:.8rem}}
@media(max-width:900px){{
  .shell{{grid-template-columns:1fr;gap:0;padding:0 18px}}
  nav{{position:static;max-height:none;border-right:0;
    border-bottom:1px solid var(--line);padding:18px 0}}
  .nav-sub{{display:none}}
}}
</style>
</head>
<body>
<button class="theme" id="theme">◐ 明暗</button>
<div class="shell">
<nav>
  <div class="brand">MSTR 資本結構<span>模型推導與決策紀錄</span></div>
  {nav}
</nav>
<main>
  <div class="hero">
    <h1>股價可以完全拆開</h1>
    <p>這是整個工具的核心輸出。數字由 <code>app/data/</code> 現算,資料至 {date}。</p>
    {svg}
  </div>
  {sections}
</main>
</div>
<script>{katex_js}</script>
<script>
document.addEventListener("DOMContentLoaded", function () {{
  renderMathInElement(document.body, {{
    delimiters: [
      {{left: "$$", right: "$$", display: true}},
      {{left: "$", right: "$", display: false}}
    ],
    ignoredClasses: ["nomath"],
    throwOnError: false
  }});
}});
var root = document.documentElement, KEY = "mstr-ref-theme";
try {{ if (localStorage.getItem(KEY)) root.setAttribute("data-theme", localStorage.getItem(KEY)); }} catch (e) {{}}
document.getElementById("theme").addEventListener("click", function () {{
  var cur = root.getAttribute("data-theme");
  var dark = matchMedia("(prefers-color-scheme: dark)").matches;
  var next = cur ? (cur === "dark" ? "light" : "dark") : (dark ? "light" : "dark");
  root.setAttribute("data-theme", next);
  try {{ localStorage.setItem(KEY, next); }} catch (e) {{}}
}});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
