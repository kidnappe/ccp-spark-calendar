#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""detail_server.py —— 史料详情丰富工具 · 本地服务（端口 8001）
静态托管项目目录 + API：
  GET  /api/events    事件列表（events.json 精简字段）
  GET  /api/models    Ollama 可用模型
  POST /api/fetch     抓百度百科正文 {title}
  POST /api/generate  调 Ollama 生成 6 子块 {event, text, url, model}
  POST /api/apply     把成功详情写回 events.json（自动备份） {items:[{key,detail,...}]}
启动：双击 tools/start_detail_gui.bat，或 python tools/detail_server.py
"""
import json
import base64
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler

PORT = 8001
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP_DIR = os.path.join(ROOT, "backups")
# 构建任务状态（POST /api/build 启动 build_data.py 重建 index.html，GET /api/build/status 轮询进度）
BUILD = {"proc": None, "start": 0, "log": "", "done": False, "code": None}


def snapshot(kind):
    """写入 events.json 前的统一备份：events.json + causality.json 复制到 backups/（带类型与时间戳）。"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    saved = []
    for name in ("events.json", "causality.json"):
        src = os.path.join(ROOT, name)
        if os.path.exists(src):
            dst = os.path.join(BACKUP_DIR, f"{name}.bak-{kind}-{ts}")
            shutil.copy2(src, dst)
            saved.append(os.path.basename(dst))
    return saved
OLLAMA = "http://127.0.0.1:11434"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ccp-spark-calendar/1.0"}


def send_json(h, obj, code=200):
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    h.send_response(code)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(data)))
    h.end_headers()
    h.wfile.write(data)


def wiki_search(title, limit=5):
    """维基百科 opensearch：按标题搜词条，返回词条名列表（可能含会址/纪念馆等噪音）"""
    q = urllib.parse.urlencode({"action": "opensearch", "search": title, "limit": limit, "format": "json"})
    try:
        req = urllib.request.Request("https://zh.wikipedia.org/w/api.php?" + q, headers=UA)
        with urllib.request.urlopen(req, timeout=12) as r:
            d = json.loads(r.read().decode("utf-8"))
        return d[1] or []
    except Exception:
        return []


def wiki_extract(page):
    """维基百科 extract API：抓词条引言正文（去格式），返回前 4000 字"""
    q = urllib.parse.urlencode({
        "action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1,
        "titles": page, "format": "json", "origin": "*", "redirects": 1})
    try:
        req = urllib.request.Request("https://zh.wikipedia.org/w/api.php?" + q, headers=UA)
        with urllib.request.urlopen(req, timeout=12) as r:
            d = json.loads(r.read().decode("utf-8"))
        for p in d["query"]["pages"].values():
            ex = p.get("extract")
            if ex:
                return ex[:4000]
    except Exception:
        pass
    return None


BAD_TERM = re.compile(r"会址|纪念馆|旧址|遗址|故居|名单|宿舍")


def wiki_search_full(text, limit=5):
    """维基百科全文检索 search API：返回结果标题列表（比 opensearch 覆盖面广）"""
    q = urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": text,
                                "srlimit": limit, "format": "json"})
    try:
        req = urllib.request.Request("https://zh.wikipedia.org/w/api.php?" + q, headers=UA)
        with urllib.request.urlopen(req, timeout=12) as r:
            d = json.loads(r.read().decode("utf-8"))
        return [s["title"] for s in d.get("query", {}).get("search", [])]
    except Exception:
        return []


def candidate_pages(title):
    seen, out = set(), []
    # 强制把同名标题放第一位：维基对多数同名事件有词条，不依赖搜索命中
    if title:
        seen.add(title)
        out.append(title)
    for c in [title, title + " 会议", title + " 事件"]:
        for p in wiki_search(c) + wiki_search_full(c):
            if p and p not in seen:
                seen.add(p)
                out.append(p)
    return out


