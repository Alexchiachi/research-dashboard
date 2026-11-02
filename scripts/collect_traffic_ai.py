#!/usr/bin/env python3
"""
scripts/collect_traffic_ai.py
每日社群流量情報採集引擎（Source-First 架構）

流程：
1. 真實來源（news_sources.py）：Google Trends 熱搜 RSS ＋ 各區主流媒體 RSS → 每區候選池（網址皆為真實報導）
2. AI 編輯（Gemini）：只能「以 cid 挑選」候選，負責分類、排序、翻譯成繁中、撰寫摘要與全域分析
   → 程式以 cid 對回原始網址，AI 無法產生或竄改任何網址
3. 無 AI 備援：Gemini 失敗時，程式依熱度挑選＋免費翻譯端點翻成繁中，仍是今天的真實報導
4. 分級審查：致命錯誤（結構）才停止；品質瑕疵與連結無法驗證 → 標註後照常發佈（每天一定有發佈）
"""

import os
import sys
import json
import re
import datetime
import urllib.request
import urllib.error
import urllib.parse
import ssl
import time

from validate_traffic_urls import (
    audit_standards,
    REGIONS,
    FORBIDDEN_SCRIPTS,
)
from news_sources import collect_candidates, MEDIA_FEEDS

try:
    from opencc import OpenCC
    _S2T = OpenCC("s2twp")
except Exception:
    _S2T = None


def get_today_str():
    tz_tw = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(tz_tw).strftime("%Y-%m-%d")


def get_ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def to_traditional(s: str) -> str:
    return _S2T.convert(s) if (_S2T and s) else s


def has_foreign_script(s: str) -> bool:
    return any(re.search(p, s or "") for p, _ in FORBIDDEN_SCRIPTS) or bool(re.search(r"[぀-ヿ]", s or ""))


def is_mostly_latin(s: str) -> bool:
    letters = re.findall(r"[A-Za-z]", s or "")
    cjk = re.findall(r"[一-鿿]", s or "")
    return len(letters) > 8 and len(letters) > len(cjk) * 2


# -------------------------------------------------------------
# Gemini 調用（模型自動探測＋暫時性錯誤退避重試）
# -------------------------------------------------------------
GEMINI_STATIC_FALLBACK_MODELS = ["gemini-3.8-flash", "gemini-3.7-flash"]

def _model_version_key(name: str):
    """將 gemini-3.8-flash 之類的名稱轉為可排序的版本 tuple（新版本優先）"""
    m = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
    ver = float(m.group(1)) if m else 0.0
    # 正式版優先於 preview / exp，完整 flash 優先於 lite
    unstable = 1 if re.search(r"preview|exp", name) else 0
    lite = 1 if "lite" in name else 0
    return (-ver, unstable, lite, name)

def list_available_flash_models(api_key: str) -> list:
    """透過 ListModels 查詢目前帳號實際可用、支援 generateContent 的 flash 模型"""
    ctx = get_ssl_context()
    found = []
    page_token = ""
    try:
        for _ in range(5):
            url = f"https://generativelanguage.googleapis.com/v1beta/models?pageSize=100&key={api_key}"
            if page_token:
                url += f"&pageToken={urllib.parse.quote(page_token)}"
            with urllib.request.urlopen(url, context=ctx, timeout=20) as resp:
                res = json.loads(resp.read().decode("utf-8"))
            for m in res.get("models", []):
                name = m.get("name", "").replace("models/", "")
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" in methods and "flash" in name and "gemini" in name \
                        and not re.search(r"image|tts|audio|live|embedding|thinking", name):
                    found.append(name)
            page_token = res.get("nextPageToken", "")
            if not page_token:
                break
    except Exception as e:
        print(f"⚠️ Gemini ListModels 查詢失敗（{e}），改用靜態模型清單", file=sys.stderr)
    return sorted(set(found), key=_model_version_key)

