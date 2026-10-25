#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大道至簡 · 每週生活熱點 × 社會創新 同步腳本 (sync_weekly.py)

從 Google Drive 搜尋所有「每週生活熱點×社會創新 YYYY-MM-DD」文件，
以 Markdown 格式匯出到 reports/06_weekly/raw/，並更新 manifest.json。
已同步過的期數預設略過（加 --force 可全部重新匯出）。

需求：gdrive CLI 已登入（gdrive auth status）。
用法：
    python3 sync_weekly.py            # 只同步新期數
    python3 sync_weekly.py --force    # 全部重新匯出
    python3 sync_weekly.py && python3 build.py   # 同步後一鍵編譯
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
WEEKLY_DIR = ROOT_DIR / "reports" / "06_weekly"
RAW_DIR = WEEKLY_DIR / "raw"
MANIFEST = WEEKLY_DIR / "manifest.json"
NAME_PREFIX = "每週生活熱點"
NAME_RE = re.compile(r"每週生活熱點\s*[×xX]\s*社會創新\s*(\d{4}-\d{2}-\d{2})")


def find_gdrive():
    exe = shutil.which("gdrive")
    if exe:
        return exe
    fallback = Path.home() / ".gemini/config/plugins/gdrive/skills/gdrive/scripts/gdrive"
    if fallback.exists():
        return str(fallback)
    sys.exit("找不到 gdrive CLI，請先安裝並登入。")


def run(gd, *args):
    return subprocess.run([gd, *args], check=True, capture_output=True, text=True).stdout


def main():
    force = "--force" in sys.argv
    gd = find_gdrive()
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(MANIFEST.read_text("utf-8")) if MANIFEST.exists() else {}
    files = json.loads(run(gd, "readonly", "search", "--name-contains", NAME_PREFIX,
                           "--type", "document", "--max", "1000", "--json"))

    found = {}
    for f in files:
        m = NAME_RE.search(f.get("name", ""))
        if m:
            found[m.group(1)] = f["id"]

    new_count = 0
    for date in sorted(found):
        fid = found[date]
        out = RAW_DIR / f"{date}.md"
        if out.exists() and not force and manifest.get(date, {}).get("id") == fid:
            continue
        run(gd, "readonly", "export", fid, str(out), "--format", "md")
        manifest[date] = {
            "id": fid,
            "drive_url": f"https://docs.google.com/document/d/{fid}/edit",
        }
        new_count += 1
        print(f"  ✓ 匯出 {date}")

    MANIFEST.write_text(json.dumps(dict(sorted(manifest.items())), ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"同步完成：雲端共 {len(found)} 期，本次新增／更新 {new_count} 期。")


if __name__ == "__main__":
    main()