def fetch_source(event):
    """为事件抓取公开史料文本。取源优先级：
    ① 共产党员网官方站内搜索（rank-0，命中即官方）
    ② Bing site: 官方域桥接（共产党员网未命中时兜底官方源）
    ③ 维基百科（同名词条优先）
    ④ 360/搜狗 web_fallback
    全部失败返回 (None,None)。"""
    title = re.sub(r"^(第|中共|新中国|庆祝)?\d{4}年", "", event["title"]).strip()
    # ① 共产党员网官方搜索
    t, u = party_search(title)
    if t:
        return t, u
    # ② Bing site: 官方域桥接
    t, u = bing_official_search(title)
    if t:
        return t, u
    # ③ 维基百科（同名词条优先）
    fallback = None
    pages = candidate_pages(title)
    pages.sort(key=lambda p: 0 if p == title else 1)
    for page in pages:
        txt = wiki_extract(page)
        if not txt or len(txt) <= 120:
            continue
        u = "https://zh.wikipedia.org/wiki/" + urllib.parse.quote(page)
        if page != title and BAD_TERM.search(page):
            if not fallback:
                fallback = (txt[:4000], u)
            continue
        return txt[:4000], u
    if fallback:
        return fallback
    # ④ 360/搜狗兜底
    return web_fallback(title)


def _html_text(seg):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", seg or "")).strip()


def sogou_search(word, limit=6):
    """搜狗网页搜索：返回 [(url, title, 摘要)]；跳转链接跟随到真实 URL"""
    out = []
    try:
        req = urllib.request.Request(
            "https://www.sogou.com/web?query=" + urllib.parse.quote(word), headers=UA)
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", "ignore")
        for b in re.findall(r'<div class="vrwrap"[\s\S]*?</div>\s*</div>\s*</div>', html)[:limit]:
            tm = re.search(r'<h3[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>', b)
            if not tm:
                continue
            u = tm.group(1)
            t = _html_text(tm.group(2))
            cm = re.search(r'(?:str_info|text-layout|fz-mid)[^>]*>([\s\S]*?)</(?:div|p)>', b)
            txt = _html_text(cm.group(1)) if cm else ""
            if len(txt) < 50:
                continue
            # 跟随搜狗跳转链接（/link?url=…）拿真实 URL
            if u.startswith("/link?"):
                try:
                    jr = urllib.request.Request("https://www.sogou.com" + u, headers=UA)
                    with urllib.request.urlopen(jr, timeout=10) as j:
                        u = j.geturl()
                except Exception:
                    u = ""
            if u:
                out.append((u, t, txt))
    except Exception:
        pass
    return out


def so360_search(word, limit=6):
    """360 搜索：返回 [(url, title, 摘要)]"""
    out = []
    try:
        req = urllib.request.Request(
            "https://www.so.com/s?q=" + urllib.parse.quote(word), headers=UA)
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", "ignore")
        for b in re.findall(r'<li class="res-list"[\s\S]*?</li>', html)[:limit]:
            tm = re.search(r'<h3[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>', b)
            if not tm:
                continue
            u = tm.group(1)
            t = _html_text(tm.group(2))
            cm = re.search(r'<p class="res-desc"[\s\S]*?>([\s\S]*?)</p>', b)
            txt = _html_text(cm.group(1)) if cm else ""
            if len(txt) >= 50:
                out.append((u, t, txt))
    except Exception:
        pass
    return out


# 官方党史/政府站域名（按优先级分层）
# 第一优先：官方党史专门站点（人民网党史、共产党员网、中央党史和文献研究院、军网、求是等）
PARTY_OFFICIAL = re.compile(
    r"dangshi\.people\.com\.cn|cpc\.people\.com\.cn|12371\.cn|dswxyjy\.org\.cn|"
    r"81\.cn|qstheory\.cn|gov\.cn|xinhuanet\.com|guangming\.com|"
    r"xuexi\.cn|gqt\.org\.cn|cnr\.cn|cctv\.com|news\.cn|people\.com\.cn")