def resolve_gemini_models(api_key: str) -> list:
    """模型優先序：環境變數 GEMINI_MODEL（可逗號分隔）> ListModels 自動探測 > 靜態備援清單"""
    models = []
    env_models = os.environ.get("GEMINI_MODEL", "").strip()
    if env_models:
        models.extend([m.strip() for m in env_models.split(",") if m.strip()])
    models.extend(list_available_flash_models(api_key)[:3])
    models.extend(GEMINI_STATIC_FALLBACK_MODELS)
    deduped = []
    for m in models:
        if m not in deduped:
            deduped.append(m)
    print(f"🤖 Gemini 候選模型順序：{deduped}")
    return deduped

_MODELS_CACHE = {}

def call_gemini(prompt: str, api_key: str, tag: str = "", timeout: int = 150) -> str:
    if "models" not in _MODELS_CACHE:
        _MODELS_CACHE["models"] = resolve_gemini_models(api_key)
    models = _MODELS_CACHE["models"]
    label = f"[{tag}] " if tag else ""
    last_err = None
    ctx = get_ssl_context()
    
    attempts = [(m, n) for m in models for n in range(3)]
    for model, attempt in attempts:
        if attempt > 0:
            # 503 高負載 / 429 限流 / 逾時屬暫時性錯誤：退避後重試同一模型
            if not isinstance(last_err, str) or not re.search(r"HTTP (503|429|500)|timed out", last_err):
                continue
            wait = 15 * attempt
            print(f"   ⏳ {label}{model} 暫時性錯誤，{wait} 秒後重試（第 {attempt + 1}/3 次）...")
            time.sleep(wait)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "responseMimeType": "application/json"
            }
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                candidates = res_data.get("candidates", [])
                if candidates:
                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])
                    if parts:
                        return parts[0].get("text", "")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            print(f"   ⚠️ {label}Gemini {model} HTTP {e.code}: {err_body[:120]}")
            last_err = f"HTTP {e.code}: {err_body[:100]}"
            if e.code == 404:
                last_err = f"model gone {e.code}: {err_body[:100]}"
            continue
        except Exception as e:
            print(f"   ⚠️ {label}Gemini {model} 呼叫異常: {e}")
            last_err = f"{type(e).__name__}: {e}"
            continue
            
    raise RuntimeError(f"Gemini API 請求失敗: {last_err}")



MAX_PER_OUTLET = 3   # 同一媒體在同一區最多選 3 則，維持觀點多元


def outlet_of(c: dict) -> str:
    """「中新網 國內」「中新網 社會」視為同一家媒體"""
    return (c.get("source") or "").split(" ")[0].strip() or c.get("url", "")


def build_region_prompt(today: str, reg: str, cands: list) -> str:
    compact = [{
        "cid": c["cid"],
        "type": "熱搜" if c["kind"] == "trend" else "媒體",
        "熱搜詞": c.get("query", ""),
        "熱度": c.get("traffic", 0),
        "來源": c.get("source", ""),
        "原文標題": c["title"],
        "摘要片段": c.get("snippet", "")[:200],
    } for c in cands]
    return f"""
你是「全球社群情報」的【{reg}】區編輯。今天的日期是 {today}。
下面是程式從 Google Trends 熱搜與{reg}主流媒體 RSS 抓到的【今天真實報導候選清單】，每則都有唯一代號 cid。

任務：
1. 挑出 5 則【綜合】（政經、國際、社會重大新聞）與 5 則【生活】（消費、娛樂、體育、文化、健康），
   依社群熱度與重要性排序（rank 1 最重要），cid 不得重複。
2. 每則新聞必須與{reg}本身直接相關（在{reg}發生、或直接牽涉{reg}），不可選只是用當地語言報導的其他地區新聞。
3. 來源要多元：同一家媒體（「來源」欄位第一個詞相同即視為同一家）最多選 {MAX_PER_OUTLET} 則。
4. 每則撰寫：
   - title：精準的繁體中文新聞標題（主語＋動作＋事件），外語必須完整翻譯，不可保留外文字。
   - summary：60~110 字繁體中文摘要。只能根據「原文標題」與「摘要片段」提供的事實撰寫，
     不得自行補充候選中沒有的數字、人名或細節；可加一句社會心理或生活面的觀察。
5. observation：用 40~70 字繁體中文寫出今天{reg}社群與大眾心理的整體觀察。
6. 絕對禁止：輸出任何網址；使用「相關發展與公眾討論持續升溫」「引發今日社群高度關注」之類的空泛套話。

候選清單（JSON）：
{json.dumps(compact, ensure_ascii=False)}

只輸出合法 JSON：
{{
  "observation": "今天{reg}的整體觀察",
  "events": [
    {{"cid": "{cands[0]['cid'] if cands else 'XX-01'}", "category": "綜合", "rank": 1, "title": "繁中標題", "summary": "繁中摘要", "brandRelevant": true}}
  ]
}}
"""


