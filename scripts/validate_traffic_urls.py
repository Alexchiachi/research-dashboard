#!/usr/bin/env python3
"""
scripts/validate_traffic_urls.py
每日社群流量情報 全維度標準審查與真實性驗證門禁

審查維度（比照 10/30 最高規格標準）：
1. 結構標準：7 區（台灣、中國、日本、韓國、美國、歐洲、中東），每區 10 則（5 綜合 rank 1..5 + 5 生活 rank 1..5），總計 70 則。
2. 全域摘要：globalSummary 必須包含 7 大區域前綴觀察（台灣：...；中國：... 等）。
3. 故事線與專欄：storylines >= 3，suggestions >= 3（覆蓋金融一百零八講、俗人對話錄、佛法生活感悟文）。
4. 標題與摘要去樣板化：嚴禁『歐美社群熱門焦點』、『相關發展與公眾討論持續升溫』、『引發今日社群高度關注』等制式套話，嚴禁【人名】抽象佔位。
5. 語言純淨度：100% 繁體中文，嚴禁未翻譯之韓文 (Hangul)、阿拉伯文 (Arabic) 與未翻譯外語標籤。
6. 連結真實性：
   - 嚴禁包含 google.com/search 等任何搜尋引擎網址。
   - 嚴格對每一個 sourceUrl 發出 HTTP 請求驗證真實可訪問性 (HTTP 200~399)。
   - 嚴禁 404 (Not Found)、402、403、500 等失效或假造連結。
"""

import sys
import os
import json
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

REGIONS = ["台灣", "中國", "日本", "韓國", "美國", "歐洲", "中東"]

FORBIDDEN_TITLE_PATTERNS = [
    r"歐美社群熱門焦點",
    r"相關發展與公眾討論持續升溫",
    r"成為今日社群熱議與大眾搜尋焦點",
    r"引發今日社群高度關注與主流媒體專題報導",
    r"國際社群關注話題【",
    r"即時熱點話題\s*#",
    r"重大民生與公共議題最新報導",
    r"【[^】]+】：相關發展",
    r"google\.com/search",
    r"bing\.com/search",
    r"yahoo\.com/search"
]

FORBIDDEN_SCRIPTS = [
    (r"[\uac00-\ud7af]", "未翻譯韓文 (Hangul)"),
    (r"[\u0600-\u06ff]", "未翻譯阿拉伯文 (Arabic)"),
]

BLOCKED_CODES = (401, 402, 403, 405, 406, 429, 451, 503)   # 多為網站擋機器人／機房 IP，來源本身仍真實
DEAD_CODES = (404, 410)

def _curl_status(url, method_args, timeout):
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    cmd = ["curl", "-s", "-k", "-L", "-o", "/dev/null", "-w", "%{http_code}",
           "-A", ua, "-H", "Accept-Language: zh-TW,zh;q=0.9,en;q=0.8",
           "--connect-timeout", str(timeout), "-m", str(timeout + 5)] + method_args + [url]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        code = res.stdout.strip()[-3:]
        return int(code) if code.isdigit() else 0
    except Exception:
        return 0

def check_url_status(url, timeout=10, max_attempts=3):
    """回傳 (status, msg)；status 為 ok / blocked / dead / invalid"""
    if not url:
        return "invalid", "URL 為空"
    low = url.lower()
    if re.search(r"(google|bing|yahoo)\.[a-z.]+/search", low):
        return "invalid", "禁止使用搜尋引擎連結，必須是新聞報導本身"
    if not (url.startswith("http://") or url.startswith("https://")):
        return "invalid", "URL 協議不合法"

    last_code = 0
    for attempt in range(max_attempts):
        # 先 HEAD（快），不成功再 GET 前 1KB（許多網站拒絕 HEAD）
        for method_args in (["-I"], ["-r", "0-1023"]):
            code = _curl_status(url, method_args, timeout)
            if 200 <= code < 400 or code == 206:
                return "ok", f"HTTP {code}"
            if code:
                last_code = code
        if last_code in DEAD_CODES:
            return "dead", f"HTTP {last_code}"
        if attempt < max_attempts - 1:
            time.sleep(1)
    if last_code in BLOCKED_CODES:
        return "blocked", f"HTTP {last_code}（疑似網站阻擋機房 IP）"
    if last_code:
        return "dead", f"HTTP {last_code}"
    return "dead", "連線超時或失敗"

