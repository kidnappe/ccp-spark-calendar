#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_detail.py —— 史料详情生成器（本地爬虫 + 本地 Ollama，数据不出本机）

流程：对指定事件
  1) 本地爬虫抓取公开史料（中文维基百科 API，纯标准库，无 CORS 限制）
  2) 本地 Ollama 模型基于抓取文本抽取 6 子块（背景/意义/论述/人物/出处/延伸）
  3) 输出 JSON，后续合并进 events.json（scripts 里的合并逻辑可复用）

用法：
  python scripts/gen_detail.py --key 1921-7-23                 # 单个事件
  python scripts/gen_detail.py --key 1921-7-23,1935-1-15,1978-12-18
  python scripts/gen_detail.py --input .ocr_work/待处理/c02.json
可选：
  --model qwen2.5:local7b   # 与 ollama list 一致
  --base  http://127.0.0.1:11434
  --out   detail_results.json
"""
import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5:local7b"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ccp-spark-calendar/1.0"}

# ---------- 爬虫：维基百科中文（api 可直连；百度百科 403 反爬不可用） ----------
def wiki_search(title, limit=5):
    """opensearch：按标题搜词条，返回词条名列表（可能含会址/纪念馆等噪音）"""
    q = urllib.parse.urlencode({"action": "opensearch", "search": title, "limit": limit, "format": "json"})
    try:
        req = urllib.request.Request("https://zh.wikipedia.org/w/api.php?" + q, headers=UA)
        with urllib.request.urlopen(req, timeout=12) as r:
            d = json.loads(r.read().decode("utf-8"))
        return d[1] or []
    except Exception:
        return []

def wiki_extract(page):
    """extract API（redirects=1 跟随重定向）：抓引言正文，返回前 4000 字"""
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


def fetch_source(event):
    """为事件抓取公开史料文本；优先选不含「会址/纪念馆」等噪音的词条；返回 (text, url)"""
    title = re.sub(r"^(第|中共|新中国|庆祝)?\d{4}年", "", event["title"]).strip()
    fallback = None
    for c in [title, title + " 会议", title + " 事件"]:
        for page in wiki_search(c):
            txt = wiki_extract(page)
            if not txt or len(txt) <= 120:
                continue
            u = "https://zh.wikipedia.org/wiki/" + urllib.parse.quote(page)
            if BAD_TERM.search(txt):
                if not fallback:
                    fallback = (txt[:4000], u)
                continue
            return txt[:4000], u
    return fallback or (None, None)

# ---------- 本地模型 ----------
def call_ollama(base, model, system, prompt):
    payload = {
        "model": model, "system": system, "prompt": prompt,
        "format": "json", "stream": False,
        "options": {"num_ctx": 4096, "num_predict": 1200},
    }
    req = urllib.request.Request(base.rstrip("/") + "/api/generate",
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.loads(r.read().decode("utf-8"))
    return d.get("response", "")

SYSTEM = ("你是中共党史史料整理员。任务：根据给定的【参考资料摘录】整理事件的史料详情。"
          "规则：1) 只依据摘录内容，不得编造或补充摘录之外的史实；"
          "2) 摘录信息不足时，相关字段给空数组/空串，绝不虚构；"
          "3) 输出严格 JSON，不要任何解释文字。")

def build_prompt(event, text, url):
    return (
        f"事件：{event['title']}（{event['year']}年{event['month']}月{event['day']}日）\n"
        f"参考资料摘录（来源 {url}）：\n---BEGIN---\n{text}\n---END---\n\n"
        '输出格式：{"bg":"背景(80-150字)","significance":"历史意义(80-150字)",'
        '"quotes":["重要论述(1-3条,无则[])"],"figures":["相关人物(2-5人,无则[])"],'
        '"srcCite":["文献出处(1-2条,注明来源)"],'
        '"furtherReading":[{"title":"延伸阅读标题","url":"链接"}]}'
    )

def parse_items(text):
    if not text:
        raise ValueError("模型返回为空")
    try:
        return json.loads(text)
    except Exception:
        s, e = text.find("{"), text.rfind("}")
        if s < 0 or e < 0:
            raise ValueError("模型返回非 JSON")
        return json.loads(text[s:e + 1])

# ---------- 主流程 ----------
def load_events(path, keys=None):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    evs = d["events"] if isinstance(d, dict) else d
    if keys:
        want = set(keys)
        return [e for e in evs if e.get("key") in want]
    return evs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", help="事件 key，逗号分隔，如 1921-7-23,1935-1-15")
    ap.add_argument("--input", help="事件输入文件（.ocr_work/待处理/c02.json 等）")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--out", default="detail_results.json")
    args = ap.parse_args()

    keys = [k.strip() for k in args.key.split(",")] if args.key else None
    if not args.input:
        args.input = "events.json"
    events = load_events(args.input, keys)
    if not events:
        sys.exit("未找到事件（检查 --key / --input）")

    print(f"共 {len(events)} 个事件 → 模型 {args.model}")
    results = []
    ok = 0
    for i, e in enumerate(events, 1):
        key = e.get("key") or f"{e['year']}-{e['month']}-{e['day']}"
        print(f"[{i}/{len(events)}] {key} {e['title']} …", flush=True)
        text, url = fetch_source(e)
        if not text:
            print("    ⚠ 未抓到资料，跳过（可后续补）", flush=True)
            continue
        try:
            raw = call_ollama(args.base, args.model, SYSTEM, build_prompt(e, text, url))
            detail = parse_items(raw)
            detail.setdefault("furtherReading", [])
            results.append({"key": key, "detail": detail, "source_url": url})
            ok += 1
            print(f"    ✓ 生成：bg {len(detail.get('bg',''))}字 / figures {len(detail.get('figures',[]))} 人", flush=True)
        except Exception as ex:
            print(f"    ⚠ 生成失败：{ex}", flush=True)
        time.sleep(0.5)  # 温和间隔，避免请求过密

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"items": results}, f, ensure_ascii=False, indent=2)
    print(f"\n完成：成功 {ok}/{len(events)} → 输出 {args.out}")
    print("查看后如需合并进 events.json，告诉我即可（我会写合并脚本）。")

if __name__ == "__main__":
    main()