def build_global_prompt(today: str, region_results: dict, by_cid: dict) -> str:
    brief = {}
    for reg in REGIONS:
        res = region_results.get(reg) or {}
        brief[reg] = {
            "觀察": res.get("observation", ""),
            "頭條": [ev.get("title") or by_cid.get(ev.get("cid"), {}).get("title", "")
                   for ev in (res.get("events") or [])][:10],
        }
    return f"""
你是「全球社群情報」的總編輯。今天的日期是 {today}。以下是七區編輯已完成的今日選稿（標題與區域觀察）：
{json.dumps(brief, ensure_ascii=False)}

請根據以上內容（不可加入清單以外的事件）撰寫：
1. globalTheme：一句話總結今日全球流量的共同核心主線（20~40 字）。
2. storylines：3~5 條跨區深度主線，每條 items 至少 2 條，皆須對應上面的頭條。
3. suggestions：3 則選題，pillar 分別為「金融一百零八講」「俗人對話錄」「佛法生活感悟文」。

只輸出合法 JSON：
{{
  "globalTheme": "…",
  "storylines": [{{"id": 1, "kind": "跨區線", "title": "主線標題", "summary": "深層分析", "items": ["細節 1", "細節 2"]}}],
  "suggestions": [
    {{"id": 1, "pillar": "金融一百零八講", "title": "選題", "direction": "核心立意", "brandRelevant": true}},
    {{"id": 2, "pillar": "俗人對話錄", "title": "選題", "direction": "核心立意", "brandRelevant": true}},
    {{"id": 3, "pillar": "佛法生活感悟文", "title": "選題", "direction": "核心立意", "brandRelevant": false}}
  ]
}}
"""


def run_ai_editors(today: str, pools: dict, api_key: str) -> dict:
    """七區同時送出（每區一個小請求），任一區失敗只影響該區；最後再做一次全域分析"""
    from concurrent.futures import ThreadPoolExecutor
    by_cid = {c["cid"]: c for reg in REGIONS for c in pools[reg]}

    def _one(reg):
        if not pools[reg]:
            return reg, None
        t0 = time.time()
        try:
            res = parse_json_response(call_gemini(build_region_prompt(today, reg, pools[reg]), api_key, tag=reg, timeout=120))
            print(f"   ✓ [{reg}] 選稿 {len(res.get('events', []))} 則（{time.time() - t0:.0f} 秒）")
            return reg, res
        except Exception as e:
            print(f"   ⚠️ [{reg}] AI 編輯失敗（{str(e)[:120]}），該區改用程式挑選＋自動翻譯")
            return reg, None

    if "models" not in _MODELS_CACHE:
        _MODELS_CACHE["models"] = resolve_gemini_models(api_key)
    with ThreadPoolExecutor(max_workers=7) as ex:
        region_results = dict(ex.map(_one, REGIONS))

    ok_regions = [r for r in REGIONS if region_results.get(r)]
    if not ok_regions:
        return None

    ai = {"events": [], "regionsByAI": ok_regions}
    obs = []
    for reg in REGIONS:
        res = region_results.get(reg)
        if res:
            ai["events"].extend(res.get("events", []))
            if res.get("observation"):
                obs.append(f"{reg}：{to_traditional(res['observation']).rstrip('。；;')}")
    ai["regionObservations"] = obs

    try:
        t0 = time.time()
        g = parse_json_response(call_gemini(build_global_prompt(today, region_results, by_cid), api_key, tag="全域", timeout=120))
        ai.update({k: g.get(k) for k in ("globalTheme", "storylines", "suggestions") if g.get(k)})
        print(f"   ✓ [全域] 主線與選題完成（{time.time() - t0:.0f} 秒）")
    except Exception as e:
        print(f"   ⚠️ [全域] 分析失敗（{str(e)[:120]}），主線與選題改用預設內容")
    return ai


