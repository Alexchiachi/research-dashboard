
MANUAL_TITLES = {
    '2026-07-10': [
        'Waymo 無人計程車載客突破兩千萬次（行）',
        '社交健康俱樂部：澡堂與桑拿成新第三空間（住／樂）',
        '「熱狗之夏」爆紅流行與食物平權（食／樂）'
    ],
    '2026-07-31': [
        '「Tanmaxxing」助曬極限化爭議與防曬設計（樂・育）',
        '赤足鞋 Barefoot Shoes 走向主流（衣・行）',
        '日本草莓與零廢棄蛋糕：爆紅餐盤上的社會創新（食）'
    ],
    '2026-08-07': [
        "Buc-ee's 海狸玉米泡芙與世界盃球迷美食外交（食）",
        '日本頂級草莓爆紅與食物體系的社會創新（食）',
        '「主角式度假」趨勢與意義生產的社會創新（行／樂）'
    ]
}
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每週生活熱點 × 社會創新：Google Docs 匯出 Markdown 的解析器。

各期文件格式不一（【ENGLISH DRAFT】、### English Draft、[EN]、[繁中]……），
本模組以「語言標記行」切段：
  - en      英文初稿（網頁預設隱藏，可切換）
  - zh      繁體中文初稿
  - neutral 前言、熱點標題、來源連結等共用內容