# 第二优先：其他百科
BAIKE = re.compile(r"baike\.sogou|baike\.so\.com|baike\.baidu|baike\.com|zhihu|weixin")


def _rank(result):
    u = result[0]
    if PARTY_OFFICIAL.search(u):
        return 0
    if BAIKE.search(u):
        return 1
    return 2


def web_fallback(title, limit=4):
    """多引擎搜索兜底：合并前几条权威摘要（官方党史站优先，其次百科），返回 (text, url)
    引擎顺序：360（稳定）→ 搜狗（命中率高但易限流，作补充）"""
    results = []
    for fn in (so360_search, sogou_search):
        for r in fn(title):
            if r not in results:
                results.append(r)
        if len(results) >= 4:
            break
    results.sort(key=_rank)
    seen, parts, url = set(), [], None
    core = re.sub(r"^(第|中共|新中国|庆祝|党的|全国|中央)\d*[次届中]*", "", title).strip()
    for u, t, txt in results:
        # 摘要或标题须包含核心关键词；过滤明显无关的条目
        if core and core not in txt and core not in t:
            continue
        if BAD_TERM.search(txt):
            continue
        if u in seen or not u.startswith("http"):
            continue
        seen.add(u)
        # 首选 URL：官方党史站优先（url 尚未取自官方站时，官方站结果优先）
        if url is None or (PARTY_OFFICIAL.search(u) and not PARTY_OFFICIAL.search(url)):
            url = u
        parts.append(txt)
        if len(parts) >= 3:
            break
    if not parts:
        return None, None
    return "；".join(parts)[:4000], url or ""


def core_term(title):
    """提取事件标题的核心专名（去前缀），用于相关性判重"""
    return re.sub(r"^(第|中共|新中国|庆祝|党的|全国|中央)\d*[次届中]*", "", title or "").strip()


