# -*- coding: utf-8 -*-
# 精准补丁：仅把 events.json 的 historyData 块重写进 index.html，
# 跳过 build_data.py 的力导向布局烘焙（那部分与本次改动无关，且耗时易超时）。
# 字段透传与 build_data.build_history 保持一致：
#   month/day / year / title / desc / cat / source / ocrDesc / ocrVerified / ocrFlagged
import re, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(ROOT, "events.json")
HTML = os.path.join(ROOT, "index.html")


def main():
    ev = json.load(open(EV, encoding="utf-8"))["events"]
    history = []
    for e in ev:
        item = {
            "month": e["month"], "day": e["day"], "year": e["year"],
            "title": e["title"], "desc": e["desc"], "cat": e.get("cat", "party"),
        }
        if e.get("source"):
            item["source"] = e["source"]
        # 史料原文与核验标记：仅当存在时透传，供详情弹窗「史料原文」区块使用
        if e.get("ocrDesc"):
            item["ocrDesc"] = e["ocrDesc"]
        if e.get("ocrVerified"):
            item["ocrVerified"] = e["ocrVerified"]
        if e.get("ocrFlagged"):
            item["ocrFlagged"] = e["ocrFlagged"]
        # 史料详情面板字段：仅当存在（非空串/非空数组）时透传
        for k in ("soft", "bg", "significance", "quotes", "figures", "srcCite", "furtherReading"):
            v = e.get(k)
            if v not in (None, "", [], {}):
                item[k] = v
        history.append(item)

    body = json.dumps(history, ensure_ascii=False, indent=1)
    html = open(HTML, encoding="utf-8").read()
    m = re.search(r"const historyData = \[.*?\n\];", html, re.S)
    if not m:
        raise SystemExit("未找到 historyData 定义")
    new = "const historyData = " + body + ";"
    html = html[:m.start()] + new + html[m.end():]
    open(HTML, "w", encoding="utf-8").write(html)
    print("historyData 已重写：共", len(history), "条")


if __name__ == "__main__":
    main()