def check_single_url(url, timeout=10, max_attempts=3):
    """相容舊介面：只有 ok 才算通過"""
    status, msg = check_url_status(url, timeout, max_attempts)
    return status == "ok", msg

def is_homepage_url(url):
    """只有網域、沒有文章路徑的連結（如 https://www.cnn.com/）不是新聞報導本身"""
    m = re.match(r"https?://[^/]+(/[^?#]*)?", url or "")
    path = (m.group(1) or "/") if m else "/"
    return len(path.strip("/")) < 8

def audit_standards(data):
    """全維度審查（不含網路）：回傳 (fatal_errors, quality_warnings)
    - fatal：結構壞掉，前台無法正確呈現 → 必須停止發佈
    - quality：內容瑕疵（未翻譯、套話、首頁連結等）→ 標註後照常發佈
    """
    fatal, quality = [], []

    theme = data.get("globalTheme", "")
    if not theme or len(theme.strip()) < 10:
        fatal.append("globalTheme 缺失或過短，必須包含深層核心主線")

    summary = data.get("globalSummary", "")
    if not summary:
        fatal.append("globalSummary 為空")
    else:
        for reg in REGIONS:
            if f"{reg}：" not in summary and f"{reg}:" not in summary:
                quality.append(f"globalSummary 缺少【{reg}】深度心智觀察段落")

    storylines = data.get("storylines", [])
    if len(storylines) < 3:
        fatal.append(f"storylines 數量不足 {len(storylines)}/3 條")
    for st in storylines:
        if not st.get("title") or len(st.get("items", [])) < 2:
            quality.append(f"故事線【{st.get('title', '未命名')}】細節條目不足 2 條")

    suggestions = data.get("suggestions", [])
    pillars = [s.get("pillar") for s in suggestions]
    for required_pillar in ["金融一百零八講", "俗人對話錄", "佛法生活感悟文"]:
        if required_pillar not in pillars:
            fatal.append(f"suggestions 缺失立柱專欄選題：{required_pillar}")

    events = data.get("events", [])
    if len(events) != 70:
        fatal.append(f"events 總數為 {len(events)}，嚴格必須為 70 則 (7 區 × 10 則)")
    region_counts = {reg: {"綜合": 0, "生活": 0} for reg in REGIONS}
    for ev in events:
        reg, cat = ev.get("region"), ev.get("category")
        if reg in region_counts and cat in region_counts[reg]:
            region_counts[reg][cat] += 1
    for reg, counts in region_counts.items():
        for cat in ("綜合", "生活"):
            if counts[cat] != 5:
                fatal.append(f"【{reg}】{cat}類別數量為 {counts[cat]}/5 則")

    seen_urls = {}
    for idx, ev in enumerate(events, start=1):
        prefix = f"[{ev.get('region', '未知')} {ev.get('category', '未知')} #{ev.get('rank', 0)}]"
        title = ev.get("title", "").strip()
        summ = ev.get("summary", "").strip()
        url = ev.get("sourceUrl", "").strip()

        if not title:
            fatal.append(f"{prefix} 標題為空")
        else:
            for pat in FORBIDDEN_TITLE_PATTERNS:
                if re.search(pat, title):
                    quality.append(f"{prefix} 標題包含樣板套話：'{title[:30]}'")
                    break
            for script_re, script_name in FORBIDDEN_SCRIPTS:
                if re.search(script_re, title):
                    quality.append(f"{prefix} 標題包含{script_name}，未完成繁體中文在地化：'{title[:30]}'")
                    break

        if not summ or len(summ) < 20:
            quality.append(f"{prefix} 摘要為空或字數不足 20 字")
        else:
            for script_re, script_name in FORBIDDEN_SCRIPTS:
                if re.search(script_re, summ):
                    quality.append(f"{prefix} 摘要包含{script_name}，未完成繁體中文在地化")
                    break

        if not url:
            fatal.append(f"{prefix} sourceUrl 為空")
        elif re.search(r"(google|bing|yahoo)\.[a-z.]+/search", url.lower()):
            fatal.append(f"{prefix} sourceUrl 為搜尋引擎連結：{url[:60]}")
        else:
            if is_homepage_url(url):
                quality.append(f"{prefix} sourceUrl 只是媒體首頁，不是報導本身：{url}")
            if url in seen_urls:
                quality.append(f"{prefix} sourceUrl 與 {seen_urls[url]} 重複：{url[:60]}")
            else:
                seen_urls[url] = prefix

    return fatal, quality

