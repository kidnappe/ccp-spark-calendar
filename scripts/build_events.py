# -*- coding: utf-8 -*-
"""合并基线事件库 + 新书事件片段 -> events.json（外部化事件库）。"""
import json, glob, re, os

# 项目根目录（scripts/ 的上一级），保证无论从哪个 cwd 运行都能定位数据文件。
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = f"{ROOT}/events.json"

def load_base():
    return json.load(open(f"{ROOT}/.ocr/baseline_events.json", encoding="utf-8"))

def load_fragments():
    evs = []
    for i in range(1, 14):
        p = f"{ROOT}/.ocr/ne{i}.json"
        try:
            evs += json.load(open(p, encoding="utf-8"))
        except FileNotFoundError:
            pass
    return evs

def key(e):
    return f"{e['year']}-{e['month']}-{e['day']}"

def main():
    merged = {}
    for e in load_base():
        e.setdefault("source", "星火日历")
        merged[key(e)] = e
    added = 0
    for e in load_fragments():
        k = key(e)
        if k not in merged:
            merged[k] = e
            added += 1
    events = sorted(merged.values(), key=lambda x: (x["year"], x["month"], x["day"]))
    meta = {"total": len(events), "from_book": added,
            "source": "《中国共产党简史》+ 星火日历",
            "key_rule": "year-month-day"}
    json.dump({"meta": meta, "events": events}, open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"events.json 写出: 共 {len(events)} 条（新增书事件 {added} 条）")

if __name__ == "__main__":
    main()
