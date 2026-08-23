#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""causal_exam.py —— 因果裁判资格考试（任务②）
用项目里"人工裁决过的边"当考卷，盲测本地 qwen 能否胜任因果审核员。

考卷重建（原 .ocr/tier_plan1~5.json 已遗失，用现状反推）：
  正例(causal)     = causality.json 中 source 含 CAUSAL_INFERRED 且现 tier=verified
                     —— 算法提名、人工查书证后升级保下来的边
  中例(background) = 同源但现 tier=background —— 人工认定"仅时代背景/平行/纪念"
  负例(unrelated)  = backups 上一版 causality.json 有、现在没有的边 —— 人工删除

流程：组卷 → 逐条盲测（只喂两端事件文本，绝不含任何 tier 信息）→ 阅卷出报告。
缓存：exam_results.jsonl（每答一题立刻落盘），中断后重跑自动跳过已答题。
阅卷：--rescore 只重新统计，不再推理。

用法：
  python causal_exam.py               # 全量考试（约 91 题）
  python causal_exam.py --limit 5     # 冒烟测试
  python causal_exam.py --rescore     # 只重出成绩单
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

CAL = r"E:\code\ccp-spark-calendar"
BAK = os.path.join(CAL, "backups", "causality.json.bak-dedup-20260821-204846")
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "exam_results.jsonl")
REPORT = os.path.join(HERE, "exam_report.md")
OLLAMA = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5:local7b"

# 生产裁判的 system prompt 与将来 causal_judge.py 保持一字不差，考的就是它
SYS = ("你是中共党史史料审核员。给你两个历史事件各自的材料摘录，"
       "判断事件A是否在史实上促成、导致了事件B。"
       "规则：1) 只依据给出的材料判断，材料无依据时 verdict=insufficient，"
       "禁止凭自身知识补充史实；"
       "2) A只是B的时代背景，或两者是同类会议/平行事件 → background；"
       "3) 材料内容支持A促成B（思想奠基/组织准备/干部培养/经验教训等间接促成也算）→ causal；"
       "4) 输出严格 JSON，不要任何解释文字。"
       "5) 纪念不是因果：若B是为A举办的周年庆祝/纪念日/纪念活动/公祭日，"
       "或两者互为周年纪念（如20周年与25周年），一律 background；"
       "6) 同类会议之间只有理论继承、思想奠基、路线延续关系 → background；"
       "7) 组织与人员的直接延续是最强因果：A的余部/部队/保留力量并入、会师、合编为B的主体，"
       "或A工程是B的直接前奏/试验田 → causal。")

PROMPT = """事件A：
{a}

事件B：
{b}

问题：事件A 是否在史实上促成、导致了事件B？
verdict 取值：causal / background / unrelated / insufficient
quote 填支持判断的材料原句（必须是上面材料中出现过的文字），无则填空串。
输出格式：{{"verdict":"...","quote":"","reason":"一句话理由"}}"""


def ekey(e):
    return "%d-%d-%d" % (e["year"], e["month"], e["day"])


def load_events():
    d = json.load(open(os.path.join(CAL, "events.json"), encoding="utf-8"))
    return {ekey(e): e for e in d["events"]}


def block(ev):
    parts = ["《%s》（%d年%d月%d日）" % (ev.get("title", ""), ev["year"], ev["month"], ev["day"])]
    for tag, field in (("简介", "desc"), ("书证", "ocrDesc"), ("背景", "bg"), ("意义", "significance")):
        if ev.get(field):
            parts.append("%s：%s" % (tag, ev[field]))
    qs = ev.get("quotes") or []
    if qs:
        parts.append("引文：" + "；".join(qs))
    return "\n".join(parts)


def build_paper(events):
    """返回 (paper, missed)。paper 元素：(a,b,expected,provenance)"""
    cur = json.load(open(os.path.join(CAL, "causality.json"), encoding="utf-8"))["edges"]
    paper, seen = [], set()
    for e in cur:
        if "CAUSAL_INFERRED" not in (e.get("source") or ""):
            continue
        lab = {"verified": "causal", "background": "background"}.get(e.get("tier"))
        if not lab:
            continue
        k = (e["from"], e["to"])
        if k not in seen:
            seen.add(k)
            paper.append((e["from"], e["to"], lab, "现存推断源边·%s" % e.get("tier")))
    if os.path.exists(BAK):
        old = json.load(open(BAK, encoding="utf-8"))["edges"]
        ck = {(e["from"], e["to"]) for e in cur}
        for e in old:
            k = (e["from"], e["to"])
            if k not in ck and k not in seen:
                seen.add(k)
                paper.append((e["from"], e["to"], "unrelated", "已被人工删除"))
    valid, missed = [], []
    for a, b, lab, prov in paper:
        if a != b and a in events and b in events:
            valid.append((a, b, lab, prov))
        else:
            missed.append((a, b, lab))
    return valid, missed


def parse_json(text):
    if not text:
        raise ValueError("模型返回为空")
    try:
        return json.loads(text)
    except Exception:
        s, e = text.find("{"), text.rfind("}")
        if s < 0 or e < 0:
            raise ValueError("模型返回非 JSON: " + text[:120])
        return json.loads(text[s:e + 1])


def ask(model, a_txt, b_txt):
    payload = {
        "model": model, "system": SYS,
        "prompt": PROMPT.format(a=a_txt, b=b_txt),
        "format": "json", "stream": False,
        "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 400},
    }
    req = urllib.request.Request(OLLAMA + "/api/generate",
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode("utf-8")).get("response", "")


def norm(s):
    return re.sub(r"[\s，。、；：「」『“”‘’（）()《》\[\]—\-·…！!?？]", "", s or "")


