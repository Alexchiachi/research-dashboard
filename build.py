
def render_weekly_series_card():
    summaries = build_weekly.get_latest_weekly_summary(count=3)
    items_html = []
    for s in summaries:
        pts = "".join(f"<li>{t}</li>" for t in s["titles"])
        items_html.append(f"""          <div class="wk-digest-item" style="border: 1px solid var(--line); background: var(--surface); padding: 18px 20px; margin-top: 14px;">
            <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px;">
              <span style="font-family: monospace; font-size: 13px; font-weight: 600; color: var(--terra);">{s["date"]}</span>
              <a href="weekly/#{s["anchor"]}" style="font-size: 12.5px; color: var(--tea);">閱讀本期全文 ↗</a>
            </div>
            <h4 style="font-family: 'Noto Serif TC', serif; font-size: 17px; margin: 4px 0 8px; color: var(--ink);">每週生活熱點 × 社會創新（{s["date"]}）</h4>
            <ol style="margin: 0; padding-left: 1.4em; font-size: 14.5px; color: var(--muted); line-height: 1.7;">
              {pts}
            </ol>
          </div>""")
    digest_cards = "\n".join(items_html)
    return f"""        <div class="report series" id="r-weekly-hub" data-search-block data-search="生活 熱點 社會創新 食 衣 住 行 育 樂 雙語">
          <header class="report-head">
            <p class="rmeta"><span class="daily">每週兩期 · 持續累積 37 期</span></p>
            <h3 class="rtitle plain">每週生活熱點 × 社會創新</h3>
            <p class="rpoint">從食、衣、住、行、育、樂等日常切角，拆解現象背後的<em>規則重組、關係轉向與社會創新</em>。每期收錄 3 則生活熱點之中文深度解析與英文版（English Draft）。</p>
          </header>
          <div class="doc" style="margin-top: 16px;">
            <p style="font-size: 15px; color: var(--muted); margin-bottom: 8px;">以下為<strong>最新出刊 3 期摘要</strong>；完整 37 期已建立專屬獨立閱讀頁面：</p>
{digest_cards}
          </div>
          <p class="rfoot" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-top: 24px;">
            <span style="font-size: 13px; color: var(--muted);">累積 37 期全歸檔（2026-06 至 2026-10）</span>
            <a class="drive-link" href="weekly/" style="background: var(--tint); color: var(--ink); border: 1px solid var(--tea); padding: 6px 16px; font-weight: 500;">前往「每週熱點全歸檔獨立頁」閱讀完整 37 期 ➔</a>
          </p>
        </div>"""
import build_weekly
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大道至簡 · 研究報告儀表板建置腳本 (build.py)
參考 happy 倉庫標準：
1. 讀取 reports/ 目錄下的 Markdown 報告，自動編譯繁體版 index.html。
2. 透過 OpenCC (tw2sp) 自動產生對應的簡體版 zh-cn/index.html（字型、hreflang、用語在地化轉換）。
3. 自動產出 sitemap.xml 與 robots.txt。
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

try:
    from opencc import OpenCC
    CC = OpenCC("tw2sp")
    HAS_OPENCC = True
except ImportError:
    HAS_OPENCC = False
    print("警告：未安裝 opencc-python-reimplemented，將略過簡體版生成。可執行 pip install opencc-python-reimplemented 安裝。")

ROOT_DIR = Path(__file__).resolve().parent
REPORTS_DIR = ROOT_DIR / "reports"
TEMPLATE_PATH = ROOT_DIR / "template.html"
OUTPUT_PATH = ROOT_DIR / "index.html"
ZH_CN_DIR = ROOT_DIR / "zh-cn"
ZH_CN_OUTPUT_PATH = ZH_CN_DIR / "index.html"