def party_search(title):
    """共产党员网官方站内搜索（服务端渲染 GET）。返回 (text,url)；无相关结果返回 (None,None)。"""
    q = urllib.parse.quote(title)
    url = "https://search.12371.cn/search.php?t=newsmerge&client=no&q=" + q
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", "ignore")
    except Exception:
        return None, None
    cand = []
    for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.S):
        href, atxt = m.group(1), _html_text(m.group(2))
        if not href or "search.php" in href or href.startswith("#") or "javascript:" in href:
            continue
        if len(atxt) < 4:
            continue  # 过滤「首页/更多/登录」等短导航文字
        if href.startswith("/"):
            href = "https://www.12371.cn" + href
        if "12371.cn" not in href:
            continue
        after = _html_text(html[m.end():m.end() + 500])
        cand.append((href, atxt, atxt + " " + after))
    if not cand:
        return None, None
    core = core_term(title)
    best = None
    if core and len(core) >= 4:
        for c in cand:
            if core in c[1]:
                best = c; break
        if not best:
            for c in cand:
                if core in c[2]:
                    best = c; break
    if not best:
        best = cand[0]
    href = best[0]
    try:
        req = urllib.request.Request(href, headers=UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            art = r.read().decode("utf-8", "ignore")
        paras = re.findall(r'<p[^>]*>(.*?)</p>', art, re.S)
        text = _html_text(" ".join(paras))
        if len(text) < 150:
            body = re.sub(r'<script.*?</script>|<style.*?</style>', '', art)
            text = _html_text(body)
        if len(text) < 150:
            return None, None
        return text[:4000], href
    except Exception:
        return None, None


def _decode_bing_u(u):
    """解码 Bing 结果跳转链接的 cloaking `u` 参数，取出裸 URL"""
    try:
        s = u.replace("-", "+").replace("_", "/")
        s += "=" * (-len(s) % 4)
        raw = base64.b64decode(s)
        i = raw.find(b"http")
        if i < 0:
            return None
        url = raw[i:].decode("utf-8", "ignore")
        m = re.match(r"https?://[^\s\"'<>]+", url)
        return m.group(0) if m else None
    except Exception:
        return None


BING_OFFICIAL_DOMAINS = ["gov.cn", "cpc.people.com.cn", "people.com.cn",
                         "news.cn", "xinhuanet.com", "qstheory.cn",
                         "dswxyjy.org.cn", "81.cn"]


def bing_official_search(title):
    """Bing `site:` 桥接官方域（兜底共产党员网）。返回 (text,url)；无命中返回 (None,None)。"""
    core = core_term(title)
    for dom in BING_OFFICIAL_DOMAINS:
        q = urllib.parse.quote("site:%s %s" % (dom, title))
        try:
            req = urllib.request.Request("https://www.bing.com/search?q=" + q, headers=UA)
            with urllib.request.urlopen(req, timeout=15) as r:
                html = r.read().decode("utf-8", "ignore")
        except Exception:
            continue
        for m in re.finditer(r'<h2[^>]*>.*?<a[^>]+href=["\']([^"\']+)["\']', html, re.S):
            href = m.group(1)
            real = None
            if "bing.com/ck/a" in href:
                um = re.search(r"[?&]u=([^&\"']+)", href)
                if um:
                    real = _decode_bing_u(urllib.parse.unquote(um.group(1)))
            elif href.startswith("http"):
                real = href
            if not real or not PARTY_OFFICIAL.search(real):
                continue
            near = _html_text(html[m.start():m.start() + 1200])
            if core and len(core) >= 4 and core not in near:
                continue
            try:
                req = urllib.request.Request(real, headers=UA)
                with urllib.request.urlopen(req, timeout=20) as rr:
                    art = rr.read().decode("utf-8", "ignore")
                paras = re.findall(r'<p[^>]*>(.*?)</p>', art, re.S)
                text = _html_text(" ".join(paras)) or _html_text(
                    re.sub(r'<script.*?</script>|<style.*?</style>', '', art))
                if len(text) >= 150:
                    return text[:4000], real
            except Exception:
                continue
    return None, None


def ollama_tags():
    req = urllib.request.Request(OLLAMA + "/api/tags")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode("utf-8")).get("models", [])