def parse_json_response(raw: str) -> dict:
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    return json.loads(s)


# -------------------------------------------------------------
# 無 AI 備援：免費翻譯端點（失敗則保留原文並標註）
# -------------------------------------------------------------
_translate_cache = {}

def translate_to_zh_tw(text: str) -> str:
    if not text:
        return text
    if not (has_foreign_script(text) or is_mostly_latin(text)):
        return to_traditional(text)
    if text in _translate_cache:
        return _translate_cache[text]
    url = ("https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=zh-TW&dt=t&q="
           + urllib.parse.quote(text[:500]))
    result = text
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=get_ssl_context(), timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        result = "".join(seg[0] for seg in data[0] if seg and seg[0]).strip() or text
    except Exception as e:
        print(f"   ⚠️ 翻譯失敗（保留原文）：{e}", file=sys.stderr)
    result = to_traditional(result)
    _translate_cache[text] = result
    return result


def clean_title(title: str) -> str:
    # 去掉「 - 媒體名」「 | 媒體名」尾巴
    t = re.sub(r"\s*[|｜]\s*[^|｜]{1,30}$", "", title).strip()
    t = re.sub(r"\s+[-–—]\s+[^-–—]{1,30}$", "", t).strip()
    return t or title


def fallback_event(c: dict, category: str, rank: int) -> dict:
    title = translate_to_zh_tw(clean_title(c["title"]))
    snippet = translate_to_zh_tw(c.get("snippet", "")) if c.get("snippet") else ""
    src = c.get("source") or "當地媒體"
    if snippet and len(snippet) >= 20:
        summary = snippet[:160]
    elif c.get("query"):
        summary = f"「{translate_to_zh_tw(c['query'])}」登上{c['region']}熱搜，{src}報導：{title}。"
    else:
        summary = f"{src}報導：{title}。"
    return {
        "region": c["region"], "category": category, "rank": rank,
        "title": title, "summary": summary,
        "sourceUrl": c["url"], "source": src, "originalTitle": c["title"],
        "brandRelevant": rank % 2 == 1,
    }


def pick_fallback_slots(cands: list, used: set) -> dict:
    """無 AI 時的分類規則：媒體 RSS（重大新聞）優先進【綜合】，Google 熱搜（社群話題）優先進【生活】"""
    free = [c for c in cands if c["cid"] not in used]
    media = [c for c in free if c["kind"] == "media"]
    trend = [c for c in free if c["kind"] == "trend"]
    slots = {"綜合": media[:5], "生活": trend[:5]}
    rest = [c for c in free if c not in slots["綜合"] and c not in slots["生活"]]
    for cat in ("綜合", "生活"):
        while len(slots[cat]) < 5 and rest:
            slots[cat].append(rest.pop(0))
    return slots


def placeholder_event(reg: str, category: str, rank: int) -> dict:
    """候選真的不夠時的誠實佔位（會列為品質警告）"""
    feed = MEDIA_FEEDS.get(reg, [("", "https://www.bbc.com/news")])[0][1]
    home = re.match(r"https?://[^/]+", feed).group(0)
    return {
        "region": reg, "category": category, "rank": rank,
        "title": f"{reg}今日{category}來源不足，本則暫缺",
        "summary": f"今日自動採集未能取得足夠的{reg}{category}類真實報導，此欄位暫時保留，請以其他則情報為準。",
        "sourceUrl": home, "placeholder": True, "brandRelevant": False,
    }


