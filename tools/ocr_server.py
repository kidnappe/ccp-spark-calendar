#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ocr_server.py —— OCR 清洗工具本地服务（端口 8000）
在纯静态 http.server 基础上增加 API：
  POST /api/fill   联网补写 ocrDesc：爬维基百科 → 本地模型基于抓取文本撰写 {event, model}
  GET  /api/models Ollama 可用模型
启动：双击 tools/start_ocr_gui.bat，或 python tools/ocr_server.py
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from http.server import HTTPServer, SimpleHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import detail_server as ds  # 复用维基抓取 / Ollama 调用 / JSON 解析

PORT = 8000
ROOT = ds.ROOT

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


def _site_label(url):
    """根据 URL 判断来源站点前缀"""
    if not url:
        return ""
    if "wikipedia.org" in url:
        return "维基百科"
    if ds.PARTY_OFFICIAL.search(url):
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


def do_fill(ev, model):
    """联网补写：返回 dict {ok, filled, source, note, flagged, url, page, text}"""
    text, url = ds.fetch_source(ev)
    if not text:
        return {"ok": False, "error": "未抓到参考资料（维基及搜索兜底均无对应内容）"}
    payload = {
        "model": model, "system": FILL_SYSTEM,
        "prompt": fill_prompt(ev, text, url),
        "format": "json", "stream": False,
        "options": {"num_ctx": 4096, "num_predict": 1000},
    }
    d = ds.ollama_generate(payload)
    obj = ds.parse_json(d.get("response", ""))
    items = obj.get("items") or [obj]
    it = items[0] or {}
    source = (it.get("source") or "").strip() or page_name_of(url)
    # 来源精确到具体页面：站点前缀 + 词条名 + 页面链接
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
        if self.path.startswith("/api/models"):
            try:
                names = [m.get("name", "") for m in ds.ollama_tags()]
                ds.send_json(self, {"ok": True, "models": names})
            except Exception as ex:
                ds.send_json(self, {"ok": False, "error": str(ex)})
        else:
            super().do_GET()

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
            body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception:
            body = {}
        if self.path == "/api/fill":
            try:
                ev = body.get("event") or {}
                model = body.get("model") or "qwen2.5:local7b"
                ds.send_json(self, do_fill(ev, model))
            except Exception as ex:
                ds.send_json(self, {"ok": False, "error": str(ex)})
        else:
            ds.send_json(self, {"ok": False, "error": "unknown api"}, 404)


if __name__ == "__main__":
    os.chdir(ROOT)
    print(f"OCR 清洗服务：http://127.0.0.1:{PORT}/tools/ocr_clean_gui.html")
    print(f"站点根：{ROOT}    按 Ctrl+C 停止")
    try:
        HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    except OSError as ex:
        print(f"启动失败：{ex}（端口 {PORT} 可能被占用，先关闭旧服务窗口）")
        input("按回车退出…")
