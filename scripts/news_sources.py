#!/usr/bin/env python3
"""
scripts/news_sources.py
真實新聞候選池採集器（Source-First 架構的第一層）

原則：網址只來自「真實的新聞來源 RSS」，絕不由 AI 產生。
- Google Trends 每日熱搜 RSS：每則熱搜附帶 1~3 篇真實報導（news_item），代表「社群流量」
- 各區主流媒體 RSS：補足「綜合」類重大新聞與 Trends 無法覆蓋的區域（如中國）

輸出：每區一份候選清單，每則候選包含 cid、原文標題、來源、摘要片段、網址、熱度、發布時間、連結狀態。
"""

import re
import ssl
import sys
import html
import datetime
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor

from validate_traffic_urls import REGIONS, check_url_status

TRENDS_NS = "{https://trends.google.com/trending/rss}"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# Google Trends 地區代碼（中國無 Trends，改以香港熱搜＋中文媒體 RSS 補足）
TRENDS_GEOS = {
    "台灣": ["TW"],
    "中國": ["HK"],
    "日本": ["JP"],
    "韓國": ["KR"],
    "美國": ["US"],
    "歐洲": ["GB", "DE", "FR"],
    "中東": ["SA", "AE", "EG"],
}

# 各區主流媒體 RSS（任何一個失效都會被略過，不影響整體）
MEDIA_FEEDS = {
    "台灣": [
        ("自由時報", "https://news.ltn.com.tw/rss/all.xml"),
        ("ETtoday", "https://feeds.feedburner.com/ettoday/realtime"),
    ],
    "中國": [
        ("中新網 國內", "https://www.chinanews.com.cn/rss/china.xml"),
        ("中新網 社會", "https://www.chinanews.com.cn/rss/society.xml"),
        ("中新網 財經", "https://www.chinanews.com.cn/rss/finance.xml"),
        ("SCMP China", "https://www.scmp.com/rss/4/feed"),
        # 綜合型來源：只保留與中國相關的報導
        ("中新網", "https://www.chinanews.com.cn/rss/scroll-news.xml", "china"),
        ("BBC 中文", "https://feeds.bbci.co.uk/zhongwen/trad/rss.xml", "china"),
    ],
    "日本": [
        ("朝日新聞", "https://www.asahi.com/rss/asahi/newsheadlines.rdf"),
        ("毎日新聞", "https://mainichi.jp/rss/etc/mainichi-flash.rss"),
        ("Kyodo", "https://english.kyodonews.net/rss/news.xml"),
        ("Japan Times", "https://www.japantimes.co.jp/feed/"),
    ],
    "韓國": [
        ("Yonhap", "https://en.yna.co.kr/RSS/news.xml"),
        ("聯合新聞", "https://www.yna.co.kr/rss/news.xml"),
    ],
    "美國": [
        ("NPR", "https://feeds.npr.org/1001/rss.xml"),
        ("NYT US", "https://rss.nytimes.com/services/xml/rss/nyt/US.xml"),
    ],
    "歐洲": [
        ("BBC Europe", "https://feeds.bbci.co.uk/news/world/europe/rss.xml"),
        ("Guardian Europe", "https://www.theguardian.com/world/europe-news/rss"),
        ("DW", "https://rss.dw.com/rdf/rss-en-all"),
    ],
    "中東": [
        ("BBC Middle East", "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml"),
        ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ],
}

REGION_CODE = {"台灣": "TW", "中國": "CN", "日本": "JP", "韓國": "KR", "美國": "US", "歐洲": "EU", "中東": "ME"}

# 綜合型來源的區域關鍵字過濾（標題或摘要須命中其一）
REGION_KEYWORDS = {
    "china": re.compile(
        r"中國|中国|大陸|大陆|內地|内地|北京|上海|廣州|广州|深圳|重慶|重庆|成都|武漢|武汉|杭州|天津|南京|西安|"
        r"香港|澳門|澳门|新疆|西藏|國務院|国务院|中共|習近平|习近平|李強|李强|人民幣|人民币|央行|發改委|发改委|"
        r"China|Chinese|Beijing|Shanghai|Hong Kong|Xi Jinping|Shenzhen|Guangdong|yuan",
        re.I),
}