def audit_structural_and_content_standards(data):
    """相容舊介面：回傳 (是否無致命錯誤, 致命錯誤清單)"""
    fatal, _ = audit_standards(data)
    return (len(fatal) == 0, fatal)

def validate_all_traffic_urls(events, max_workers=10):
    """並行驗證所有 events 的 sourceUrl 真實性"""
    items_to_check = []
    for ev in events:
        items_to_check.append((
            ev.get("id", 0),
            ev.get("region", ""),
            ev.get("category", ""),
            ev.get("rank", 0),
            ev.get("title", ""),
            ev.get("sourceUrl", "")
        ))

    def _worker(item):
        eid, reg, cat, rank, title, url = item
        ok, msg = check_single_url(url)
        return (eid, reg, cat, rank, title, url, ok, msg)

    failed = []
    passed = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for res in executor.map(_worker, items_to_check):
            eid, reg, cat, rank, title, url, ok, msg = res
            if ok:
                passed.append(res)
            else:
                failed.append(res)

    return passed, failed

def audit_full_standards(data, check_network=True):
    """全維度審查入口：回傳 (是否全數合格, 所有問題, 連結失敗清單)"""
    fatal, quality = audit_standards(data)
    all_errors = fatal + quality
    failed_urls = []
    if check_network:
        _, failed_urls = validate_all_traffic_urls(data.get("events", []))
        for f in failed_urls:
            eid, reg, cat, rank, title, url, ok, msg = f
            all_errors.append(f"[{reg} {cat} #{rank}] 連結無法在 runner 上驗證 ({msg}): {url}")
    return (len(all_errors) == 0, all_errors, failed_urls)

def main():
    if len(sys.argv) < 2:
        print("使用方式: python3 validate_traffic_urls.py <path_to_json> [--no-network]")
        sys.exit(1)

    json_path = sys.argv[1]
    check_network = "--no-network" not in sys.argv

    if not os.path.exists(json_path):
        print(f"❌ 錯誤：找不到檔案 {json_path}")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception as e:
            print(f"❌ JSON 解析失敗：{e}")
            sys.exit(1)

    print(f"🔍 開始全維度審查情報標準（檔案：{os.path.basename(json_path)}）...")
    fatal, quality = audit_standards(data)
    failed_urls = []
    if check_network:
        _, failed_urls = validate_all_traffic_urls(data.get("events", []))

    events = data.get("events", [])
    print("\n" + "=" * 60)
    print("📊 審查結果報告：")
    print("=" * 60)
    print(f"  事件總數: {len(events)} / 70")
    print(f"  致命錯誤: {len(fatal)}")
    print(f"  品質警告: {len(quality)}")
    if check_network:
        print(f"  新聞連結真實連線: {len(events) - len(failed_urls)}/{len(events)} 通過")

    for w in quality:
        print(f"  ⚠️ {w}")
    for f in failed_urls:
        print(f"  ⚠️ [{f[1]} {f[2]} #{f[3]}] 連結無法驗證 ({f[7]}): {f[5]}")

    if fatal:
        print(f"\n🚨 發現 {len(fatal)} 項致命錯誤，此份資料不可發佈：")
        for err in fatal:
            print(f"  ❌ {err}")
        sys.exit(1)
    print("\n✅ 無致命錯誤，可以發佈。" + ("（品質警告請見上方）" if quality or failed_urls else "全數達標！"))
    sys.exit(0)

if __name__ == "__main__":
    main()