def static_analysis() -> dict:
    return {
        "storylines": [
            {
                "id": 1,
                "kind": "跨區線",
                "title": "全球生活成本抗禦與庶民消費理性轉向",
                "summary": "高通膨與物價壓力推動群眾普遍轉向精打細算、二手重製與平價餐飲，展現跨文化的自主適應力。",
                "items": [
                    "東亞都會青年聚焦超商暖食與平價小確幸避風港",
                    "歐美家庭在節慶採購上自發推動手作省錢方案",
                    "各大電商購物節摒棄套路、回歸剛需減法消費"
                ]
            },
            {
                "id": 2,
                "kind": "跨區線",
                "title": "大選與地緣波動下的群眾心理防禦機制",
                "summary": "在重大政治議程與地緣局勢牽動下，公眾心理呈現高度審慎與向內收攝，社群普遍渴望免於紛擾的穩定生活。",
                "items": [
                    "美選搖擺州民調緊咬促發數千萬人提前投票避險",
                    "歐洲公務部門對抗緊縮預算與基建維護問題持續發酵",
                    "中東各方積極重啟外交斡旋力求化解區域波動"
                ]
            },
            {
                "id": 3,
                "kind": "跨區線",
                "title": "演算法浪潮下青年世代的數位排毒與心靈降熵",
                "summary": "面對海量熱搜與資訊轟炸，年輕族群在東亞與歐美不約而同掀起寺廟寄宿、無手機咖啡館等降熵體驗。",
                "items": [
                    "韓國青年踴躍參與古剎冥想與無手機寄宿體驗",
                    "矽谷與西海岸流行無螢幕咖啡館與週末數位排毒",
                    "都會街頭透過幽默解構職場壓力成為集體共鳴"
                ]
            }
        ],
        "suggestions": [
            {
                "id": 1,
                "pillar": "金融一百零八講",
                "title": "數據繁榮與荷包體感：如何在總經分歧中建立一人公司的抗脆弱堡壘",
                "direction": "從宏觀經濟數據與個體通膨壓力的對比切入，剖析宏觀敘事如何遮蔽微觀體感，闡述小微個體如何透過減法思維與現金流護城河抵抗週期波動。",
                "brandRelevant": True
            },
            {
                "id": 2,
                "pillar": "俗人對話錄",
                "title": "熱搜數字的迷魂陣：我們是在閱讀時代，還是在被演算法消費？",
                "direction": "探討每日海量熱門關鍵字背後的注意力定價機制，分析群眾為何容易陷入情緒極化的陷阱，提供大道至簡的清醒觀察之道。",
                "brandRelevant": True
            },
            {
                "id": 3,
                "pillar": "佛法生活感悟文",
                "title": "無常波動下的安住之道：在資訊洪流中找回內在清涼",
                "direction": "結合全球地緣政治與日常壓力的集體焦慮，分享如何在喧囂萬變的外境中練習向內觀照、放下執念，安頓當下一念心。",
                "brandRelevant": False
            }
        ]
    }


def global_summary_from(ai: dict, events: list) -> str:
    """AI 有寫的區域用 AI 觀察，沒寫的區域用該區頭條組成，確保七區都有"""
    obs = {o.split("：", 1)[0]: o for o in (ai or {}).get("regionObservations", [])}
    fb = fallback_global_summary(events).rstrip("。").split("；")
    fb_map = {p.split("：", 1)[0]: p for p in fb}
    return "；".join(obs.get(reg) or fb_map.get(reg, f"{reg}：今日資料不足") for reg in REGIONS) + "。"


def fallback_global_summary(events: list) -> str:
    parts = []
    for reg in REGIONS:
        tops = [e["title"] for e in events if e["region"] == reg and e["rank"] == 1]
        parts.append(f"{reg}：" + ("、".join(t[:30] for t in tops) if tops else "今日資料不足"))
    return "；".join(parts) + "。"