MAX_AGE_HOURS = 48          # 超過 48 小時的報導視為舊聞，直接剔除
MAX_TRENDS_PER_REGION = 20
MAX_MEDIA_PER_REGION = 15


def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _fetch_xml(url: str, timeout: int = 12):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, context=_ssl_ctx(), timeout=timeout) as resp:
        return ET.fromstring(resp.read())


def _clean_text(s: str, limit: int = 300) -> str:
    if not s:
        return ""
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


def _parse_date(s: str):
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s.strip())
    except Exception:
        try:
            dt = datetime.datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def _is_fresh(dt, now) -> bool:
    return dt is None or (now - dt) <= datetime.timedelta(hours=MAX_AGE_HOURS)


def _parse_traffic(s: str) -> int:
    """'200,000+' / '2萬+' → 整數，用於熱度排序"""
    if not s:
        return 0
    s = s.replace(",", "").replace("+", "").strip()
    mult = 1
    if s.endswith("萬"):
        mult, s = 10000, s[:-1]
    elif s.upper().endswith("K"):
        mult, s = 1000, s[:-1]
    elif s.upper().endswith("M"):
        mult, s = 1000000, s[:-1]
    try:
        return int(float(s) * mult)
    except ValueError:
        return 0


def _is_bad_url(url: str) -> bool:
    u = url.lower()
    if not u.startswith(("http://", "https://")):
        return True
    if re.search(r"(google|bing|yahoo)\.[a-z.]+/search", u) or "news.google.com" in u:
        return True
    return False


def collect_trends(region: str, now) -> list:
    out = []
    for geo in TRENDS_GEOS.get(region, []):
        try:
            tree = _fetch_xml(f"https://trends.google.com/trending/rss?geo={geo}")
        except Exception as e:
            print(f"   ⚠️ Trends {geo} 讀取失敗：{e}")
            continue
        for it in tree.findall(".//item"):
            query = _clean_text(it.findtext("title", ""), 80)
            traffic = _parse_traffic(it.findtext(f"{TRENDS_NS}approx_traffic", ""))
            pub = _parse_date(it.findtext("pubDate", ""))
            if not _is_fresh(pub, now):
                continue
            for ni in it.findall(f"{TRENDS_NS}news_item"):
                url = (ni.findtext(f"{TRENDS_NS}news_item_url", "") or "").strip()
                title = _clean_text(ni.findtext(f"{TRENDS_NS}news_item_title", ""), 200)
                if not url or not title or _is_bad_url(url):
                    continue
                out.append({
                    "kind": "trend",
                    "query": query,
                    "title": title,
                    "snippet": _clean_text(ni.findtext(f"{TRENDS_NS}news_item_snippet", ""), 300),
                    "source": _clean_text(ni.findtext(f"{TRENDS_NS}news_item_source", ""), 60),
                    "url": url,
                    "traffic": traffic,
                    "published": pub.isoformat() if pub else "",
                    "geo": geo,
                })
                break  # 每則熱搜只取第一篇報導，避免同一話題佔滿名額
    out.sort(key=lambda x: -x["traffic"])
    return out[:MAX_TRENDS_PER_REGION]


