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
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import urllib.parse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
WEEKLY_DIR = ROOT_DIR / "reports" / "06_weekly"
RAW_DIR = WEEKLY_DIR / "raw"
MANIFEST = WEEKLY_DIR / "manifest.json"
NAME_PREFIX = "每週生活熱點"
NAME_RE = re.compile(r"每週生活熱點\s*[×xX]\s*社會創新\s*(\d{4}-\d{2}-\d{2})")


def get_oauth_token():
    """從雲端主機憑證路徑或環境變數取得 Google OAuth Access Token"""
    cand_pairs = [
        (
            Path("/opt/morning-brief/credentials/gcp-oauth.keys.json"),
            Path("/opt/morning-brief/credentials/.gdrive-server-credentials.json"),
        ),
        (
            Path.home() / ".config/morning-brief/gcp-oauth.keys.json",
            Path.home() / ".config/morning-brief/.gdrive-server-credentials.json",
        )
    ]
    for key_file, token_file in cand_pairs:
        if key_file.exists() and token_file.exists():
            try:
                keys_data = json.loads(key_file.read_text("utf-8"))
                keys = keys_data.get("installed") or keys_data.get("web") or {}
                token_data = json.loads(token_file.read_text("utf-8"))
                client_id = keys.get("client_id")
                client_secret = keys.get("client_secret")
                refresh_token = token_data.get("refresh_token")
                if client_id and client_secret and refresh_token:
                    req = urllib.request.Request(
                        "https://oauth2.googleapis.com/token",
                        data=urllib.parse.urlencode({
                            "client_id": client_id,
                            "client_secret": client_secret,
                            "refresh_token": refresh_token,
                            "grant_type": "refresh_token"
                        }).encode("utf-8"),
                        headers={"Content-Type": "application/x-www-form-urlencoded"}
                    )
                    with urllib.request.urlopen(req) as resp:
                        res = json.loads(resp.read().decode("utf-8"))
                        return res.get("access_token")
            except Exception as e:
                print(f"  ⚠️ 讀取 OAuth 憑證失敗 ({key_file}): {e}")
    return None


def search_files_api(token):
    q = f"name contains '{NAME_PREFIX}' and mimeType = 'application/vnd.google-apps.document' and trashed = false"
    url = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode({
        "q": q,
        "fields": "files(id,name)",
        "pageSize": 1000
    })
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8")).get("files", [])


def export_doc_markdown_api(token, file_id, out_path):
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}/export?mimeType=text/markdown"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        content = resp.read()
    out_path.write_bytes(content)


def find_gdrive():
    exe = shutil.which("gdrive")
    if exe:
        return exe
    fallback = Path.home() / ".gemini/config/plugins/gdrive/skills/gdrive/scripts/gdrive"
    if fallback.exists():
        return str(fallback)
    return None


def run(gd, *args):
    return subprocess.run([gd, *args], check=True, capture_output=True, text=True).stdout


def main():
    force = "--force" in sys.argv
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text("utf-8")) if MANIFEST.exists() else {}

    token = get_oauth_token()
    files = []
    use_api = False

    if token:
        try:
            print("  🌐 偵測到雲端主機 Google OAuth 憑證，直接使用 Google Drive REST API 檢索...")
            files = search_files_api(token)
            use_api = True
        except Exception as e:
            print(f"  ⚠️ REST API 檢索失敗，嘗試本機 CLI: {e}")

    if not use_api:
        gd = find_gdrive()
        if not gd:
            sys.exit("找不到有效的 Google Drive 憑證或 gdrive CLI。")
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
        if use_api:
            export_doc_markdown_api(token, fid, out)
        else:
            run(gd, "readonly", "export", fid, str(out), "--format", "md")
        manifest[date] = {
            "id": fid,
            "drive_url": f"https://docs.google.com/document/d/{fid}/edit",
        }
        new_count += 1
        print(f"  ✓ 匯出 {date}")

    MANIFEST.write_text(json.dumps(dict(sorted(manifest.items())), ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"同步完成：雲端共 {len(found)} 期，本次新增／更新 {new_count} 期。")
    return new_count


if __name__ == "__main__":
    main()