# -------------------------------------------------------------
# 組裝：AI 結果 → 以 cid 對回真實網址；缺額由程式補齊
# -------------------------------------------------------------
def assemble(today: str, pools: dict, ai: dict = None) -> tuple:
    by_cid = {c["cid"]: c for reg in REGIONS for c in pools[reg]}
    notes = []
    events = []
    used = set()
    slots = {(reg, cat): [] for reg in REGIONS for cat in ("綜合", "生活")}
    outlet_count = {reg: {} for reg in REGIONS}

    if ai:
        for ev in ai.get("events", []):
            cid = str(ev.get("cid", "")).strip()
            c = by_cid.get(cid)
            cat = ev.get("category")
            if not c:
                notes.append(f"AI 給了不存在的 cid：{cid}，已忽略")
                continue
            if cid in used or cat not in ("綜合", "生活"):
                continue
            reg = c["region"]  # 以候選本身的區域為準，AI 不能跨區
            if len(slots[(reg, cat)]) >= 5:
                continue
            if outlet_count[reg].get(outlet_of(c), 0) >= MAX_PER_OUTLET:
                notes.append(f"{reg}：{outlet_of(c)} 已達 {MAX_PER_OUTLET} 則上限，略過 {cid}")
                continue
            outlet_count[reg][outlet_of(c)] = outlet_count[reg].get(outlet_of(c), 0) + 1
            title = (ev.get("title") or "").strip()
            summary = (ev.get("summary") or "").strip()
            if not title or has_foreign_script(title):
                title = translate_to_zh_tw(clean_title(c["title"]))
            slots[(reg, cat)].append({
                "region": reg, "category": cat, "rank": 0,
                "title": to_traditional(title), "summary": to_traditional(summary),
                "sourceUrl": c["url"], "source": c.get("source", ""), "originalTitle": c["title"],
                "brandRelevant": bool(ev.get("brandRelevant", False)),
                "_rank": ev.get("rank", 99), "_cid": cid,
            })
            used.add(cid)

    # 補齊缺額（AI 不足或沒有 AI）
    for reg in REGIONS:
        need = {cat: 5 - len(slots[(reg, cat)]) for cat in ("綜合", "生活")}
        if need["綜合"] > 0 or need["生活"] > 0:
            fb = pick_fallback_slots(pools[reg], used)
            for cat in ("綜合", "生活"):
                pool = fb[cat] + fb["綜合" if cat == "生活" else "生活"] + pools[reg]
                while need[cat] > 0:
                    # 先挑還沒達上限的媒體；真的不夠才放寬
                    c = next((x for x in pool if x["cid"] not in used
                              and outlet_count[reg].get(outlet_of(x), 0) < MAX_PER_OUTLET), None) \
                        or next((x for x in pool if x["cid"] not in used), None)
                    if not c:
                        break
                    outlet_count[reg][outlet_of(c)] = outlet_count[reg].get(outlet_of(c), 0) + 1
                    ev = fallback_event(c, cat, 0)
                    ev["_rank"], ev["_cid"] = 50 + len(slots[(reg, cat)]), c["cid"]
                    slots[(reg, cat)].append(ev)
                    used.add(c["cid"])
                    need[cat] -= 1
                while need[cat] > 0:
                    ev = placeholder_event(reg, cat, 0)
                    ev["_rank"], ev["_cid"] = 99, ""
                    slots[(reg, cat)].append(ev)
                    need[cat] -= 1
                    notes.append(f"{reg}{cat}候選不足，使用佔位")

    eid = 1000
    for reg in REGIONS:
        for cat in ("綜合", "生活"):
            lst = sorted(slots[(reg, cat)], key=lambda e: e.get("_rank", 99))
            for r, ev in enumerate(lst, start=1):
                ev["rank"] = r
                ev["id"] = eid
                eid += 1
                cid = ev.pop("_cid", "")
                ev.pop("_rank", None)
                c = by_cid.get(cid)
                if c and c.get("linkStatus") == "blocked":
                    ev["linkUnverified"] = True
                events.append(ev)

    static = static_analysis()
    data = {
        "date": today,
        "sourceModifiedAt": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec="seconds"),
        "followupNote": None,
        "globalTheme": (ai or {}).get("globalTheme") or "今日全球真實熱搜與主流報導速覽",
        "globalSummary": (ai or {}).get("globalSummary") or global_summary_from(ai, events),
        "events": events,
        "storylines": (ai or {}).get("storylines") or static["storylines"],
        "suggestions": (ai or {}).get("suggestions") or static["suggestions"],
        "generator": "gemini+sources" if ai else "sources-only",
        "aiRegions": (ai or {}).get("regionsByAI", []),
    }
    for idx, st in enumerate(data["storylines"], start=1):
        st.setdefault("id", idx)
        st.setdefault("kind", "跨區線")
    for idx, sg in enumerate(data["suggestions"], start=1):
        sg.setdefault("id", idx)
    # AI 若漏了某個立柱，用靜態選題補上，避免成為致命錯誤
    pillars = {s.get("pillar") for s in data["suggestions"]}
    for s in static["suggestions"]:
        if s["pillar"] not in pillars:
            data["suggestions"].append(dict(s, id=len(data["suggestions"]) + 1))
    if len(data["storylines"]) < 3:
        data["storylines"] = (data["storylines"] + static["storylines"])[:3]
    return data, notes