BASE_URL = "https://alexchiachi.github.io/research-dashboard/"

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
    },
    {
        "id": "cat-weekly",
        "dir": "06_weekly",
        "no": "06",
        "name": "生活熱點 × 社會創新",
        "folder": "weekly/",
        "empty_msg": "每週生活熱點 × 社會創新系列持續追蹤中。",
        "has_series": False,
        "is_weekly": True
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
        html = markdown.markdown(clean_body, extensions=['tables', 'fenced_code'])
    else:
        html = clean_body

    def wrap_table_match(m):
        prefix = m.group(1) or ""
        table = m.group(2)
        if prefix:
            return prefix + table
        return f'<div class="tablewrap">{table}</div>'

    html = re.sub(r'(<div class="tablewrap">[\s\n]*)?(<table\b[^>]*>.*?</table>)', wrap_table_match, html, flags=re.DOTALL)
    return html

def clean_title_for_menu(title):
    """去除標題末尾的（2026-10-22）等贅字，保持目錄精煉"""
    return re.sub(r'（\d{4}-\d{2}-\d{2}）$', '', title).strip()

def calc_reading_stats(body_text):
    """計算報告字數與預估閱讀時間（以中文 380 字/分、英文 180 詞/分為標準）"""
    clean_text = re.sub(r'<[^>]+>', '', body_text)
    cjk_chars = len(re.findall(r'[\u4e00-\u9fff]', clean_text))
    en_words = len(re.findall(r'[a-zA-Z0-9]+', clean_text))
    total_words = cjk_chars + en_words
    minutes = max(1, round(cjk_chars / 380 + en_words / 180))
    return total_words, f"{total_words:,}", minutes

def inject_mini_toc(report_id, html):
    """為具備 3 個以上章節的報告自動建立篇內極簡目錄 (Mini-TOC)"""
    # 1. 標準化特定自訂標題
    html = re.sub(r'<div style="font-size:16px;color:#82663F;margin-bottom:8px;">(.*?)</div>', r'<h2>\1</h2>', html)
    
    # 2. 探測 h2 與 h3 數量
    all_h2 = re.findall(r'<h2\b[^>]*>(.*?)</h2>', html, flags=re.DOTALL)
    all_h3 = re.findall(r'<h3\b[^>]*>(.*?)</h3>', html, flags=re.DOTALL)
    
    # 決定抓取的標籤深度：總數 <= 15 則包含 h2 + h3，否則僅保留 h2
    include_h3 = (len(all_h2) + len(all_h3) <= 15) and len(all_h3) > 0
    target_pattern = r'<(h[23])(\b[^>]*)>(.*?)</\1>' if include_h3 else r'<(h2)(\b[^>]*)>(.*?)</\1>'
    
    headings = []
    def heading_repl(m):
        tag = m.group(1)
        attrs = m.group(2) or ""
        title = m.group(3).strip()
        clean_title = re.sub(r'<[^>]+>', '', title).strip()
        if not clean_title or len(clean_title) > 60:
            return m.group(0)
            
        id_match = re.search(r'id=["\']([^"\']+)["\']', attrs)
        if id_match:
            h_id = id_match.group(1)
        else:
            idx = len(headings) + 1
            h_id = f"{report_id}-sec-{idx}"
            attrs = f' id="{h_id}"' + attrs
            
        headings.append((tag, h_id, clean_title))
        return f'<{tag}{attrs}>{title}</{tag}>'

    new_html = re.sub(target_pattern, heading_repl, html, flags=re.DOTALL)
    
    if len(headings) >= 3:
        toc_items = []
        for tag, hid, htitle in headings:
            cls = ' class="sub"' if tag == 'h3' else ''
            toc_items.append(f'            <li{cls}><a href="#{hid}">{htitle}</a></li>')
        toc_html = "\n".join(toc_items)
        mini_toc = f"""        <details class="mini-toc">
          <summary class="mini-toc-summary"><span class="mini-toc-title">篇內章節導覽</span><span class="mini-toc-count">（共 {len(headings)} 個章節）</span><span class="mini-toc-arrow">▾</span></summary>
          <ol class="mini-toc-list">
{toc_html}
          </ol>
        </details>"""
        return mini_toc + "\n" + new_html
    return new_html

def build_zhcn_version(zh_hant_html):
    """參考 happy/tools/build_zhcn.py 產生符合大陸在地用語的簡體版本"""
    cn = zh_hant_html
    # 1. 語言宣告與 canonical
    cn = cn.replace('<html lang="zh-Hant">', '<html lang="zh-Hans">')
    cn = cn.replace(f'<link rel="canonical" href="{BASE_URL}" />', f'<link rel="canonical" href="{BASE_URL}zh-cn/" />')
    
    # 2. 簡體專用字型（改載 Noto Serif SC 與 Noto Sans SC，避免混用後備字體）
    cn = cn.replace("Noto+Serif+TC", "Noto+Serif+SC")
    cn = cn.replace("Noto+Sans+TC", "Noto+Sans+SC")
    cn = cn.replace('"Noto Sans TC", "PingFang TC", "Microsoft JhengHei"', '"Noto Sans SC", "PingFang SC", "Microsoft YaHei"')
    cn = cn.replace('"Noto Serif TC", "Songti TC"', '"Noto Serif SC", "Songti SC"')
    
    # 3. 語言切換鈕指回繁體版
    cn = cn.replace(
        '<a class="lang-switch" href="zh-cn/" hreflang="zh-Hans" lang="zh-Hans">简体</a>',
        '<a class="lang-switch" href="../" hreflang="zh-Hant" lang="zh-Hant">繁体</a>'
    )
    
    # 4. OpenCC tw2sp 繁簡詞彙轉換
    cn = CC.convert(cn)
    
    ZH_CN_DIR.mkdir(parents=True, exist_ok=True)
    with open(ZH_CN_OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(cn)
    print(f"✓ 簡體版已產生：{ZH_CN_OUTPUT_PATH.relative_to(ROOT_DIR)}（字型切換為 Noto SC，詞彙 tw2sp 在地化）")

def build_sitemap_and_robots():
    """產出符合 Google 與各大搜尋引擎標準的雙語 sitemap.xml 與 robots.txt"""
    sitemap_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xhtml="http://www.w3.org/1999/xhtml">
  <url>
    <loc>{BASE_URL}</loc>
    <xhtml:link rel="alternate" hreflang="zh-Hant" href="{BASE_URL}"/>
    <xhtml:link rel="alternate" hreflang="zh-Hans" href="{BASE_URL}zh-cn/"/>
    <xhtml:link rel="alternate" hreflang="x-default" href="{BASE_URL}"/>
  </url>
  <url>
    <loc>{BASE_URL}zh-cn/</loc>
    <xhtml:link rel="alternate" hreflang="zh-Hant" href="{BASE_URL}"/>
    <xhtml:link rel="alternate" hreflang="zh-Hans" href="{BASE_URL}zh-cn/"/>
    <xhtml:link rel="alternate" hreflang="x-default" href="{BASE_URL}"/>
  </url>
  <url>
    <loc>{BASE_URL}weekly/</loc>
    <xhtml:link rel="alternate" hreflang="zh-Hant" href="{BASE_URL}weekly/"/>
    <xhtml:link rel="alternate" hreflang="zh-Hans" href="{BASE_URL}zh-cn/weekly/"/>
    <xhtml:link rel="alternate" hreflang="x-default" href="{BASE_URL}weekly/"/>
  </url>
  <url>
    <loc>{BASE_URL}zh-cn/weekly/</loc>
    <xhtml:link rel="alternate" hreflang="zh-Hant" href="{BASE_URL}weekly/"/>
    <xhtml:link rel="alternate" hreflang="zh-Hans" href="{BASE_URL}zh-cn/weekly/"/>
    <xhtml:link rel="alternate" hreflang="x-default" href="{BASE_URL}weekly/"/>
  </url>
</urlset>
"""
    with open(ROOT_DIR / "sitemap.xml", "w", encoding="utf-8") as f:
        f.write(sitemap_xml)

    robots_txt = f"""User-agent: *
Allow: /

Sitemap: {BASE_URL}sitemap.xml
"""
    with open(ROOT_DIR / "robots.txt", "w", encoding="utf-8") as f:
        f.write(robots_txt)
    print("✓ sitemap.xml 與 robots.txt 已更新")

def build():
    # 0. 先編譯每週生活熱點獨立頁
    build_weekly.build_weekly()

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
                clean_title = clean_title_for_menu(title)
                
                total_words, formatted_words, minutes = calc_reading_stats(body)
                rendered_body = render_content(body)
                body_html = inject_mini_toc(report_id, rendered_body)
                
                rep = {
                    "id": report_id,
                    "title": title,
                    "clean_title": clean_title,
                    "date": date,
                    "tag": tag,
                    "point": point,
                    "drive_url": drive_url,
                    "search": search,
                    "total_words": total_words,
                    "formatted_words": formatted_words,
                    "minutes": minutes,
                    "body_html": body_html,
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

    empty_cats = [c["name"] for c in CATEGORIES if len(categories_reports[c["id"]]) == 0 and not c.get("has_series") and not c.get("is_weekly")]
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
        elif cat.get("is_weekly"):
            topbar_dd_lines.append('            <a role="menuitem" href="weekly/"><span class="d-date">全 37 期</span><span>前往每週生活熱點全歸檔頁 ➔</span></a>')
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
        cat_dd_lines = []
        if cat.get("has_series"):
            cat_dd_lines.append('              <a role="menuitem" href="#r-daily-top10"><span class="d-date">每日更新</span><span>每日社群流量 Top10</span></a>')
        if cat.get("is_weekly"):
            cat_dd_lines.append('              <a role="menuitem" href="weekly/"><span class="d-date">全 37 期</span><span>前往每週生活熱點全歸檔頁 ➔</span></a>')
        if reps:
            for r in reps:
                cat_dd_lines.append(f'              <a role="menuitem" href="#{r["id"]}"><span class="d-date">{r["date"]}</span><span>{r["clean_title"]}</span></a>')
        elif cat.get("is_weekly"):
            topbar_dd_lines.append('            <a role="menuitem" href="weekly/"><span class="d-date">全 37 期</span><span>前往每週生活熱點全歸檔頁 ➔</span></a>')
        elif not cat.get("has_series"):
            cat_dd_lines.append('              <span class="d-note">尚無歸檔報告，待累積</span>')
        cat_dd_html = "\n".join(cat_dd_lines)

        report_cards = []
        if cat.get("has_series"):
            report_cards.append(SERIES_CARD_TRAFFIC)
        if cat.get("is_weekly"):
            report_cards.append(render_weekly_series_card())

        if reps:
            for r in reps:
                tag_html = f'<span class="tag">{r["tag"]}</span>' if r["tag"] else ""
                rfoot_html = f'<p class="rfoot"><a class="drive-link" href="{r["drive_url"]}" target="_blank" rel="noopener">雲端原檔 ↗</a></p>' if r["drive_url"] else ""
                card = f"""        <article class="report" id="{r["id"]}" data-search-block data-search="{r["search"]}">
          <header class="report-head">
            <div class="report-meta-row">
              <p class="rmeta">
                <span class="rdate">{r["date"]}</span>{tag_html}
                <span class="rstats" title="全文約 {r["formatted_words"]} 字，預估閱讀時間 {r["minutes"]} 分鐘">約 {r["formatted_words"]} 字 · 閱讀約 {r["minutes"]} 分鐘</span>
              </p>
              <button type="button" class="cite-btn" data-id="{r["id"]}" data-title="{r["clean_title"]}" data-date="{r["date"]}" title="複製本篇研報引用資訊與錨點連結">
                <span class="icon">🔗</span> 複製引用
              </button>
            </div>
            <h3 class="rtitle">{r["title"]}</h3>
            <p class="rpoint">{r["point"]}</p>
          </header>
          <div class="doc">
{r["body_html"]}
          </div>
          {rfoot_html}
        </article>"""
                report_cards.append(card)
        elif cat.get("is_weekly"):
            topbar_dd_lines.append('            <a role="menuitem" href="weekly/"><span class="d-date">全 37 期</span><span>前往每週生活熱點全歸檔頁 ➔</span></a>')
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
          {"<a class=\"folder\" href=\"weekly/\">全歸檔獨立頁 →</a>" if cat.get("is_weekly") else f'<a class="folder" href="{cat["folder"]}" target="_blank" rel="noopener">開啟資料夾 →</a>'}
        </div>
{cat_body}
      </section>"""
        cat_blocks.append(cat_html)

    categories_html = "\n\n".join(cat_blocks)

    # 6. 替換樣板變數產出繁體版
    output = template
    output = output.replace("{{CANONICAL_URL}}", BASE_URL)
    output = output.replace("{{LANG_SWITCH}}", '<a class="lang-switch" href="zh-cn/" hreflang="zh-Hans" lang="zh-Hans">简体</a>')
    output = output.replace("{{TOPBAR_DROPDOWN}}", topbar_dropdown_html)
    output = output.replace("{{TOTAL_REPORTS}}", str(total_count))
    output = output.replace("{{LATEST_DATE}}", latest_date)
    output = output.replace("{{PENDING_CATS_COUNT}}", str(pending_count))
    output = output.replace("{{PENDING_CATS_NAMES}}", pending_names)
    output = output.replace("{{TOC_ITEMS}}", toc_items_html)
    output = output.replace("{{CATEGORIES_HTML}}", categories_html)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"✓ 繁體版編譯成功！已匯總 {total_count} 份報告至 {OUTPUT_PATH.name}（最新日期：{latest_date}）")

    # 7. 產出簡體版 zh-cn/index.html
    if HAS_OPENCC:
        build_zhcn_version(output)

    # 8. 產出 sitemap.xml 與 robots.txt
    build_sitemap_and_robots()

if __name__ == "__main__":
    build()
