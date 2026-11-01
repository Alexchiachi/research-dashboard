#!/usr/bin/env python3
"""
scripts/validate_traffic_urls.py
嚴格驗證每日流量情報 JSON 檔案中所有 70 則情報的 sourceUrl：
1. 嚴禁包含 google.com/search 等搜尋引擎連結
2. 嚴禁空值或格式不合法
3. 嚴格對每一個網址發出 HTTP 請求驗證真實可訪問性 (HTTP 200, 301, 302, 307, 308)
4. 支援 3 次自動重試，過濾網絡抖動
5. 若有任何 404 (Not Found)、402、403、500 等失效或假造連結，立即回報並終止發布。
"""

import sys
import os
import json
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

def check_single_url(url):
    for attempt in range(3):
        cmd = [
            "curl", "-s", "-I", "-k", "-L",
            "-A", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "--connect-timeout", "10", "-m", "15", url
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
        time.sleep(1)
    return False, "連線超時或失敗"

def validate_url(item):
    eid, region, cat, rank, title, url = item
    
    if not url:
        return (eid, region, cat, rank, title, url, False, "URL 為空")

    if "google.com/search" in url.lower() or "bing.com/search" in url.lower() or "yahoo.com/search" in url.lower():
        return (eid, region, cat, rank, title, url, False, "禁止使用搜尋引擎連結，必須是新聞報導本身")
    
    if not (url.startswith("http://") or url.startswith("https://")):
        return (eid, region, cat, rank, title, url, False, "URL 協議不合法")

    ok, msg = check_single_url(url)
    return (eid, region, cat, rank, title, url, ok, msg)

def main():
    if len(sys.argv) < 2:
        print("使用方式: python3 validate_traffic_urls.py <path_to_json>")
        sys.exit(1)

    json_path = sys.argv[1]
    if not os.path.exists(json_path):
        print(f"錯誤：找不到檔案 {json_path}")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    events = data.get("events", [])
    if len(events) != 70:
        print(f"⚠️ 警告：事件數量為 {len(events)}（標準為 7 區 × 10 則 = 70 則）")

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

    print(f"🔍 開始並行驗證 {len(items_to_check)} 則新聞連結真實性 (含自動重試)...")
    failed = []
    passed = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        for res in executor.map(validate_url, items_to_check):
            eid, region, cat, rank, title, url, ok, msg = res
            if ok:
                passed.append(res)
            else:
                failed.append(res)
                print(f"❌ [失敗] [{region} {cat} #{rank}] {title[:30]}... | 狀態: {msg} | 網址: {url}")

    print(f"\n📊 驗證結果彙總：")
    print(f"  總數: {len(items_to_check)}")
    print(f"  ✅ 通過: {len(passed)}")
    print(f"  ❌ 失敗: {len(failed)}")

    if failed:
        print(f"\n🚨 發現 {len(failed)} 個無效或異常連結！拒絕發布，請修正後再試。")
        sys.exit(1)
    else:
        print("🎉 全部 70 則新聞連結 100% 驗證通過，皆為真實有效報導！")
        sys.exit(0)

if __name__ == "__main__":
    main()
