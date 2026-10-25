#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大道至簡 · 每週生活熱點 × 社會創新 建置模組 (build_weekly.py)

1. 讀取 reports/06_weekly/raw/ 下的 37 份 Markdown 報告。
2. 透過 weekly_parser 解析雙語段落與熱點標題。
3. 產生獨立子頁 weekly/index.html（繁體版）與 zh-cn/weekly/index.html（簡體版）。
4. 提供 get_latest_weekly_summary() 供主頁 build.py 嵌入最新 3 期精選摘要。
"""

import json
import glob
import re
from pathlib import Path
import markdown
import weekly_parser as wp

try:
    from opencc import OpenCC
    CC = OpenCC("tw2sp")
    HAS_OPENCC = True
except ImportError:
    HAS_OPENCC = False

ROOT_DIR = Path(__file__).resolve().parent
WEEKLY_DIR = ROOT_DIR / "reports" / "06_weekly"
RAW_DIR = WEEKLY_DIR / "raw"
MANIFEST_PATH = WEEKLY_DIR / "manifest.json"
WEEKLY_TEMPLATE_PATH = ROOT_DIR / "weekly_template.html"

OUTPUT_DIR = ROOT_DIR / "weekly"
OUTPUT_PATH = OUTPUT_DIR / "index.html"
ZH_CN_OUTPUT_DIR = ROOT_DIR / "zh-cn" / "weekly"
ZH_CN_OUTPUT_PATH = ZH_CN_OUTPUT_DIR / "index.html"

BASE_URL = "https://alexchiachi.github.io/research-dashboard/weekly/"
MAIN_URL = "https://alexchiachi.github.io/research-dashboard/"


def load_manifest():
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text("utf-8"))
        except Exception:
            return {}
    return {}


def render_issue_doc_html(segs, issue_id):
    """將期數的多語言段落轉換為帶語言切換器的 HTML"""
    html_parts = []
    pair_idx = 0
    i = 0
    while i < len(segs):
        k, txt = segs[i]
        if k == "sep":
            html_parts.append('<hr class="sep" />')
            i += 1
        elif k == "neutral":
            rendered = markdown.markdown(txt, extensions=["tables", "fenced_code"])
            html_parts.append(f'<div class="wk-neutral">{rendered}</div>')
            i += 1
        elif k == "en":
            en_txt = txt
            zh_txt = ""
            if i + 1 < len(segs) and segs[i + 1][0] == "zh":
                zh_txt = segs[i + 1][1]
                i += 2
            else:
                i += 1
            pair_idx += 1
            en_html = markdown.markdown(en_txt, extensions=["tables", "fenced_code"])
            zh_html = markdown.markdown(zh_txt, extensions=["tables", "fenced_code"])

            block = f"""<div class="wk-pair" id="{issue_id}-hot-{pair_idx}">
  <div class="wk-lang-bar">
    <span class="wk-hot-num">熱點 0{pair_idx}</span>
    <div class="wk-lang-toggles" role="group" aria-label="語言切換">
      <button type="button" class="wk-btn-lang active" data-lang="zh">繁體中文</button>
      <button type="button" class="wk-btn-lang" data-lang="en">English</button>
    </div>
  </div>
  <div class="wk-body wk-zh-body">{zh_html}</div>
  <div class="wk-body wk-en-body" style="display:none;">{en_html}</div>
