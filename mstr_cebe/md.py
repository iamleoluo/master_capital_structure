"""Markdown → HTML 的最小子集。

**reference/ 的 .md 與 posts/ 的 .md 共用這一份** —— 兩邊的排版規則必須一樣,
否則同一段文字在講義與文章裡會長得不同。

只支援實際用得到的:h1–h3、段落、清單、表格、引言、程式碼塊、$$ 數學。
行內數學先抽出來再處理 markdown,否則底線會被當成強調。
"""
from __future__ import annotations

import html
import re


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
