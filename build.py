#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大道至簡 · 研究報告儀表板建置腳本 (build.py)
讀取 reports/ 目錄下的 Markdown 報告，自動編譯為單頁純靜態 index.html。
"""

import os
import sys
import glob
import re
from pathlib import Path

try:
    import markdown
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False

ROOT_DIR = Path(__file__).resolve().parent
REPORTS_DIR = ROOT_DIR / "reports"
TEMPLATE_PATH = ROOT_DIR / "template.html"
OUTPUT_PATH = ROOT_DIR / "index.html"

CATEGORIES = [
    {
        "id": "cat-market",
        "dir": "01_market",
        "no": "01",
        "name": "市場調查",
        "folder": "https://drive.google.com/drive/folders/1TX-DgK-FvIUK3bMsOlHrwrIDJRsdNtL7",
        "empty_msg": "市場調查分類已建置完成，待新報告產出後直接歸檔於此處與 Google Drive 專屬資料夾。",
        "has_series": False
    },
    {
        "id": "cat-traffic",
        "dir": "02_traffic",
        "no": "02",
        "name": "流量情報",
        "folder": "https://drive.google.com/drive/folders/1u3FoolLkG7uCUekMXx9AC84Lj0W4Dk6e",
        "empty_msg": "流量情報分類已建置完成，待新報告產出後直接歸檔於此處與 Google Drive 專屬資料夾。",
        "has_series": True
    },
    {
        "id": "cat-people",
        "dir": "03_people",
        "no": "03",
        "name": "人物研究",
        "folder": "https://drive.google.com/drive/folders/10YmyOky6zqTUcPCdSyPw5r9zqFLtCuQ",
        "empty_msg": "人物研究分類已建置完成，待新報告產出後直接歸檔於此處與 Google Drive 專屬資料夾。",
        "has_series": False
    },
    {
        "id": "cat-events",
        "dir": "04_events",
        "no": "04",
        "name": "事件追蹤",
        "folder": "https://drive.google.com/drive/folders/1yt5RjbdupxjNlzVIaEJHKNv55kLk6Dhl",
        "empty_msg": "事件追蹤分類已建置完成，待新報告產出後直接歸檔於此處與 Google Drive 專屬資料夾。",
        "has_series": False
    },
    {
        "id": "cat-platform",
        "dir": "05_platform",
        "no": "05",
        "name": "平台研究",
        "folder": "https://drive.google.com/drive/folders/1Xijg_Hx4V3gXeG79dRs8A3SEDe64LS6p",
        "empty_msg": "平台研究分類已建置完成，待新報告產出後直接歸檔於此處與 Google Drive 專屬資料夾。",
        "has_series": False
    }
]

SERIES_CARD_TRAFFIC = """<div class="report series" id="r-daily-top10" data-search-block data-search="每日 社群 流量 top10 台灣 中國 日本 韓國 美國 事件">
        <header class="report-head">
          <p class="rmeta"><span class="daily">每日更新</span></p>
          <h3 class="rtitle plain">每日社群流量 Top10</h3>
          <p class="rpoint">台、中、日、韓、美五地各 10 則，每日更新，原始檔存在專屬資料夾。互動版是 Muse 裡的<em>「流量情報儀表板」</em>，每日自動同步。</p>
        </header>
        <p class="rfoot"><a class="drive-link" href="https://drive.google.com/drive/folders/1jDiEBED8qTob14wdkSSonkMP1378cHdq" target="_blank" rel="noopener">開啟資料夾 ↗</a></p>
      </div>"""

def parse_frontmatter(content):
    """解析 YAML Frontmatter 與內文"""
    meta = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1]
            body = parts[2].strip()
            for line in fm_text.strip().splitlines():
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    meta[key] = val
    return meta, body

def render_content(body):
    """將 Markdown / HTML 內文轉為安全 HTML"""
    if not body:
        return ""
    lines = body.splitlines()
    clean_lines = []
    in_code = False
    for line in lines:
        s = line.strip()
        if s.startswith("```"):
            in_code = not in_code
            clean_lines.append(line)
        elif in_code:
            clean_lines.append(line)
        elif s.startswith("<"):
            clean_lines.append(s)
        elif line.startswith("    ") and not s.startswith(("-", "*", "1", "2", "3", "4", "5", "6", "7", "8", "9")):
            clean_lines.append(s)
        else:
            clean_lines.append(line)
    clean_body = "\n".join(clean_lines).strip()
    if HAS_MARKDOWN:
        return markdown.markdown(clean_body, extensions=['tables', 'fenced_code'])
    return clean_body

def clean_title_for_menu(title):
    """去除標題末尾的（2026-10-22）等贅字，保持目錄精煉"""
    return re.sub(r'（\d{4}-\d{2}-\d{2}）$', '', title).strip()

def build():
    if not TEMPLATE_PATH.exists():
        print(f"錯誤：找不到樣板檔案 {TEMPLATE_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    categories_reports = {}
    all_reports = []

    # 1. 讀取與分類所有報告
    for cat in CATEGORIES:
        cat_dir = REPORTS_DIR / cat["dir"]
        cat_reports = []
        if cat_dir.exists():
            for md_file in sorted(cat_dir.glob("*.md")):
                with open(md_file, "r", encoding="utf-8") as f:
                    raw = f.read()
                meta, body = parse_frontmatter(raw)
                report_id = meta.get("id") or ("r-" + md_file.stem)
                title = meta.get("title", md_file.stem)
                date = meta.get("date", "2026-10-22")
                tag = meta.get("tag", "")
                point = meta.get("point", "")
                drive_url = meta.get("drive_url", "")
                search = meta.get("search", title)
                
                rep = {
                    "id": report_id,
                    "title": title,
                    "clean_title": clean_title_for_menu(title),
                    "date": date,
                    "tag": tag,
                    "point": point,
                    "drive_url": drive_url,
                    "search": search,
                    "body_html": render_content(body),
                    "cat_id": cat["id"],
                    "cat_name": cat["name"],
                    "cat_no": cat["no"]
                }
                cat_reports.append(rep)
                all_reports.append(rep)

        # 分類內按日期降序排列
        cat_reports.sort(key=lambda r: r["date"], reverse=True)
        categories_reports[cat["id"]] = cat_reports

    # 2. 全局報告排序（用於目錄與統計）
    all_reports.sort(key=lambda r: r["date"], reverse=True)

    total_count = len(all_reports)
    latest_date = all_reports[0]["date"] if all_reports else "2026-10-22"

    empty_cats = [c["name"] for c in CATEGORIES if len(categories_reports[c["id"]]) == 0]
    pending_count = len(empty_cats)
    pending_names = "、".join(empty_cats) if empty_cats else "無"

    # 3. 建立頂欄下拉選單 (TOPBAR_DROPDOWN)
    topbar_dd_lines = []
    for cat in CATEGORIES:
        topbar_dd_lines.append(f'            <a class="d-cat" href="#{cat["id"]}"><b>{cat["no"]}</b>{cat["name"]}</a>')
        if cat.get("has_series"):
            topbar_dd_lines.append('            <a role="menuitem" href="#r-daily-top10"><span class="d-date">每日更新</span><span>每日社群流量 Top10</span></a>')
        reps = categories_reports[cat["id"]]
        if reps:
            for r in reps:
                topbar_dd_lines.append(f'            <a role="menuitem" href="#{r["id"]}"><span class="d-date">{r["date"]}</span><span>{r["clean_title"]}</span></a>')
        elif not cat.get("has_series"):
            topbar_dd_lines.append('            <span class="d-note">尚無歸檔報告，待累積</span>')
    topbar_dropdown_html = "\n".join(topbar_dd_lines)

    # 4. 建立目錄 (TOC_ITEMS)
    toc_lines = []
    for r in all_reports:
        toc_lines.append(f'          <li><a href="#{r["id"]}"><span class="tdate">{r["date"]}</span><span class="ttitle">{r["clean_title"]}</span><span class="tcat">{r["cat_name"]}</span></a></li>')
    toc_items_html = "\n".join(toc_lines)

    # 5. 建立五大分類區塊 (CATEGORIES_HTML)
    cat_blocks = []
    for cat in CATEGORIES:
        reps = categories_reports[cat["id"]]
        # 分類內部下拉選單
        cat_dd_lines = []
        if cat.get("has_series"):
            cat_dd_lines.append('              <a role="menuitem" href="#r-daily-top10"><span class="d-date">每日更新</span><span>每日社群流量 Top10</span></a>')
        if reps:
            for r in reps:
                cat_dd_lines.append(f'              <a role="menuitem" href="#{r["id"]}"><span class="d-date">{r["date"]}</span><span>{r["clean_title"]}</span></a>')
        elif not cat.get("has_series"):
            cat_dd_lines.append('              <span class="d-note">尚無歸檔報告，待累積</span>')
        cat_dd_html = "\n".join(cat_dd_lines)

        # 報告卡片
        report_cards = []
        if cat.get("has_series"):
            report_cards.append(SERIES_CARD_TRAFFIC)

        if reps:
            for r in reps:
                tag_html = f'<span class="tag">{r["tag"]}</span>' if r["tag"] else ""
                rfoot_html = f'<p class="rfoot"><a class="drive-link" href="{r["drive_url"]}" target="_blank" rel="noopener">雲端原檔 ↗</a></p>' if r["drive_url"] else ""
                card = f"""        <article class="report" id="{r["id"]}" data-search-block data-search="{r["search"]}">
          <header class="report-head">
            <p class="rmeta">{r["date"]}{tag_html}</p>
            <h3 class="rtitle">{r["title"]}</h3>
            <p class="rpoint">{r["point"]}</p>
          </header>
          <div class="doc">
{r["body_html"]}
          </div>
          {rfoot_html}
        </article>"""
                report_cards.append(card)
        elif not cat.get("has_series"):
            empty_block = f"""        <div class="empty">
          <span class="big">尚無歸檔報告</span>
          <p style="margin:0;">{cat["empty_msg"]}</p>
        </div>"""
            report_cards.append(empty_block)

        cat_body = "\n".join(report_cards)

        cat_html = f"""      <!-- {cat["no"]} {cat["name"]} -->
      <section class="cat" id="{cat["id"]}">
        <div class="cat-head">
          <span class="no">{cat["no"]}</span>
          <h2>{cat["name"]}</h2>
          <div class="dd">
            <button class="dd-btn" type="button" aria-haspopup="true" aria-expanded="false">本分類文章<span class="car" aria-hidden="true">▾</span></button>
            <div class="dd-panel" role="menu" aria-label="{cat["name"]}文章選單">
{cat_dd_html}
            </div>
          </div>
          <a class="folder" href="{cat["folder"]}" target="_blank" rel="noopener">開啟資料夾 →</a>
        </div>
{cat_body}
      </section>"""
        cat_blocks.append(cat_html)

    categories_html = "\n\n".join(cat_blocks)

    # 6. 替換樣板變數並輸出
    output = template
    output = output.replace("{{TOPBAR_DROPDOWN}}", topbar_dropdown_html)
    output = output.replace("{{TOTAL_REPORTS}}", str(total_count))
    output = output.replace("{{LATEST_DATE}}", latest_date)
    output = output.replace("{{PENDING_CATS_COUNT}}", str(pending_count))
    output = output.replace("{{PENDING_CATS_NAMES}}", pending_names)
    output = output.replace("{{TOC_ITEMS}}", toc_items_html)
    output = output.replace("{{CATEGORIES_HTML}}", categories_html)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"✓ 編譯成功！已匯總 {total_count} 份報告至 {OUTPUT_PATH.name}（最新日期：{latest_date}）")

if __name__ == "__main__":
    build()