並萃取每期三則熱點的中文標題作為摘要。
"""

import re

CN_NUM = "一二三四五六七八九十"

# --- 行分類用的正規式（以「去除 Markdown 符號後的純文字」比對）---
RE_EN_MARK = re.compile(r"^(english(\s*(draft|version|初稿|text))?|en\s*draft|英文(版|初稿))\b", re.I)
RE_EN_HEAD = re.compile(r"^\[\s*(EN|English)\s*\]\s*\S", re.I)              # [EN] Title...
RE_ZH_MARK = re.compile(r"^(繁體中文|中文初稿|中文版|繁中初稿|traditional\s*chinese)")
RE_ZH_HEAD = re.compile(r"^\[\s*(繁中|中文|繁體中文)\s*\]\s*\S")             # [繁中] 標題...
RE_EN_SECTION = re.compile(r"^introduction\.?$", re.I)              # 無標記文件的英文段落起點
RE_ZH_SECTION = re.compile(r"^引言[。．.：:]?$")                       # 無標記文件的中文段落起點
RE_HOTSPOT = re.compile(rf"^(熱點\s*[{CN_NUM}0-9]+|event\s*[0-9]+|hotspot\s*[0-9]+|topic\s*[0-9]+)", re.I)
RE_SOURCES = re.compile(r"^(來源(連結)?|參考(資料|來源)|sources?|source\s*links?|references?)\b", re.I)
RE_SEP = re.compile(r"^\s*(#+\s*)?\\?(-{3,}|─{5,}|━{5,}|={5,}|\*{3,}|_{3,})\s*$")


def plain(line):
    """去除 Markdown 標記，用於分類判斷"""
    s = line.strip()
    s = re.sub(r"^#+\s*", "", s)
    s = s.replace("\\[", "[").replace("\\]", "]")
    s = s.replace("**", "").replace("__", "")
    s = s.strip("*_ ").strip()
    s = s.replace("【", "[").replace("】", "]")
    s = re.sub(r"^[─━=\-\s]{3,}|[─━=\-\s]{3,}$", "", s).strip()
    # 外層括號：[English Draft] → English Draft
    m = re.fullmatch(r"\[([^\[\]]+)\]\s*", s)
    if m:
        s = m.group(1).strip()
    return s


def clean_md(text):
    """修正 Google Docs 匯出的跳脫字元與裸網址"""
    text = text.replace("\r\n", "\n")
    text = re.sub(r"\\([:=&~@/%?!|+\-])", r"\1", text)
    # 裸網址 → 自動連結（避開已在 ( [ < " 之後者）
    text = re.sub(r'(?<![\(\[<"=/])(https?://[^\s<>\)\]\*，。）」]+)', r"<\1>", text)
    return text


def classify(line):
    p = plain(line)
    if not p:
        return None
    if RE_SEP.match(line):
        return "sep"
    if len(p) <= 45 and RE_EN_MARK.match(p):
        return "en_mark"
    if len(p) <= 30 and RE_ZH_MARK.match(p):
        return "zh_mark"
    if RE_EN_HEAD.match(p):
        return "en_head"
    if RE_ZH_HEAD.match(p):
        return "zh_head"
    if RE_EN_SECTION.match(p):
        return "en_section"
    if RE_ZH_SECTION.match(p):
        return "zh_section"
    if RE_HOTSPOT.match(p):
        return "hotspot"
    if len(p) <= 40 and RE_SOURCES.match(p):
        return "sources"
    return None


def segment(raw):
    """回傳 [(kind, markdown_text), ...]，kind ∈ {neutral, en, zh, sep}"""
    text = clean_md(raw)
    lines = text.split("\n")

    # 去掉第一個文件標題行（網頁卡片已有標題）
    for i, ln in enumerate(lines[:6]):
        if "每週生活熱點" in ln and len(plain(ln)) < 80:
            lines[i] = ""
            break

    segs = []
    state = "neutral"
    buf = []

    def flush():
        if buf and any(b.strip() for b in buf):
            if segs and segs[-1][0] == state:
                segs[-1] = (state, segs[-1][1] + "\n" + "\n".join(buf))
            else:
                segs.append((state, "\n".join(buf)))
        buf.clear()

    for ln in lines:
        c = classify(ln)
        if c == "sep":
            flush()
            state = "neutral"
            if not segs or segs[-1][0] != "sep":
                segs.append(("sep", ""))
            continue
        if c in ("en_mark", "zh_mark"):
            flush()
            state = "en" if c == "en_mark" else "zh"
            continue  # 標記行本身不顯示（由切換鈕/標籤取代）
        if c in ("en_head", "zh_head"):
            flush()
            state = "en" if c == "en_head" else "zh"
            ln = re.sub(r"\\?\[\s*(EN|English|繁中|中文|繁體中文)\s*\\?\]\s*", "", ln, count=1, flags=re.I)
        elif c in ("en_section", "zh_section"):
            want = "en" if c == "en_section" else "zh"
            if state != want:
                flush()
                state = want
        elif c in ("hotspot", "sources"):
            flush()
            state = "neutral"
        buf.append(ln)
    flush()
    # 去掉開頭/結尾的分隔線
    while segs and segs[0][0] == "sep":
        segs.pop(0)
    while segs and segs[-1][0] == "sep":
        segs.pop()
    return segs


def _strip_title(s):
    s = plain(s).replace("\\", "")
    s = re.sub(rf"^熱點\s*[{CN_NUM}0-9]+\s*", "", s)
    s = re.sub(r"^[/／·・\s]*(event|hotspot|topic)\s*\d+\s*", "", s, flags=re.I)
    s = re.sub(r"^(標題|title)\s*[:：]\s*", "", s, flags=re.I)
    s = s.lstrip("：:｜|—–-·・/／　 ").strip()
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip("*_ ")


def _is_weak(t):
    """只有分類詞（如「（住 / Housing）」「FOOD (食)」）的標題視為不足"""
    core = re.sub(r"[（(][^）)]*[）)]", "", t)
    core = re.sub(r"[\s:：｜|—–\-/／·・&]+", "", core)
    return len(core) < 5 or core.isupper()


def _first_title_line(md):
    for ln in md.split("\n"):
        t = _strip_title(ln)
        if not t or len(t) <= 5:
            continue
        if len(t) <= 90 and not t.endswith(("。", ".", "：", ":")):
            return t
        return None
    return None


def extract_titles(segs, date="", limit=3):
    if date in MANUAL_TITLES:
        return MANUAL_TITLES[date][:limit]
    """萃取熱點標題：優先用「熱點一…」行，內容不足時改用中文段落標題"""
    hot, zh = [], []
    for kind, md in segs:
        if kind == "neutral":
            cands = [_strip_title(ln) for ln in md.split("\n") if classify(ln) == "hotspot"]
            cands = [c for c in cands if c]
            if cands:
                cjk = [c for c in cands if re.search(r"[\u4e00-\u9fff]{3,}", c)]
                hot.append((cjk or cands)[0])
        elif kind == "zh":
            t = _first_title_line(md)
            if t:
                zh.append(t)
    n = max(len(hot), len(zh))
    out = []
    for i in range(n):
        h = hot[i] if i < len(hot) else ""
        z = zh[i] if i < len(zh) else ""
        if h and not _is_weak(h) and re.search(r"[\u4e00-\u9fff]{3,}", h):
            out.append(h)
        elif z:
            out.append(z)
        elif h:
            out.append(h)
    seen, res = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            res.append(t)
    return res[:limit]


def extract_intro(segs):
    """第一段中性前言文字（作為摘要備援）"""
    for kind, md in segs:
        if kind == "neutral":
            for ln in md.split("\n"):
                p = plain(ln)
                if len(p) > 30 and classify(ln) is None:
                    return p
            break
    return ""