def ollama_generate(payload):
    req = urllib.request.Request(OLLAMA + "/api/generate",
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8"))


def parse_json(text):
    if not text:
        raise ValueError("模型返回为空")
    try:
        return json.loads(text)
    except Exception:
        s, e = text.find("{"), text.rfind("}")
        if s < 0 or e < 0:
            raise ValueError("模型返回非 JSON")
        return json.loads(text[s:e + 1])


def _site_label(url):
    """根据 URL 判断来源站点前缀（与 ocr_server 同步）"""
    if not url:
        return ""
    if "wikipedia.org" in url:
        return "维基百科"
    if PARTY_OFFICIAL.search(url):
        for k, v in [("dangshi.people.com.cn", "人民网·党史频道"),
                     ("cpc.people.com.cn", "中国共产党新闻网"),
                     ("12371.cn", "共产党员网"),
                     ("dswxyjy.org.cn", "中央党史和文献研究院"),
                     ("81.cn", "中国军网"),
                     ("qstheory.cn", "求是网"),
                     ("xinhuanet.com", "新华网"),
                     ("guangming.com", "光明网"),
                     ("gov.cn", "政府网"),
                     ("xuexi.cn", "学习强国"),
                     ("gqt.org.cn", "中国共青团网"),
                     ("cnr.cn", "央广网"),
                     ("cctv.com", "央视网"),
                     ("news.cn", "新华网"),
                     ("people.com.cn", "人民网")]:
            if k in url:
                return v
        return "官方党史网站"
    if "sogou.com" in url:
        return "搜狗"
    if "so.com" in url:
        return "360"
    return "网络资料"


SYSTEM = ("你是中共党史史料整理员。任务：根据【参考资料摘录】整理事件的史料详情。"
          "规则：1) 只依据摘录，不得编造或补充摘录之外的史实；"
          "2) bg（背景）与 significance（历史意义）必须填写，各 80-150 字，根据摘录概括；"
          "3) quotes 若摘录含原文引文则填 1-3 条，无则空数组；"
          "4) figures 填摘录中出现的相关人物（2-5 人），无则空数组；"
          "5) srcCite 注明资料出处（填参考资料的实际来源页面，如『共产党员网』『维基百科』等具体来源，不要填泛化的媒体名）；"
          "6) furtherReading 给延伸阅读标题与链接；"
          "7) 输出严格 JSON，不要任何解释文字。")


def build_prompt(event, text, url):
    return (
        f"事件：{event.get('title', '')}（{event.get('year')}年{event.get('month')}月{event.get('day')}日）\n"
        f"参考资料摘录（来源 {_site_label(url)} {url}）：\n---BEGIN---\n{text}\n---END---\n\n"
        '输出格式：{"bg":"背景(80-150字)","significance":"历史意义(80-150字)",'
        '"quotes":["重要论述(1-3条,无则[])"],"figures":["相关人物(2-5人,无则[])"],'
        '"srcCite":["文献出处(1-2条,注明具体来源页面)"],"furtherReading":[{"title":"标题","url":"链接"}]}'
    )


# ==================== OCR 清洗 /api/fill（原 ocr_server.py 并入，统一为一个工具服务） ====================
FILL_SYSTEM = ("你是中共党史资料编写员。任务：根据【参考资料摘录】为事件补写 ocrDesc 字段。"
               "规则：1) 只依据摘录撰写，不得编造摘录之外的事实；"
               "2) 摘录不足时 filled 留空且 flagged=true；"
               "3) 正文写 100-250 字即可（参考：现有条目中位约 110 字、上限约 350 字），"
               "客观书面语，包含时间、背景、经过、结果、意义，正文不含『据…来源…』标注；"
               "4) 摘录可能很长，只需概括关键事实，禁止大段照抄摘录原文；"
               "5) source 字段填参考资料的实际来源页面名称（例如『宣统帝退位』『洛川会议』），"
               "不要填人民网/新华网等媒体名，只填实际抓到的那个页面/词条名；"
               "6) 输出严格 JSON，不要任何解释文字。")


def fill_prompt(event, text, url):
    # 摘录只取前 1200 字——正文要求 100-250 字，长摘录会诱导模型照抄
    text = (text or "").strip()[:1200]
    return (
        f"事件：{event.get('title', '')}（{event.get('year')}年{event.get('month')}月{event.get('day')}日）\n"
        f"参考资料摘录（来源 {url}）：\n---BEGIN---\n{text}\n---END---\n\n"
        '输出格式：{"items":[{"index":0,"filled":"撰写文本(100-250字)","source":"来源词条名","note":"说明","flagged":false}]}'
    )


def page_name_of(url):
    """从维基 URL 提取词条名（解码、下划线还原空格）"""
    if not url:
        return ""
    name = url.rstrip("/").rsplit("/", 1)[-1]
    try:
        name = urllib.parse.unquote(name).replace("_", " ")
    except Exception:
        pass
    return name


def do_fill(ev, model):
    """OCR 联网补写 ocrDesc：抓维基/官方源 → 本地模型撰写。返回 dict"""
    text, url = fetch_source(ev)
    if not text:
        return {"ok": False, "error": "未抓到参考资料（维基及搜索兜底均无对应内容）"}
    payload = {
        "model": model, "system": FILL_SYSTEM,
        "prompt": fill_prompt(ev, text, url),
        "format": "json", "stream": False,
        "options": {"num_ctx": 4096, "num_predict": 1000},
    }
    d = ollama_generate(payload)
    obj = parse_json(d.get("response", ""))
    items = obj.get("items") or [obj]
    it = items[0] or {}
    source = (it.get("source") or "").strip() or page_name_of(url)
    src_cite = f"{_site_label(url)}《{source}》（{url}）"
    return {"ok": True,
            "filled": it.get("filled", ""), "source": src_cite,
            "note": it.get("note", ""), "flagged": bool(it.get("flagged")),
            "url": url, "page": source, "text": text[:300]}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        p = self.path
        if p.startswith("/api/events"):
            try:
                d = json.load(open(os.path.join(ROOT, "events.json"), encoding="utf-8"))
                SUB = ("bg", "significance", "quotes", "figures", "srcCite", "furtherReading")
                items = []
                for e in d["events"]:
                    enriched = bool(e.get("bg") or e.get("significance"))
                    it = {
                        "key": e.get("key") or f"{e['year']}-{e['month']}-{e['day']}",
                        "year": e["year"], "month": e["month"], "day": e["day"],
                        "title": e["title"], "desc": e.get("desc", ""), "cat": e.get("cat", ""),
                        "enriched": enriched,
                        "official": bool(e.get("detailVerified")),
                    }
                    if enriched:
                        for sub in SUB:
                            if e.get(sub):
                                it[sub] = e[sub]
                        ds = e.get("detailSource") or {}
                        it["detailSource"] = ds.get("url") or ""
                        it["site"] = ds.get("site") or ""
                    items.append(it)
                send_json(self, {"ok": True, "total": len(items), "items": items})
            except Exception as ex:
                send_json(self, {"ok": False, "error": str(ex)})
        elif p.startswith("/api/models"):
            try:
                names = [m.get("name", "") for m in ollama_tags()]
                send_json(self, {"ok": True, "models": names})
            except Exception as ex:
                send_json(self, {"ok": False, "error": str(ex)})
        elif p.startswith("/api/build/status"):
            send_json(self, build_status())
        else:
            super().do_GET()

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
            body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception:
            body = {}
        if self.path == "/api/build":
            try:
                started = start_build()
                send_json(self, {"ok": started, "running": not started,
                                 "msg": "构建已启动" if started else "已有构建正在运行"})
            except Exception as ex:
                send_json(self, {"ok": False, "error": str(ex)})
        elif self.path == "/api/fill":
            try:
                ev = body.get("event") or {}
                model = body.get("model") or "qwen2.5:local7b"
                send_json(self, do_fill(ev, model))
            except Exception as ex:
                send_json(self, {"ok": False, "error": str(ex)})
        elif self.path == "/api/fetch":
            ev = {"title": body.get("title") or "", "year": body.get("year"),
                  "month": body.get("month"), "day": body.get("day")}
            text, url = fetch_source(ev)
            send_json(self, {"ok": bool(text), "text": text, "url": url,
                             "site": _site_label(url),
                             "official": bool(url) and bool(PARTY_OFFICIAL.search(url))})
        elif self.path == "/api/generate":
            try:
                ev = body.get("event") or {}
                text = body.get("text", "") or ""
                url = body.get("url", "") or ""
                if not text:
                    raise ValueError("缺少抓取文本")
                payload = {
                    "model": body.get("model") or "qwen2.5:local7b",
                    "system": SYSTEM, "prompt": build_prompt(ev, text, url),
                    "format": "json", "stream": False,
                    "options": {"num_ctx": 4096, "num_predict": 1600},
                }
                d = ollama_generate(payload)
                detail = parse_json(d.get("response", ""))
                send_json(self, {"ok": True, "detail": detail, "raw": d.get("response", "")})
            except Exception as ex:
                send_json(self, {"ok": False, "error": str(ex)})
        elif self.path == "/api/apply":
            try:
                d = api_apply(body)
                send_json(self, d)
            except Exception as ex:
                send_json(self, {"ok": False, "error": str(ex)})
        else:
            send_json(self, {"ok": False, "error": "unknown api"}, 404)


def api_apply(body):
    """把丰富工具生成的 6 子块写回 events.json（扁平写入顶层字段，与 build_data.py 期望一致）。
    入库前自动备份 events.json。返回 {ok, applied, skipped, backup}。"""
    items = body.get("items") or []
    if not isinstance(items, list):
        return {"ok": False, "error": "items 须为数组"}
    path = os.path.join(ROOT, "events.json")
    try:
        data = json.load(open(path, encoding="utf-8"))
    except Exception as ex:
        return {"ok": False, "error": "读取 events.json 失败：" + str(ex)}
    evs = data.get("events", [])
    by_key = {}
    for e in evs:
        k = e.get("key") or f"{e['year']}-{e['month']}-{e['day']}"
        by_key[k] = e
    SUB = ("bg", "significance", "quotes", "figures", "srcCite", "furtherReading")
    applied, skipped, seen = 0, 0, set()
    for it in items:
        k = it.get("key")
        d = it.get("detail") or {}
        if not k or k in seen:
            skipped += 1; continue
        e = by_key.get(k)
        if not e:
            skipped += 1; continue
        for sub in SUB:
            if sub in d and d[sub] not in (None, "", [], {}):
                e[sub] = d[sub]
        e["detailSource"] = {"url": it.get("source_url") or "", "site": it.get("site") or ""}
        e["detailVerified"] = bool(it.get("official"))
        seen.add(k); applied += 1
    saved = snapshot("apply")
    backup = saved[0] if saved else ""
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return {"ok": True, "applied": applied, "skipped": skipped, "backup": os.path.basename(backup)}


# ==================== 构建 API：POST /api/build 启动、GET /api/build/status 轮询 ====================
def start_build():
    """后台启动 build_data.py 重建 index.html；已在运行时返回 False。"""
    global BUILD
    p = BUILD["proc"]
    if p is not None and p.poll() is None:
        return False
    log = os.path.join(ROOT, "_build_runtime.log")
    try:
        logf = open(log, "w", encoding="utf-8")
    except OSError as ex:
        return False
    # 构建前快照：把 events.json / causality.json 备份到 backups/
    saved = snapshot("prebuild")
    if saved:
        logf.write("已备份到 backups/：" + ", ".join(saved) + "\n")
        logf.flush()
    BUILD.update(proc=None, start=time.time(), log=log, done=False, code=None)
    BUILD["proc"] = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "scripts", "build_data.py")],
        cwd=ROOT, stdout=logf, stderr=subprocess.STDOUT)
    threading.Thread(target=_watch_build, args=(logf,), daemon=True).start()
    return True


def _watch_build(logf):
    p = BUILD["proc"]
    code = p.wait()
    try:
        logf.close()
    except Exception:
        pass
    BUILD["code"] = code
    BUILD["done"] = True


def build_status():
    p = BUILD["proc"]
    running = p is not None and p.poll() is None
    tail = ""
    try:
        with open(BUILD["log"], encoding="utf-8") as f:
            tail = f.read()[-2000:]
    except Exception:
        pass
    return {"ok": True, "running": running, "done": BUILD["done"],
            "code": BUILD["code"],
            "elapsed": int(time.time() - BUILD["start"]) if BUILD["start"] else 0,
            "log": tail}


if __name__ == "__main__":
    os.chdir(ROOT)
    print(f"星火日历统一工具服务：http://127.0.0.1:{PORT}/tools/workshop.html")
    print(f"（OCR 清洗 / 合并应用 / 详情丰富 三合一；OCR 需本机 Ollama）")
    print(f"站点根：{ROOT}    按 Ctrl+C 停止")
    try:
        HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    except OSError as ex:
        print(f"启动失败：{ex}（端口 {PORT} 可能被占用，先关闭旧服务窗口）")
        input("按回车退出…")
