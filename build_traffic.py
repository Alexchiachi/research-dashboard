#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大道至簡 · 流量情報編譯模組 (build_traffic.py)
負責讀取 reports/02_traffic/daily/*.json，按日期由新到舊排序，
將資料編譯為 reports/02_traffic/data.json，並同步注入至 traffic.html。
"""

import json
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
TRAFFIC_DIR = ROOT_DIR / "reports" / "02_traffic"
DAILY_DIR = TRAFFIC_DIR / "daily"
DATA_JSON_PATH = TRAFFIC_DIR / "data.json"
TRAFFIC_HTML_PATH = ROOT_DIR / "traffic.html"

def load_daily_entries():
    """載入所有每日流量 JSON 檔案，按日期由新到舊排序"""
    if not DAILY_DIR.exists():
        DAILY_DIR.mkdir(parents=True, exist_ok=True)
    
    entries = []
    for f in DAILY_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text("utf-8"))
            if isinstance(d, dict) and "date" in d:
                entries.append(d)
        except Exception as e:
            print(f"警告：讀取 {f.name} 失敗: {e}")
    
    # 依日期遞減排序 (最新排最前)
    entries.sort(key=lambda x: x.get("date", ""), reverse=True)
    return entries

def build_traffic():
    entries = load_daily_entries()
    if not entries:
        print("未在 reports/02_traffic/daily 找到任何資料。")
        return False
    
    # 1. 輸出至 reports/02_traffic/data.json
    json_str = json.dumps(entries, ensure_ascii=False, indent=2)
    DATA_JSON_PATH.write_text(json_str + "\n", "utf-8")
    print(f"  ✓ 成功編譯 {DATA_JSON_PATH.name}（共 {len(entries)} 期，最新日期：{entries[0]['date']}）")
    
    # 2. 將編譯後陣列同步注入 traffic.html 中的 const DATA = [...]
    if TRAFFIC_HTML_PATH.exists():
        html = TRAFFIC_HTML_PATH.read_text("utf-8")
        # 替換 const DATA = [...];
        compact_json = json.dumps(entries, ensure_ascii=False)
        new_html, count = re.subn(
            r'const DATA = (\[.*?\]);\s*const REGIONS',
            lambda _: f'const DATA = {compact_json};\nconst REGIONS',
            html,
            flags=re.DOTALL
        )
        if count > 0:
            TRAFFIC_HTML_PATH.write_text(new_html, "utf-8")
            print(f"  ✓ 成功注入 {TRAFFIC_HTML_PATH.name}（已更新至最新 {entries[0]['date']}）")
        else:
            print("  ⚠️ 在 traffic.html 中未匹配到 const DATA 宣告，請手動確認結構。")
    
    return True

if __name__ == "__main__":
    build_traffic()