</div>"""
            html_parts.append(block)
        elif k == "zh":
            pair_idx += 1
            zh_html = markdown.markdown(txt, extensions=["tables", "fenced_code"])
            block = f'<div class="wk-pair"><div class="wk-body wk-zh-body">{zh_html}</div></div>'
            html_parts.append(block)
            i += 1
    return "\n".join(html_parts)


def get_latest_weekly_summary(count=3):
    """回傳最新 N 期的結構化摘要，供主頁 build.py 渲染 06 分類區塊"""
    manifest = load_manifest()
    raw_files = sorted(RAW_DIR.glob("*.md"), reverse=True)
    summaries = []
    for md_file in raw_files[:count]:
        date = md_file.stem
        raw_text = md_file.read_text("utf-8")
        segs = wp.segment(raw_text)
        titles = wp.extract_titles(segs, date=date)
        drive_url = manifest.get(date, {}).get("drive_url", "")
        summaries.append({
            "date": date,
            "titles": titles,
            "drive_url": drive_url,
            "anchor": f"w-{date}"
        })
    return summaries


def build_weekly():
    if not WEEKLY_TEMPLATE_PATH.exists():
        print(f"錯誤：找不到樣板檔案 {WEEKLY_TEMPLATE_PATH}")
        return

    manifest = load_manifest()
    template = WEEKLY_TEMPLATE_PATH.read_text("utf-8")

    raw_files = sorted(RAW_DIR.glob("*.md"), reverse=True)
    total_issues = len(raw_files)
    total_topics = total_issues * 3
    latest_date = raw_files[0].stem if raw_files else "2026-10-23"

    # 按月份統計
    months_count = {}
    issues_data = []

    for idx, md_file in enumerate(raw_files):
        date = md_file.stem
        month = date[:7]  # YYYY-MM
        months_count[month] = months_count.get(month, 0) + 1

        raw_text = md_file.read_text("utf-8")
        segs = wp.segment(raw_text)
        titles = wp.extract_titles(segs, date=date)
        drive_url = manifest.get(date, {}).get("drive_url", "")
        issue_id = f"w-{date}"

        # 估算中文字數
        zh_text = " ".join(txt for k, txt in segs if k in ("zh", "neutral"))
        cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", zh_text))
        reading_min = max(1, round(cjk_chars / 380))

        doc_html = render_issue_doc_html(segs, issue_id)

        # 最新一期預設展開，其他收合
        is_latest = (idx == 0)
        collapse_cls = "" if is_latest else " collapsed"

        issues_data.append({
            "id": issue_id,
            "date": date,
            "month": month,
            "titles": titles,
            "cjk_chars": f"{cjk_chars:,}",
            "reading_min": reading_min,
            "drive_url": drive_url,
            "collapse_cls": collapse_cls,
            "doc_html": doc_html
        })

    # 月份導覽列
    month_nav_lines = []
    month_names = {
        "2026-10": "10 月（最新）",
        "2026-09": "9 月",
        "2026-08": "8 月",
        "2026-07": "7 月",
        "2026-06": "6 月（起跑）"
    }
    for m in sorted(months_count.keys(), reverse=True):
        m_label = month_names.get(m, m)
        m_cnt = months_count[m]
        month_nav_lines.append(f'          <a href="javascript:void(0)" data-month="{m}">{m_label} ({m_cnt})</a>')
    month_nav_html = "\n".join(month_nav_lines)

    # 目錄 TOC
    toc_lines = []
    for item in issues_data:
        titles_summary = " · ".join(item["titles"])
        toc_lines.append(
            f'          <li><a href="#{item["id"]}"><span class="tdate">{item["date"]}</span><span class="ttitle">{titles_summary}</span></a></li>'
        )
    toc_html = "\n".join(toc_lines)

    # 期數卡片 HTML
    card_blocks = []
    for item in issues_data:
        titles_ol = "".join(f"<li><b>熱點 0{i+1}：</b>{t}</li>" for i, t in enumerate(item["titles"]))
        search_kw = f"{item['date']} " + " ".join(item["titles"])

        drive_foot = f'<p class="rfoot"><a class="drive-link" href="{item["drive_url"]}" target="_blank" rel="noopener">Google Docs 原檔 ↗</a></p>' if item["drive_url"] else ""

        card = f"""        <article class="issue-card{item['collapse_cls']}" id="{item['id']}" data-month="{item['month']}" data-search="{search_kw}">
          <header class="issue-head">
            <div class="issue-meta-row">
              <p class="imeta">
                <span class="idate">{item['date']}</span>
                <span class="istats">中文約 {item['cjk_chars']} 字 · 閱讀約 {item['reading_min']} 分鐘 · 附英文初稿</span>
              </p>
              <button type="button" class="cite-btn" data-id="{item['id']}" data-title="每週生活熱點 × 社會創新（{item['date']}）" data-date="{item['date']}" title="複製本期引用資訊與錨點連結">
                <span class="icon">🔗</span> 複製引用
              </button>
            </div>
            <h2 class="ititle">每週生活熱點 × 社會創新（{item['date']}）</h2>
            <div class="ipoint">
              <ol>
                {titles_ol}
              </ol>
            </div>
          </header>
          <div class="issue-doc">
{item['doc_html']}
          </div>
          {drive_foot}
        </article>"""
        card_blocks.append(card)

    issues_html = "\n\n".join(card_blocks)

    # 繁體版輸出
    output = template
    output = output.replace("{{CANONICAL_URL}}", BASE_URL)
    output = output.replace("{{HOME_URL}}", "../")
    output = output.replace("{{LANG_SWITCH}}", '<a class="lang-switch" href="../zh-cn/weekly/" hreflang="zh-Hans" lang="zh-Hans">简体</a>')
    output = output.replace("{{TOTAL_ISSUES}}", str(total_issues))
    output = output.replace("{{TOTAL_TOPICS}}", str(total_topics))
    output = output.replace("{{LATEST_DATE}}", latest_date)
    output = output.replace("{{MONTH_NAV_ITEMS}}", month_nav_html)
    output = output.replace("{{TOC_ITEMS}}", toc_html)
    output = output.replace("{{ISSUES_HTML}}", issues_html)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(output, encoding="utf-8")
    print(f"✓ 每週生活熱點繁體版建置完成：{OUTPUT_PATH.relative_to(ROOT_DIR)}（共 {total_issues} 期、{total_topics} 則熱點）")

    # 簡體版輸出
    if HAS_OPENCC:
        cn = output
        cn = cn.replace('<html lang="zh-Hant">', '<html lang="zh-Hans">')
        cn = cn.replace(f'<link rel="canonical" href="{BASE_URL}" />', f'<link rel="canonical" href="{BASE_URL.replace("weekly/", "zh-cn/weekly/")}" />')
        cn = cn.replace("Noto+Serif+TC", "Noto+Serif+SC")
        cn = cn.replace("Noto+Sans+TC", "Noto+Sans+SC")
        cn = cn.replace('"Noto Sans TC", "PingFang TC", "Microsoft JhengHei"', '"Noto Sans SC", "PingFang SC", "Microsoft YaHei"')
        cn = cn.replace('"Noto Serif TC", "Songti TC"', '"Noto Serif SC", "Songti SC"')
        cn = cn.replace("{{HOME_URL}}", "../../zh-cn/")
        cn = cn.replace(
            '<a class="lang-switch" href="../zh-cn/weekly/" hreflang="zh-Hans" lang="zh-Hans">简体</a>',
            '<a class="lang-switch" href="../../weekly/" hreflang="zh-Hant" lang="zh-Hant">繁体</a>'
        )
        cn = CC.convert(cn)

        ZH_CN_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ZH_CN_OUTPUT_PATH.write_text(cn, encoding="utf-8")
        print(f"✓ 每週生活熱點簡體版建置完成：{ZH_CN_OUTPUT_PATH.relative_to(ROOT_DIR)}（字型切換為 Noto SC，詞彙 tw2sp 在地化）")


if __name__ == "__main__":
    build_weekly()