def quote_valid(quote, a_txt, b_txt):
    """引文必须是两端材料原文的子串（去空白标点后比对），否则视为无效引用"""
    q = norm(quote)
    if len(q) < 6:
        return False
    corpus = norm(a_txt) + "|" + norm(b_txt)
    return q in corpus


def rescore(records, events, out):
    matrix = defaultdict(Counter)          # expected -> verdict -> n
    quotes_ok = quotes_total = 0
    for rec in records:
        exp, v = rec["expected"], rec.get("verdict") or "parse_error"
        matrix[exp][v] += 1
        if v == "causal" and rec.get("quote"):
            quotes_total += 1
            if quote_valid(rec["quote"], block(events[rec["a"]]), block(events[rec["b"]])):
                quotes_ok += 1
    labels = ["causal", "background", "unrelated"]
    L = []
    L.append("# 因果裁判考试成绩单\n")
    total = sum(sum(c.values()) for c in matrix.values())
    L.append("- 考生模型：%s" % rec_model(records))
    L.append("- 实考题数：%d / 组卷数见下" % total)
    L.append("")
    L.append("| 期望\\作答 | " + " | ".join(labels + ["insufficient", "其他"]) + " |")
    L.append("|---|" + "---|" * (len(labels) + 2))
    for exp in labels:
        row = [str(matrix[exp][v]) for v in labels + ["insufficient"]]
        others = sum(n for v, n in matrix[exp].items()
                     if v not in labels and v != "insufficient")
        row.append(str(others))
        L.append("| **%s** | " % exp + " | ".join(row) + " |")
    L.append("")
    for exp in labels:
        answered = sum(matrix[exp].values())
        hit = matrix[exp][exp]
        if answered:
            L.append("- 期望 %s：命中 %d/%d（%.0f%%）" % (exp, hit, answered, 100 * hit / answered))
    insuf = sum(matrix[e]["insufficient"] for e in labels)
    L.append("- 弃权(insufficient)：%d 题（占 %.0f%%）" % (insuf, 100 * insuf / max(total, 1)))
    if quotes_total:
        L.append("- 引文有效率：%d/%d（%.0f%%）" % (quotes_ok, quotes_total, 100 * quotes_ok / quotes_total))
    # 错题清单
    bad = [r for r in records
           if (r["expected"] == "causal" and r.get("verdict") != "causal")
           or (r["expected"] == "background" and r.get("verdict") not in ("background", "insufficient"))
           or (r["expected"] == "unrelated" and r.get("verdict") not in ("unrelated", "insufficient"))]
    L.append("\n## 错题清单（%d 条，供人工复核考卷本身）\n" % len(bad))
    for r in bad:
        ta = events[r["a"]].get("title", r["a"])
        tb = events[r["b"]].get("title", r["b"])
        L.append("### %s → %s" % (ta, tb))
        L.append("- 期望 `%s`｜作答 `%s`｜理由：%s" % (r["expected"], r.get("verdict"), r.get("reason", "")))
        if r.get("quote"):
            mark = "有效引文" if quote_valid(r["quote"], block(events[r["a"]]), block(events[r["b"]])) else "**伪引文**"
            L.append("- 引文（%s）：%s" % (mark, r["quote"]))
        L.append("- 出处：%s" % r.get("provenance", ""))
        L.append("")
    out.write("\n".join(L))
    return matrix


def rec_model(records):
    ms = {r.get("model") for r in records}
    return "、".join(sorted(x for x in ms if x)) or "?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只考前 N 题（冒烟测试）")
    ap.add_argument("--rescore", action="store_true", help="不推理，只用缓存重新出报告")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    args = ap.parse_args()

    events = load_events()
    paper, missed = build_paper(events)
    print("组卷：%d 题" % len(paper))
    print("  ", dict(Counter(lab for _, _, lab, _ in paper)))
    if missed:
        print("跳过端点缺失 %d 题" % len(missed))

    cache = {}
    if os.path.exists(CACHE):
        for line in open(CACHE, encoding="utf-8"):
            line = line.strip()
            if line:
                r = json.loads(line)
                cache[(r["a"], r["b"])] = r

    if not args.rescore:
        todo = [(a, b, lab, prov) for a, b, lab, prov in paper if (a, b) not in cache]
        if args.limit:
            todo = todo[:args.limit]
        print("待考 %d 题（缓存已有 %d）" % (len(todo), len(cache)))
        f = open(CACHE, "a", encoding="utf-8")
        for i, (a, b, lab, prov) in enumerate(todo, 1):
            t0 = time.time()
            try:
                raw = ask(args.model, block(events[a]), block(events[b]))
                obj = parse_json(raw)
                rec = {"a": a, "b": b, "expected": lab, "provenance": prov,
                       "model": args.model,
                       "verdict": (obj.get("verdict") or "").strip(),
                       "quote": (obj.get("quote") or "").strip(),
                       "reason": (obj.get("reason") or "").strip()}
            except Exception as ex:
                rec = {"a": a, "b": b, "expected": lab, "provenance": prov,
                       "model": args.model, "verdict": "parse_error",
                       "error": str(ex)[:200]}
            cache[(a, b)] = rec
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            print("[%d/%d] %s → %s  期望=%s 作答=%s (%.1fs)"
                  % (i, len(todo), a, b, lab, rec["verdict"], time.time() - t0))
        f.close()

    records = [cache[(a, b)] for a, b, _, _ in paper if (a, b) in cache]
    with open(REPORT, "w", encoding="utf-8") as out:
        rescore(records, events, out)
    print("成绩单已写出:", REPORT)


if __name__ == "__main__":
    main()
