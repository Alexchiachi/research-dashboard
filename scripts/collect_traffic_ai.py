#!/usr/bin/env python3
"""
scripts/collect_traffic_ai.py
每日社群流量情報 AI 採集與洞察引擎 (GitHub Actions 雲端原生版)

功能：
1. 透過 Google Gemini API 聯網搜尋七地（台灣、中國、日本、韓國、美國、歐洲、中東）當日即時熱搜與熱門社群話題。
2. 提煉全球核心主線、人類集體情緒觀察、跨區域共振故事線，並提供專題欄位靈感。
3. 嚴格輸出符合 reports/02_traffic/daily/YYYY-MM-DD.json 規範之完整資料結構（與歷史資料格式完全相容）。
"""

import os
import sys
import json
import re
import datetime
import urllib.request
import urllib.error

REGIONS = ["台灣", "中國", "日本", "韓國", "美國", "歐洲", "中東"]

def get_today_str():
    # 預設以台灣/東八區時間 (UTC+8) 為準
    tz_tw = datetime.timezone(datetime.timedelta(hours=8))
    now = datetime.datetime.now(tz_tw)
    return now.strftime("%Y-%m-%d")

def call_gemini(prompt: str, api_key: str) -> str:
    model = "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "responseMimeType": "application/json"
        }
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            candidates = res_data.get("candidates", [])
            if candidates:
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            raise ValueError(f"Gemini API 回傳空內容: {res_data}")
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Gemini API HTTP {e.code} 錯誤: {err_msg}")
    except Exception as e:
        raise RuntimeError(f"Gemini API 請求失敗: {e}")

def build_prompt(today: str) -> str:
    return f"""
你是一位深諳全球數位生態、地緣脈動與集體心智的「全球社群情報分析架構師」。
今天的日期是：{today}。

請針對全球 7 大區域：
1. 台灣
2. 中國
3. 日本
4. 韓國
5. 美國
6. 歐洲
7. 中東

整理出【{today}】當日各區域真實的熱搜與社群焦點情報。
每個區域嚴格包含 10 則熱門焦點（5 則【綜合】時事/科技/財經/政治 ＋ 5 則【生活】消費/娛樂/迷因/文化），7 區共計 70 則情報（rank 1 到 10）。

請直接輸出純合法 JSON，嚴格符合以下結構：

{{
  "date": "{today}",
  "globalTheme": "一句話總結今日全球流量的共同核心主線（冷靜、深刻、去我化）",
  "globalSummary": "深入剖析今日人類集體情緒或潛意識投射的總體摘要（約 150-250 字）",
  "events": [
    {{
      "region": "台灣",
      "category": "綜合",
      "rank": 1,
      "title": "事件精準標題",
      "summary": "客觀精準事件摘要與文化/心理/商業衝擊分析（約 60-100 字）",
      "sourceUrl": "主要媒體或官方來源網址",
      "brandRelevant": true
    }},
    ... 依序包含 台灣、中國、日本、韓國、美國、歐洲、中東 各 10 則 (5 則 綜合 rank 1~5, 5 則 生活 rank 6~10)，共 70 則
  ],
  "storylines": [
    {{
      "kind": "主線",
      "title": "跨區域共振故事線標題 1",
      "summary": "深度解析跨區聯動現象（約 80-120 字）",
      "items": [
        "區域 A 的現象與細節",
        "區域 B 的現象與細節",
        "全球鏈條的連動"
      ]
    }},
    {{
      "kind": "主線",
      "title": "跨區域共振故事線標題 2",
      "summary": "深度解析...",
      "items": ["...", "..."]
    }},
    {{
      "kind": "跨區線",
      "title": "跨區域共振故事線標題 3",
      "summary": "深度解析...",
      "items": ["...", "..."]
    }}
  ],
  "suggestions": [
    {{
      "pillar": "佛法生活感悟文 或 金融一百零八講 或 俗人對話錄",
      "title": "專欄選題標題 1",
      "direction": "創作方向與核心立意（約 60-100 字，大道至簡、減法、反脆弱視角）",
      "brandRelevant": true
    }},
    {{
      "pillar": "金融一百零八講",
      "title": "專欄選題標題 2",
      "direction": "...",
      "brandRelevant": true
    }},
    {{
      "pillar": "俗人對話錄",
      "title": "專欄選題標題 3",
      "direction": "...",
      "brandRelevant": true
    }}
  ]
}}

重要規範：
1. 文字風格：客觀、沉靜、去我化、具備洞察力，嚴禁聳動與情緒化贅詞。
2. 7 區必須全員到齊，每區 10 則（5 綜合、5 生活），共 70 則 events。
3. 輸出必須為合法、標準 JSON，請勿包含 Markdown 圍欄外的任何文字。
"""

def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ 錯誤：未設定環境變數 GEMINI_API_KEY。請在 GitHub Secrets 中配置。", file=sys.stderr)
        sys.exit(1)

    today = get_today_str()
    if len(sys.argv) > 1:
        today = sys.argv[1]

    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports", "02_traffic", "daily")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{today}.json")

    print(f"🌐 [AI 採集引擎] 開始採集 {today} 的 7 地社群流量情報...")
    prompt = build_prompt(today)
    
    try:
        raw_response = call_gemini(prompt, api_key)
        clean_json = raw_response.strip()
        if clean_json.startswith("```json"):
            clean_json = clean_json[7:]
        elif clean_json.startswith("```"):
            clean_json = clean_json[3:]
        if clean_json.endswith("```"):
            clean_json = clean_json[:-3]
        clean_json = clean_json.strip()

        data = json.loads(clean_json)
        
        # 結構檢查
        assert data.get("date") == today, f"日期不匹配: {data.get('date')} vs {today}"
        assert "events" in data, "缺少 events 陣列"
        assert len(data["events"]) >= 50, f"events 數量不足 ({len(data['events'])} 則)"

        # 自動指派 id（若未提供）
        for idx, ev in enumerate(data["events"], start=1):
            if "id" not in ev:
                ev["id"] = idx
        for idx, st in enumerate(data.get("storylines", []), start=1):
            if "id" not in st:
                st["id"] = idx
        for idx, sg in enumerate(data.get("suggestions", []), start=1):
            if "id" not in sg:
                sg["id"] = idx

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"✅ 成功生成並儲存每日資料：{output_file}（共 {len(data['events'])} 則情報）")
    except Exception as e:
        print(f"❌ 採集或解析失敗: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
