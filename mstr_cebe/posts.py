"""觀點:大事記(事件)與資本結構(主張)。

**這一層是詮釋,不是觀測。** 講義解公式、儀表板解數值,
只有這裡告訴你「這些數字該怎麼看」—— 所以每一則都要標日期與作者。

## 凍結的標日期,活的不要手寫

一篇文章引用的數字是**寫作當下的快照**,存在 `pins` 裡,永遠不改;
現況由資料層負責,永遠是今天。兩者都標 as-of,並排顯示。

這條規則取代了更早的「手寫文字不得包含數字」—— 那條太嚴,
會讓人根本沒辦法寫分析。真正的問題從來不是散文裡有數字,
而是那些數字**沒有標日期卻被當成現況在顯示**。

而且漂移可以反過來變成內容:**你能看到一個觀點寫下時的世界,
以及它後來變成什麼。** 這只有「資料會自己更新、文章不會」的系統做得到。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .md import md_to_html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS_DIR = os.path.join(ROOT, "posts")

# 兩種文體。結構與樣式一致,差別只有一個:**社論帶「主張」,新聞沒有** ——
# 因為主張可以被後續的資料檢驗,事件不行。
KINDS = {
    "chronicle": "大事記",      # 錨在一個時點或區間:發生了什麼、大概為什麼
    "structure": "機制解讀",    # 錨在一個主張:這家公司怎麼運作、對長期價值的影響
}


@dataclass(frozen=True)
class Pin:
    """寫作當下釘住的一個數字,外加它現在的值。"""
    key: str
    label: str
    then: float
    now: Optional[float] = None
    unit: str = ""


@dataclass(frozen=True)
class Post:
    slug: str
    title: str
    date: str
    author: str
    kind: str
    tags: List[str] = field(default_factory=list)
    claim: str = ""
    # 這一則對應到哪一個階段。有值時,前端會把管線算出來的骨架
    # (指標表、資金流、期間事件、圖表)掛在散文旁邊 ——
    # **散文不會過期是因為數字不在散文裡。**
    era: str = ""
    pins: List[Pin] = field(default_factory=list)
    charts: List[Dict] = field(default_factory=list)
    html: str = ""
    lede: str = ""


# ---------------------------------------------------------------------------
# pin 的解析:key → 它現在的值
# ---------------------------------------------------------------------------
#
# key 的形狀是 `<來源>:<參數>:<指標>`。解析器只認得列在這裡的 ——
# 認不出來就留 None(文章照樣顯示當時的值,只是沒有對照)。
# **不要讓文章自己寫 JSON path**,那會讓資料結構變成公開介面。

def _era_metric(data: dict, era_id: str, metric: str) -> Optional[float]:
    era = next((e for e in data["chronicle"] if e["id"] == era_id), None)
    if era is None:
        return None
    if metric in ("decision", "market"):
        return era["split"][metric]
    m = era["metrics"].get(metric)
    return m["pct"] if isinstance(m, dict) else None


def _now_metric(data: dict, field_: str) -> Optional[float]:
    d = data["daily"]
    return d[field_][-1] if field_ in d else None


def _program(data: dict, group: str, key: str):
    p = (data.get("meta") or {}).get("program")
    if not p:
        return None
    return {"split": p["split"], "layer": p["layers4"]}.get(group, {}).get(key)


RESOLVERS: Dict[str, Callable] = {
    "era": lambda data, a, b: _era_metric(data, a, b),
    "now": lambda data, a, _b: _now_metric(data, a),
    "program": lambda data, a, b: _program(data, a, b),
}


def resolve(key: str, data: dict) -> Optional[float]:
    parts = (key.split(":") + ["", ""])[:3]
    fn = RESOLVERS.get(parts[0])
    return fn(data, parts[1], parts[2]) if fn else None


# ---------------------------------------------------------------------------
# 讀檔
# ---------------------------------------------------------------------------

def parse_front_matter(src: str) -> tuple:
    """`---` 夾起來的 YAML 子集 + 本文。

    只支援 key: value、清單、以及 `- {a: b}` 這種行內物件 ——
    不引入 YAML 依賴,因為格式是我們自己定的,複雜就是自找麻煩。
    """
    if not src.startswith("---"):
        raise ValueError("缺少 front matter")
    _, fm, body = src.split("---", 2)
    meta: Dict = {}
    key = None
    for line in fm.strip().splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.startswith((" ", "\t", "-")) and key:
            item = line.lstrip(" \t-").strip()
            meta.setdefault(key, [])
            if isinstance(meta[key], list):
                meta[key].append(json.loads(item) if item.startswith("{") else item)
            continue
        k, _, v = line.partition(":")
        key, v = k.strip(), v.strip()
        if v.startswith("[") or v.startswith("{"):
            meta[key] = json.loads(v)
        elif v:
            meta[key] = v.strip('"')
        else:
            meta[key] = []
    return meta, body.strip()


def load_all(data: dict, path: str = POSTS_DIR) -> List[Post]:
    """讀 posts/*.md,解析 front matter,把 pin 的現值查出來。"""
    out: List[Post] = []
    if not os.path.isdir(path):
        return out
    for name in sorted(os.listdir(path)):
        if not name.endswith(".md"):
            continue
        slug = name[:-3]
        meta, body = parse_front_matter(
            open(os.path.join(path, name), encoding="utf-8").read())
        if meta.get("kind") not in KINDS:
            raise ValueError(f"{name}: kind 必須是 {sorted(KINDS)}")
        dt.date.fromisoformat(meta["date"])          # 格式錯就爆
        html_body, _ = md_to_html(body, slug)
        pins = [Pin(key=p["key"], label=p.get("label", p["key"]),
                    then=float(p["then"]), unit=p.get("unit", ""),
                    now=resolve(p["key"], data))
                for p in meta.get("pins", [])]
        lede = re.sub(r"<[^>]+>", "", html_body.split("</p>")[0])[:160]
        out.append(Post(
            slug=slug, title=meta["title"], date=meta["date"],
            author=meta.get("author", ""), kind=meta["kind"],
            tags=meta.get("tags", []), claim=meta.get("claim", ""),
            era=meta.get("era", ""),
            pins=pins, charts=meta.get("charts", []),
            html=html_body, lede=lede))
    return sorted(out, key=lambda p: (p.date, p.slug), reverse=True)


def to_json(posts: List[Post]) -> List[dict]:
    return [{
        "slug": p.slug, "title": p.title, "date": p.date, "author": p.author,
        "kind": p.kind, "tags": p.tags, "claim": p.claim, "era": p.era,
        "charts": p.charts, "html": p.html, "lede": p.lede,
        "pins": [{"key": x.key, "label": x.label, "then": x.then,
                  "now": x.now, "unit": x.unit} for x in p.pins],
    } for p in posts]
