#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_similar.py —— 预计算"相关事件" top-N（标签加权 + TF-IDF 文本相似度）

读取 events.json 中的 tags 字段（由 tag_events.py 生成），
结合 TF-IDF 余弦相似度和因果边关系，为每条事件计算 top-8 相关事件，
写入 events.json 的 similar 字段。

用法：
  python scripts/build_similar.py              # 全量计算并写入
  python scripts/build_similar.py --top 10     # 改为 top-10
  python scripts/build_similar.py --dry-run    # 不写入，仅输出统计
  python scripts/build_similar.py --key 1921-7-23  # 查看单条结果

依赖：仅 Python 标准库（math, collections, re）。
"""
import argparse
import json
import math
import os
import re
import sys
from collections import Counter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
EVENTS_PATH = os.path.join(ROOT, "events.json")
CAUSALITY_PATH = os.path.join(ROOT, "causality.json")

# ========== 简易中文分词（按字/词切分，无第三方依赖） ==========
STOPWORDS = set("的了是在和与及其对为着过被把将从到也都还就而又或但如果因为所以"
                "这那之上下中前后左右内外里间年月日时分秒号第")

def tokenize(text):
    """粗粒度中文分词：连续汉字按 bigram 切分 + 英文/数字按词"""
    if not text:
        return []
    tokens = []
    chinese_runs = re.findall(r'[\u4e00-\u9fff]+', text)
    for run in chinese_runs:
        for i in range(len(run) - 1):
            bg = run[i:i+2]
            if bg[0] not in STOPWORDS and bg[1] not in STOPWORDS:
                tokens.append(bg)
        if len(run) == 1 and run not in STOPWORDS:
            tokens.append(run)
    eng = re.findall(r'[a-zA-Z0-9]+', text)
    tokens.extend(w.lower() for w in eng if len(w) > 1)
    return tokens

# ========== TF-IDF ==========
def build_tfidf(docs):
    """docs: list of str -> (vocab, tfidf_vectors as list of dict)"""
    tokenized = [tokenize(d) for d in docs]
    df = Counter()
    for toks in tokenized:
        df.update(set(toks))
    n = len(docs)
    idf = {t: math.log((n + 1) / (c + 1)) + 1 for t, c in df.items()}

    vectors = []
    for toks in tokenized:
        tf = Counter(toks)
        total = len(toks) or 1
        vec = {t: (c / total) * idf.get(t, 1) for t, c in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1
        vec = {t: v / norm for t, v in vec.items()}
        vectors.append(vec)
    return vectors

def cosine_sim(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(t, 0) for t, v in a.items())

# ========== 因果边加载 ==========
def load_causal_pairs():
    pairs = set()
    if not os.path.exists(CAUSALITY_PATH):
        return pairs
    with open(CAUSALITY_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    for e in data.get("edges", []):
        pairs.add((e["from"], e["to"]))
        pairs.add((e["to"], e["from"]))
    return pairs

# ========== 打分 ==========
def score_pair(a, b, tfidf_a, tfidf_b, causal_pairs):
    s = 0.0
    ta, tb = a.get("tags", {}), b.get("tags", {})
    if ta.get("theme") and ta["theme"] == tb.get("theme"):
        s += 3.0
    if ta.get("nature") and ta["nature"] == tb.get("nature"):
        s += 2.0
    if ta.get("period") and ta["period"] == tb.get("period"):
        s += 1.5
    ka = a.get("key") or f"{a['year']}-{a['month']}-{a['day']}"
    kb = b.get("key") or f"{b['year']}-{b['month']}-{b['day']}"
    if (ka, kb) in causal_pairs:
        s += 0.5
    s += cosine_sim(tfidf_a, tfidf_b) * 2.0
    return s

# ========== 主流程 ==========
def main():
    ap = argparse.ArgumentParser(description="预计算相关事件 top-N")
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--key", help="查看指定事件的相似列表")
    args = ap.parse_args()

    with open(EVENTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    events = data["events"]

    tagged = sum(1 for e in events if e.get("tags"))
    print(f"事件总数: {len(events)}，已有标签: {tagged}")
    if tagged == 0:
        print("警告：无标签数据，请先运行 tag_events.py。将仅使用文本相似度。", file=sys.stderr)

    docs = [f"{e['title']} {e.get('desc','')} {e.get('bg','')}" for e in events]
    print("构建 TF-IDF 向量...")
    vectors = build_tfidf(docs)

    causal_pairs = load_causal_pairs()
    print(f"因果边: {len(causal_pairs)//2} 对")

    keys = [e.get("key") or f"{e['year']}-{e['month']}-{e['day']}" for e in events]

    if args.key:
        idx = keys.index(args.key) if args.key in keys else -1
        if idx < 0:
            print(f"未找到 key: {args.key}", file=sys.stderr)
            sys.exit(1)
        scores = []
        for j in range(len(events)):
            if j == idx:
                continue
            s = score_pair(events[idx], events[j], vectors[idx], vectors[j], causal_pairs)
            scores.append((s, j))
        scores.sort(reverse=True)
        print(f"\n{args.key} 「{events[idx]['title']}」的 top-{args.top} 相关事件：")
        for s, j in scores[:args.top]:
            print(f"  {s:.3f}  {keys[j]}  {events[j]['title']}")
            t = events[j].get("tags", {})
            if t:
                print(f"        tags: {t.get('theme','?')}/{t.get('nature','?')}/{t.get('period','?')}")
        return

    print(f"计算 {len(events)}x{len(events)-1} 对相似度...")
    similar_map = {}
    for i in range(len(events)):
        scores = []
        for j in range(len(events)):
            if i == j:
                continue
            s = score_pair(events[i], events[j], vectors[i], vectors[j], causal_pairs)
            scores.append((s, keys[j]))
        scores.sort(reverse=True)
        similar_map[keys[i]] = [k for _, k in scores[:args.top]]
        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(events)}]")

    print(f"完成。每条事件 top-{args.top} 相关事件已计算。")

    if args.dry_run:
        sample_keys = keys[:5]
        for k in sample_keys:
            ev = next(e for e in events if (e.get("key") or f"{e['year']}-{e['month']}-{e['day']}") == k)
            print(f"\n{k} 「{ev['title']}」→")
            for sk in similar_map[k]:
                sev = next(e for e in events if (e.get("key") or f"{e['year']}-{e['month']}-{e['day']}") == sk)
                print(f"    {sk} {sev['title']}")
        return

    for ev in events:
        k = ev.get("key") or f"{ev['year']}-{ev['month']}-{ev['day']}"
        ev["similar"] = similar_map.get(k, [])

    with open(EVENTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已写入 {EVENTS_PATH}")

    has_sim = sum(1 for e in events if e.get("similar"))
    print(f"similar 覆盖：{has_sim}/{len(events)}")

if __name__ == "__main__":
    main()
