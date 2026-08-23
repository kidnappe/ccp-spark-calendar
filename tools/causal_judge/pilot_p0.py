#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pilot_p0.py —— A级×P0 试运行（生产前验收：先跑 N 条对照基线再放全量）
通过统一服务 /api/judge 逐条送审 P0 队列（verified 且 evidence 为空），
产出 pilot_results.jsonl + 控制台摘要（伪引文率 vs 基线 12%、平均耗时）。
用法：
  python pilot_p0.py            # 默认 10 条
  python pilot_p0.py --limit 30
依赖：tools/detail_server.py 已在 8001 运行 + 本机 Ollama。
"""
import argparse
import io
import json
import os
import sys
import time
import urllib.request

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
CAL = os.path.dirname(os.path.dirname(HERE))
API = "http://127.0.0.1:8001/api/judge"
OUT = os.path.join(HERE, "pilot_results.jsonl")
BASELINE_QUOTE_EFF = 88  # 考试 v3/washed 基线


def pick_p0(limit):
    evs = json.load(open(os.path.join(CAL, "events.json"), encoding="utf-8"))["events"]
    keys = {e.get("key") or "%d-%d-%d" % (e["year"], e["month"], e["day"]) for e in evs}
    edges = json.load(open(os.path.join(CAL, "causality.json"), encoding="utf-8"))["edges"]
    done = set()
    if os.path.exists(OUT):
        for l in open(OUT, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                done.add((r["a"], r["b"]))
    todo = []
    for e in edges:
        k = (e["from"], e["to"])
        if (e.get("tier") == "verified" and not (e.get("evidence") or "").strip()
                and e["from"] in keys and e["to"] in keys and k not in done):
            todo.append(e)
            if len(todo) >= limit:
                break
    return todo, len(done)


def judge(edge, model):
    payload = {"a": edge["from"], "b": edge["to"], "model": model}
    req = urllib.request.Request(API, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--model", default="qwen2.5:local7b")
    args = ap.parse_args()

    todo, cached = pick_p0(args.limit)
    print("P0 待跑 %d 条（缓存已有 %d）" % (len(todo), cached))
    f = open(OUT, "a", encoding="utf-8")
    for i, e in enumerate(todo, 1):
        t0 = time.time()
        try:
            d = judge(e, args.model)
            if not d.get("ok"):
                raise RuntimeError(d.get("error") or "unknown")
            rec = {"a": d["a"], "b": d["b"], "currentTier": e.get("tier"),
                   "verdict": d["verdict"], "quote": d["quote"],
                   "quoteValid": bool(d["quoteValid"]), "reason": d["reason"],
                   "elapsed": d["elapsed"], "model": d["model"]}
        except Exception as ex:
            rec = {"a": e["from"], "b": e["to"], "currentTier": e.get("tier"),
                   "verdict": "parse_error", "quote": "", "quoteValid": False,
                   "reason": "", "error": str(ex)[:200], "model": args.model,
                   "elapsed": round(time.time() - t0, 1)}
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
        print("[%d/%d] %s → %s  %s%s (%ss)" % (
            i, len(todo), rec["a"], rec["b"], rec["verdict"],
            "" if rec["verdict"] != "causal" else ("·引文%s" % ("有效" if rec["quoteValid"] else "伪")),
            rec["elapsed"]))
    f.close()

    # ---- 汇总 ----
    rs = [json.loads(l) for l in open(OUT, encoding="utf-8") if l.strip()]
    qs = [r for r in rs if r["verdict"] == "causal" and r.get("quote")]
    ok = sum(1 for r in qs if r["quoteValid"])
    errs = sum(1 for r in rs if r["verdict"] == "parse_error")
    insuf = sum(1 for r in rs if r["verdict"] == "insufficient")
    el = [r["elapsed"] for r in rs if r.get("elapsed")]
    print("\n==== 试运行汇总（累计 %d 条）====" % len(rs))
    print("引文有效率：%d/%d = %d%%｜基线 %d%% → %s"
          % (ok, len(qs), round(100 * ok / len(qs)) if qs else -1,
             BASELINE_QUOTE_EFF,
             "达标" if not qs or round(100 * ok / len(qs)) >= BASELINE_QUOTE_EFF else "低于基线，停止扩量排查"))
    print("失败 %d｜弃权 %d｜平均耗时 %.1fs" % (errs, insuf, sum(el) / len(el) if el else 0))


if __name__ == "__main__":
    main()
