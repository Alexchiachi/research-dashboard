#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大道至簡 · 每日流量情報 Google 雲端硬碟同步腳本 (sync_traffic_to_gdrive.py)

功能：
1. 將 reports/02_traffic/daily/<date>.json 轉為高質感的 Markdown 簡報（含全球主線、人心觀察、故事線、選題與七地 70 則詳細情報）。
2. 同步上傳至 Google Drive 的「02_流量情報」資料夾（ID: 1467YTUDdUK-mlXkddfbN7QhWRGWzBTw_）。
3. 同時上傳 Markdown 簡報與原始 JSON 檔案，實現雙保險雲端留痕。
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
TRAFFIC_DIR = ROOT_DIR / "reports" / "02_traffic"
DAILY_DIR = TRAFFIC_DIR / "daily"
DAILY_MD_DIR = TRAFFIC_DIR / "daily_md"

GDRIVE_TRAFFIC_FOLDER_ID = "1467YTUDdUK-mlXkddfbN7QhWRGWzBTw_"


def find_gdrive():
    exe = shutil.which("gdrive")
    if exe:
        return exe
    fallback = Path.home() / ".gemini/config/plugins/gdrive/skills/gdrive/scripts/gdrive"
    if fallback.exists():
        return str(fallback)
    sys.exit("找不到 gdrive CLI，請確認已安裝並完成登入。")


def run_cmd(args):
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def json_to_markdown(entry):
    date = entry.get("date", "")
    theme = entry.get("globalTheme", "")
    summary = entry.get("globalSummary", "")
    storylines = entry.get("storylines", [])
    suggestions = entry.get("suggestions", [])
    events = entry.get("events", [])

    lines = []
    lines.append(f"# 每日社群流量 Top10 七地情報簡報（{date}）\n")
    lines.append(f"> **出刊日期**：{date}  ")
    lines.append(f"> **涵蓋區域**：台灣 · 中國 · 日本 · 韓國 · 美國 · 歐洲 · 中東（共 {len(events)} 則熱門焦點）  ")
    lines.append(f"> **今日全球主線**：{theme}\n")
    lines.append("---\n")

    lines.append("## 🧭 今日人心觀察\n")
    lines.append(f"{summary}\n")

    if storylines:
        lines.append("## ⚡ 跨區主線與故事線\n")
        for s in storylines:
            lines.append(f"### 【{s.get('kind', '故事線')}】{s.get('title', '')}")
            if s.get("summary"):
                lines.append(f"{s['summary']}\n")
            if s.get("items"):
                for it in s["items"]:
                    lines.append(f"- {it}")
            lines.append("")

    if suggestions:
        lines.append("## 💡 大道至簡專欄選題建議\n")
        for g in suggestions:
            dia = " ◇" if g.get("brandRelevant") else ""
            lines.append(f"### [{g.get('pillar', '專欄')}]{dia} {g.get('title', '')}")
            lines.append(f"**創作方向**：{g.get('direction', '')}\n")

    lines.append("## 🌍 七地社群流量詳細情報\n")
    regions = ["台灣", "中國", "日本", "韓國", "美國", "歐洲", "中東"]
    for r in regions:
        r_events = [e for e in events if e.get("region") == r]
        if not r_events:
            continue
        lines.append(f"### 📍 {r}")
        for cat in ["綜合", "生活"]:
            cat_list = [e for e in r_events if e.get("category") == cat]
            if not cat_list:
                continue
            lines.append(f"\n#### 【{cat}類】")
            for e in sorted(cat_list, key=lambda x: x.get("rank", 0)):
                dia = " ◇" if e.get("brandRelevant") else ""
                url = e.get("sourceUrl", "")
                link_title = f"[{e.get('title', '')}]({url})" if url else e.get("title", "")
                lines.append(f"**{e.get('rank', 0)}. {link_title}**{dia}")
                if e.get("summary"):
                    lines.append(f"> {e['summary']}")
                lines.append("")

    lines.append("---\n")
    lines.append("*本報告由 Antigravity 每日自轉引擎生成並同步至 Google 雲端硬碟與 GitHub Pages。*")
    return "\n".join(lines)


def sync_date_to_gdrive(date_str):
    gd = find_gdrive()
    json_path = DAILY_DIR / f"{date_str}.json"
    if not json_path.exists():
        print(f"錯誤：找不到 {json_path}")
        return False

    entry = json.loads(json_path.read_text("utf-8"))
    DAILY_MD_DIR.mkdir(parents=True, exist_ok=True)
    md_content = json_to_markdown(entry)
    md_path = DAILY_MD_DIR / f"{date_str}-traffic.md"
    md_path.write_text(md_content, "utf-8")
    print(f"  ✓ 本機 Markdown 簡報已生成：{md_path.name}")

    # 上傳 Markdown 簡報至 Google Drive「02_流量情報」資料夾
    print(f"  ⬆ 正在上傳 {md_path.name} 至 Google 雲端硬碟「02_流量情報」資料夾...")
    try:
        upload_res = run_cmd([gd, "mutate", "upload", str(md_path), "--parent", GDRIVE_TRAFFIC_FOLDER_ID])
        print(f"  ✓ {upload_res.strip()}")
    except Exception as e:
        print(f"  ⚠️ Markdown 上傳提示: {e}")

    # 同步上傳原始 JSON 檔案
    print(f"  ⬆ 正在上傳 {json_path.name} 至 Google 雲端硬碟...")
    try:
        upload_json_res = run_cmd([gd, "mutate", "upload", str(json_path), "--parent", GDRIVE_TRAFFIC_FOLDER_ID])
        print(f"  ✓ {upload_json_res.strip()}")
    except Exception as e:
        print(f"  ⚠️ JSON 上傳提示: {e}")

    return True


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "2026-10-31"
    sync_date_to_gdrive(target)