# -------------------------------------------------------------
# 主流程
# -------------------------------------------------------------
def main():
    today = get_today_str()
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        today = sys.argv[1]

    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports", "02_traffic", "daily")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{today}.json")

    print(f"📡 [1/3 真實來源] 採集 {today} 七區熱搜與主流媒體報導...")
    pools = collect_candidates()
    total = sum(len(v) for v in pools.values())
    if total == 0:
        print("🚨 所有新聞來源都無法讀取（網路中斷？），今日無法產生情報。", file=sys.stderr)
        sys.exit(1)

    ai = None
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if api_key:
        print(f"\n🤖 [2/3 AI 編輯] 七區同時交由 Gemini 從 {total} 則候選中挑選、翻譯與撰寫分析...")
        t0 = time.time()
        ai = run_ai_editors(today, pools, api_key)
        if ai:
            print(f"   ✓ AI 完成 {len(ai['regionsByAI'])}/7 區（共 {time.time() - t0:.0f} 秒）")
        else:
            print("   ⚠️ 七區 AI 編輯全部失敗，改用程式挑選＋自動翻譯")
    else:
        print("\nℹ️ 未設定 GEMINI_API_KEY，使用程式挑選＋自動翻譯")

    print("\n🧩 [3/3 組裝與審查] 以 cid 對回真實網址並補齊缺額...")
    data, notes = assemble(today, pools, ai)
    for n in notes:
        print(f"   ℹ️ {n}")

    fatal, quality = audit_standards(data)
    unverified = [e for e in data["events"] if e.get("linkUnverified")]
    if fatal:
        print(f"🚨 發現 {len(fatal)} 項致命錯誤，拒絕寫入：", file=sys.stderr)
        for err in fatal:
            print(f"   ❌ {err}", file=sys.stderr)
        sys.exit(1)

    if quality or unverified:
        data["qualityWarnings"] = quality + [
            f"[{e['region']} {e['category']} #{e['rank']}] 連結被網站阻擋、無法在 runner 上驗證：{e['sourceUrl']}"
            for e in unverified
        ]
        print(f"::warning::今日情報有 {len(data['qualityWarnings'])} 項品質提醒，已標註並照常發佈")
        for w in data["qualityWarnings"]:
            print(f"   ⚠️ {w}")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 已儲存 {output_file}（70 則，產生方式：{data['generator']}，品質提醒 {len(data.get('qualityWarnings', []))} 項）")


if __name__ == "__main__":
    main()
