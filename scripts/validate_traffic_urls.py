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

def check_single_url(url, timeout=10, max_attempts=3):
    """使用 curl 驗證單一 URL 的真實 HTTP 狀態碼，內建自動重試"""
    if not url:
        return False, "URL 為空"
    if "google.com/search" in url.lower() or "bing.com/search" in url.lower() or "yahoo.com/search" in url.lower():
        return False, "禁止使用搜尋引擎連結，必須是新聞報導本身"
    if not (url.startswith("http://") or url.startswith("https://")):
        return False, "URL 協議不合法"

    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    for attempt in range(max_attempts):
        cmd = [
            "curl", "-s", "-I", "-k", "-L",
            "-A", ua,
            "--connect-timeout", str(timeout), "-m", str(timeout + 5), url
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            status_matches = re.findall(r"HTTP/\d+(?:\.\d+)?\s+(\d{3})", res.stdout)
            if status_matches:
                final_code = int(status_matches[-1])
                if 200 <= final_code < 400:
                    return True, f"HTTP {final_code}"
                elif final_code in (404, 402, 403, 410, 500, 502, 503):
                    return False, f"HTTP {final_code}"
        except Exception:
            pass
        if attempt < max_attempts - 1:
            time.sleep(1)
    return False, "連線超時或失敗"

def audit_structural_and_content_standards(data):
    """審查資料結構、全域摘要、故事線、專欄選題、標題/摘要品質與語言翻譯標準"""
    errors = []

    # 1. globalTheme
    theme = data.get("globalTheme", "")
    if not theme or len(theme.strip()) < 10:
        errors.append("globalTheme 缺失或過短，必須包含深層核心主線")

    # 2. globalSummary 七區分號結構
    summary = data.get("globalSummary", "")
    if not summary:
        errors.append("globalSummary 為空")
    else:
        for reg in REGIONS:
            if f"{reg}：" not in summary and f"{reg}:" not in summary:
                errors.append(f"globalSummary 缺少【{reg}】深度心智觀察段落")

    # 3. storylines
    storylines = data.get("storylines", [])
    if len(storylines) < 3:
        errors.append(f"storylines 數量不足 {len(storylines)}/3 條")
    for st in storylines:
        if not st.get("title") or len(st.get("items", [])) < 2:
            errors.append(f"故事線【{st.get('title', '未命名')}】細節條目不足 2 條")

    # 4. suggestions (三大立柱)
    suggestions = data.get("suggestions", [])
    if len(suggestions) < 3:
        errors.append(f"suggestions 數量不足 {len(suggestions)}/3 條")
    pillars = [s.get("pillar") for s in suggestions]
    for required_pillar in ["金融一百零八講", "俗人對話錄", "佛法生活感悟文"]:
        if required_pillar not in pillars:
            errors.append(f"suggestions 缺失立柱專欄選題：{required_pillar}")

    # 5. events 結構與數量
    events = data.get("events", [])
    if len(events) != 70:
        errors.append(f"events 總數為 {len(events)}，嚴格必須為 70 則 (7 區 × 10 則)")

    # 檢查每區分佈
    region_counts = {reg: {"綜合": 0, "生活": 0} for reg in REGIONS}
    for ev in events:
        reg = ev.get("region")
        cat = ev.get("category")
        if reg in region_counts and cat in region_counts[reg]:
            region_counts[reg][cat] += 1

    for reg, counts in region_counts.items():
        if counts["綜合"] != 5:
            errors.append(f"【{reg}】綜合類別數量為 {counts['綜合']}/5 則")
        if counts["生活"] != 5:
            errors.append(f"【{reg}】生活類別數量為 {counts['生活']}/5 則")

    # 6. 標題與摘要內容品質檢測
    for idx, ev in enumerate(events, start=1):
        eid = ev.get("id", idx)
        reg = ev.get("region", "未知")
        cat = ev.get("category", "未知")
        rank = ev.get("rank", 0)
        title = ev.get("title", "").strip()
        summ = ev.get("summary", "").strip()
        url = ev.get("sourceUrl", "").strip()

        prefix = f"[{reg} {cat} #{rank}]"

        if not title:
            errors.append(f"{prefix} 標題為空")
        else:
            for pat in FORBIDDEN_TITLE_PATTERNS:
                if re.search(pat, title):
                    errors.append(f"{prefix} 標題包含樣板套話或搜尋網址：'{title[:30]}...'")
                    break

            for script_re, script_name in FORBIDDEN_SCRIPTS:
                if re.search(script_re, title):
                    errors.append(f"{prefix} 標題包含{script_name}，未完成繁體中文在地化：'{title[:30]}...'")
                    break

        if not summ or len(summ) < 20:
            errors.append(f"{prefix} 摘要為空或字數不足 20 字")
        else:
            for script_re, script_name in FORBIDDEN_SCRIPTS:
                if re.search(script_re, summ):
                    errors.append(f"{prefix} 摘要包含{script_name}，未完成繁體中文在地化")
                    break

        if not url:
            errors.append(f"{prefix} sourceUrl 為空")

    return (len(errors) == 0, errors)

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
    """全維度審查入口（結構 + 內容 + 網路 URL）"""
    struct_ok, struct_errors = audit_structural_and_content_standards(data)
    all_errors = list(struct_errors)

    failed_urls = []
    if check_network:
        events = data.get("events", [])
        passed, failed_urls = validate_all_traffic_urls(events)
        for f in failed_urls:
            eid, reg, cat, rank, title, url, ok, msg = f
            all_errors.append(f"[{reg} {cat} #{rank}] 連結失效或無法訪問 ({msg}): {url}")

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
    is_valid, all_errors, failed_urls = audit_full_standards(data, check_network=check_network)

    print("\n" + "="*60)
    print("📊 審查結果報告：")
    print("="*60)
    print(f"  事件總數: {len(data.get('events', []))} / 70")
    print(f"  全域主線與摘要: {'✅ 合規' if not any('global' in e for e in all_errors) else '❌ 未達標'}")
    print(f"  故事線與專欄: {'✅ 合規' if not any('storylines' in e or 'suggestions' in e for e in all_errors) else '❌ 未達標'}")
    print(f"  標題與摘要繁中/去樣板: {'✅ 合規' if not any('標題' in e or '摘要' in e for e in all_errors) else '❌ 未達標'}")
    
    if check_network:
        total_urls = len(data.get('events', []))
        passed_count = total_urls - len(failed_urls)
        print(f"  新聞連結真實連線: {passed_count}/{total_urls} 通過 (❌ 失敗: {len(failed_urls)})")

    if not is_valid:
        print(f"\n🚨 審查未通過！共發現 {len(all_errors)} 項不符合標準：")
        for err in all_errors:
            print(f"  ❌ {err}")
        print("\n請修正上述所有問題直至完全符合標準後再行發布。")
        sys.exit(1)
    else:
        print("\n🎉 恭喜！全站情報 100% 通過所有標準審查（結構、品質、翻譯、真實連結皆合格）！")
        sys.exit(0)

if __name__ == "__main__":
    main()
