#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wash_exam_paper.py —— 洗考卷（任务②收尾：修正考卷本身的可疑标注）
背景：v3 错题清单 20 条中约三分之一系考卷标注可疑（交接文档结论），
     用带噪声的基线当生产验收尺子不可靠，故逐条人工复核后产出洗净考卷。

裁决原则（与冻结 v3 SYS 规则一致，只修考卷不改模型作答）：
  rule5 纪念/周年 → background；rule6 同类会议理论继承 → background；
  制度性通过/组织延续/试验田 → causal；拿不准且人工原判可辩护 → 保持不动并记录。

做法：只改 washed 版 jsonl 的 expected 字段（模型作答一字不动），
     再用 causal_exam.py --rescore 出新基线 exam_report_v4_washed.md。
用法：
  python wash_exam_paper.py            # 生成 exam_results_washed.jsonl + 洗考卷说明
  python causal_exam.py --rescore      # 需先把 washed 复制为 exam_results.jsonl 再跑
"""
import io
import json
import os
import sys

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
CAL = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(HERE, "exam_results_v3.jsonl")
DST = os.path.join(HERE, "exam_results_washed.jsonl")
NOTES = os.path.join(HERE, "洗考卷裁决说明.md")

# ---- 裁决结论：翻案清单（titleA, titleB, 新expected, 理由）----
# 这 5 条的"错"不在模型而在标注：与冻结规则的 rule5/rule6 直接冲突。
FLIPS = [
    ("科技体制改革决定", "教育体制改革决定", "background",
     "1985 年两个平行出台的改革决定，材料无相互促成记载，rule6 同类→background"),
    ("中共十五大召开", "中共十六大召开", "background",
     "党代会间的理论继承属 rule6 同类会议→background；原标 causal 与自家规则冲突（交接文档已点名宽松标注）"),
    ("“一带一路”高峰论坛", "第二届“一带一路”论坛", "background",
     "连续举办的同系列会议，rule6 同类→background"),
    ("“一带一路”高峰论坛", "“一带一路”十周年", "background",
     "十周年是时间刻度非事件结果，rule5 纪念→background"),
    ("第二届“一带一路”论坛", "“一带一路”十周年", "background",
     "论坛不是周年节点的成因，rule5 纪念→background"),
]
# 其余 15 条错题经复核维持原标注（模型真错或规则边界内正确），理由见 NOTES 正文。


def load_events_by_title():
    d = json.load(open(os.path.join(CAL, "events.json"), encoding="utf-8"))
    m = {}
    for e in d["events"]:
        m.setdefault(e.get("title", ""), []).append(e)
    return m


def ekey(e):
    return "%d-%d-%d" % (e["year"], e["month"], e["day"])


def main():
    records = [json.loads(l) for l in open(SRC, encoding="utf-8") if l.strip()]
    by_title = load_events_by_title()

    flip_keys = set()
    notes = ["# 洗考卷裁决说明（v3 错题 20 条逐条复核）\n",
             "> 只改 expected 标注、不动模型作答；每条给出裁决与理由。",
             "> 裁决原则：与冻结 v3 SYS 的 rule5/rule6/rule7 保持一致；拿不准且原判可辩护则维持。\n"]
    for ta, tb, newlab, why in FLIPS:
        ka = by_title.get(ta, [])
        kb = by_title.get(tb, [])
        if not ka or not kb:
            print("!! 标题未匹配事件：", ta, tb)
            continue
        flip_keys.add((ka[0] and ekey(ka[0]), kb[0] and ekey(kb[0])))
        notes.append("## 翻案：%s → %s\n- 原标注 `causal` → 改 `%s`\n- 理由：%s\n" % (ta, tb, newlab, why))

    changed = 0
    out = []
    for r in records:
        if (r["a"], r["b"]) in flip_keys and r["expected"] == "causal":
            r = dict(r, expected="background",
                     provenance=(r.get("provenance") or "") + "｜洗考卷翻案")
            changed += 1
        out.append(r)

    kept = ["上海共产党早期组织成立→共产主义小组扩散（组织源头推动各地建组，rule7 成立）",
            "建党纪念日→中央确定党的生日（纪念家族，rule5 判 background 无误，模型答 causal 错）",
            "南京大屠杀→首个国家公祭日（同上，rule5）",
            "志愿军入朝→保家卫国宣言（入朝既成事实促成各党派公开表态，causal 可辩护）",
            "一五计划开始→党的全国代表会议（1955 代表会议审议计划草案，因计划而开会）",
            "一届人大→国务院成立（人大通过国务院组织法，直接制度因果，模型误用 rule6）",
            "葛洲坝动工→三峡开工（rule7 试验田条款的原型案例）",
            "十届全国人大→反分裂国家法（该届人大三次会议通过，制度性通过）",
            "十届全国人大→物权法（五次会议通过，同上）",
            "宪法修正案→宪法修正案（同名重名事件对，rule6 判 background 合理，建议未来给事件标题去重）",
            "天宫一号对接→神八天宫对接（发射是交会对接的直接前奏，rule7）",
            "习近平当选总书记→继续领航（任期制度自然延续，非事件因果，rule 边界案例：rule7 措辞未覆盖'连任'，维持 background）",
            "十届全国人大→十一五规划批准（四次全会批准，模型引文系伪造故记伪引文，但标注 background 本身可辩护——同届人大例行审议）",
            "十六大→十八大 / 十六大→十九大（跨届理论继承，rule6，模型答 causal 错）"]
    notes.append("## 维持原标注的错题（%d 条，模型真错或边界内正确）\n" % len(kept))
    for k in kept:
        notes.append("- %s" % k)
    notes.append("\n## 统计\n- 送审错题 20 条：翻案 %d 条、维持 %d 条" % (len(FLIPS), len(kept)))

    with open(DST, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    open(NOTES, "w", encoding="utf-8").write("\n".join(notes))
    print("翻案实际生效 %d 条（目标 %d）" % (changed, len(FLIPS)))
    print("已写出:", DST)
    print("已写出:", NOTES)
    print("下一步：copy exam_results_washed.jsonl -> exam_results.jsonl 后跑 --rescore")


if __name__ == "__main__":
    main()