def collect_media(region: str, now) -> list:
    out = []
    for entry in MEDIA_FEEDS.get(region, []):
        source, feed = entry[0], entry[1]
        kw = REGION_KEYWORDS.get(entry[2]) if len(entry) > 2 else None
        try:
            tree = _fetch_xml(feed)
        except Exception as e:
            print(f"   ⚠️ {source} RSS 讀取失敗：{e}")
            continue
        items = tree.findall(".//item") or tree.findall(".//{http://www.w3.org/2005/Atom}entry")
        if not items:  # RDF (DW)
            items = tree.findall(".//{http://purl.org/rss/1.0/}item")
        count = 0
        for it in items:
            def t(tag):
                for cand in (tag, f"{{http://purl.org/rss/1.0/}}{tag}", f"{{http://www.w3.org/2005/Atom}}{tag}"):
                    v = it.findtext(cand)
                    if v:
                        return v
                return ""
            url = t("link").strip()
            if not url:
                link_el = it.find("{http://www.w3.org/2005/Atom}link")
                url = (link_el.get("href", "") if link_el is not None else "").strip()
            title = _clean_text(t("title"), 200)
            pub = _parse_date(t("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date", "") or t("updated"))
            if not url or not title or _is_bad_url(url) or not _is_fresh(pub, now):
                continue
            snippet = _clean_text(t("description") or t("summary"), 300)
            if kw and not kw.search(title + " " + snippet):
                continue
            out.append({
                "kind": "media",
                "query": "",
                "title": title,
                "snippet": snippet,
                "source": source,
                "url": url,
                "traffic": 0,
                "published": pub.isoformat() if pub else "",
                "geo": "",
            })
            count += 1
            if count >= 8:  # 每個媒體最多 8 則，維持來源多樣性
                break
        print(f"      · {source}：{count} 則")
    return out[:MAX_MEDIA_PER_REGION]


def verify_candidates(cands: list, max_workers: int = 16) -> None:
    """就地標註每則候選的連結狀態：ok / blocked（網站擋機房 IP）/ dead（真的失效）"""
    def _w(c):
        status, msg = check_url_status(c["url"], timeout=8, max_attempts=2)
        return status, msg
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for c, (status, msg) in zip(cands, ex.map(_w, cands)):
            c["linkStatus"] = status
            c["linkMsg"] = msg


def collect_candidates(now=None, verify: bool = True) -> dict:
    """回傳 {region: [candidate, ...]}，已去重、剔除舊聞與失效連結"""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    pools = {}
    for reg in REGIONS:
        trends = collect_trends(reg, now)
        media = collect_media(reg, now)
        seen = set()
        merged = []
        # 交錯排列：熱搜（社群流量）與媒體（重大新聞）各半，讓 AI 有均衡的選擇
        for i in range(max(len(trends), len(media))):
            for src in (trends, media):
                if i < len(src):
                    key = re.sub(r"[?#].*$", "", src[i]["url"]).rstrip("/")
                    if key not in seen:
                        seen.add(key)
                        merged.append(src[i])
        pools[reg] = merged
        print(f"   📥 {reg}：熱搜 {len(trends)} 則、媒體 {len(media)} 則 → 候選 {len(merged)} 則")

    if verify:
        all_c = [c for reg in REGIONS for c in pools[reg]]
        print(f"   🔗 驗證 {len(all_c)} 則候選連結...")
        verify_candidates(all_c)

    for reg in REGIONS:
        alive = [c for c in pools[reg] if c.get("linkStatus", "ok") != "dead"]
        dead = len(pools[reg]) - len(alive)
        # 連得上的優先，被擋（但來源真實）的排後
        alive.sort(key=lambda c: 0 if c.get("linkStatus", "ok") == "ok" else 1)
        for i, c in enumerate(alive, start=1):
            c["cid"] = f"{REGION_CODE[reg]}-{i:02d}"
            c["region"] = reg
        pools[reg] = alive
        if dead:
            print(f"   🗑️ {reg}：剔除 {dead} 則失效連結，剩 {len(alive)} 則")
    return pools


if __name__ == "__main__":
    import json
    p = collect_candidates(verify="--no-verify" not in sys.argv)
    print(json.dumps({k: v[:3] for k, v in p.items()}, ensure_ascii=False, indent=2))
