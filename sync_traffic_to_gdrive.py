#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大道至簡 · 每日流量情報 Google 雲端硬碟同步腳本 (sync_traffic_to_gdrive.py)

功能：
1. 將 reports/02_traffic/daily/<date>.json 轉為高質感的 Markdown 簡報（含全球主線、人心觀察、故事線、選題與七地 70 則詳細情報）。
2. 同步上傳至 Google Drive 的「02_流量情報」資料夾（ID: 1467YTUDdUK-mlXkddfbN7QhWRGWzBTw_）。
3. 支援雙模式：
   - 模式 A（本機模式）：調用系統本機之 gdrive CLI（利用既有登入授權）。
   - 模式 B（雲端 Actions 模式）：讀取環境變數 GDRIVE_SERVICE_ACCOUNT_KEY（JSON 字串），以 Google 官方 REST API 免依賴上傳。
"""

import os
import sys
import json
import shutil
import subprocess
import urllib.request
import urllib.error
import time
import base64
import hmac
import hashlib
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
    return None


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


# -------------------------------------------------------------
# 雲端原生 Google Drive API 上傳 (免安裝 gdrive CLI，支援 Service Account)
# -------------------------------------------------------------
def get_service_account_token(sa_info: dict) -> str:
    # 支援標準 Google OAuth2 JWT Bearer Flow
    import urllib.parse
    header = {"alg": "RS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "iss": sa_info["client_email"],
        "scope": "https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/drive",
        "aud": "https://oauth2.googleapis.com/token",
        "exp": now + 3600,
        "iat": now
    }
    
    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')
    
    encoded_header = b64url(json.dumps(header).encode('utf-8'))
    encoded_payload = b64url(json.dumps(payload).encode('utf-8'))
    unsigned_jwt = f"{encoded_header}.{encoded_payload}"
    
    # 使用 private_key 進行 RS256 簽名
    # 若在 GitHub Actions 容器中未預裝 cryptography，可用 openssl 簽名
    p_key = sa_info["private_key"]
    sign_cmd = subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", "/dev/stdin"],
        input=p_key.encode('utf-8'),
        capture_output=True,
        check=True
    )
    signature = sign_cmd.stdout
    jwt = f"{unsigned_jwt}.{b64url(signature)}"
    
    token_req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=urllib.parse.urlencode({
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwt
        }).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    with urllib.request.urlopen(token_req) as resp:
        res = json.loads(resp.read().decode('utf-8'))
        return res["access_token"]


def upload_via_service_account(file_path: Path, parent_id: str, sa_info: dict, mime_type: str = "text/plain"):
    token = get_service_account_token(sa_info)
    metadata = {
        "name": file_path.name,
        "parents": [parent_id]
    }
    
    boundary = "-------314159265358979323846"
    delimiter = f"\r\n--{boundary}\r\n".encode('utf-8')
    close_delimiter = f"\r\n--{boundary}--\r\n".encode('utf-8')
    
    body = bytearray()
    body.extend(delimiter)
    body.extend(b"Content-Type: application/json; charset=UTF-8\r\n\r\n")
    body.extend(json.dumps(metadata).encode('utf-8'))
    body.extend(delimiter)
    body.extend(f"Content-Type: {mime_type}\r\n\r\n".encode('utf-8'))
    body.extend(file_path.read_bytes())
    body.extend(close_delimiter)
    
    req = urllib.request.Request(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
        data=bytes(body),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/related; boundary={boundary}"
        }
    )
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode('utf-8'))
        return res.get("id")


def sync_date_to_gdrive(date_str):
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

    sa_key_env = os.environ.get("GDRIVE_SERVICE_ACCOUNT_KEY")
    if sa_key_env:
        # 雲端 Actions 模式
        print("  🌐 偵測到 GDRIVE_SERVICE_ACCOUNT_KEY，使用 Google Drive REST API 上傳...")
        try:
            sa_info = json.loads(sa_key_env)
            md_file_id = upload_via_service_account(md_path, GDRIVE_TRAFFIC_FOLDER_ID, sa_info, "text/markdown")
            print(f"  ✓ Markdown 上傳成功 (ID: {md_file_id})")
            json_file_id = upload_via_service_account(json_path, GDRIVE_TRAFFIC_FOLDER_ID, sa_info, "application/json")
            print(f"  ✓ JSON 上傳成功 (ID: {json_file_id})")
            return True
        except Exception as e:
            print(f"  ⚠️ 雲端 REST API 上傳失敗: {e}")
            return False

    # 本機模式：尋找 gdrive CLI
    gd = find_gdrive()
    if not gd:
        print("  ℹ️ 未配置 GDRIVE_SERVICE_ACCOUNT_KEY 且找不到 gdrive CLI，跳過 Google Drive 上傳。")
        return True

    print(f"  ⬆ 正在透過本機 gdrive CLI 上傳 {md_path.name} 至「02_流量情報」資料夾...")
    try:
        upload_res = run_cmd([gd, "mutate", "upload", str(md_path), "--parent", GDRIVE_TRAFFIC_FOLDER_ID])
        print(f"  ✓ {upload_res.strip()}")
    except Exception as e:
        print(f"  ⚠️ Markdown 上傳提示: {e}")

    print(f"  ⬆ 正在透過本機 gdrive CLI 上傳 {json_path.name} 至「02_流量情報」資料夾...")
    try:
        upload_json_res = run_cmd([gd, "mutate", "upload", str(json_path), "--parent", GDRIVE_TRAFFIC_FOLDER_ID])
        print(f"  ✓ {upload_json_res.strip()}")
    except Exception as e:
        print(f"  ⚠️ JSON 上傳提示: {e}")

    return True


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "2026-10-31"
    sync_date_to_gdrive(target)
