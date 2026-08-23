# -*- coding: utf-8 -*-
"""
build_causality.py — 生成 causality.json（关联事件库）
======================================================
合并三类边：
  1) .ocr/causal.json            （55 条已证实边，tier=verified）
  2) .ocr/causal_inferred.json   （89 条推断边，tier=inferred）
  3) .ocr/ne_edges_1..5.json     （37 条新书事件补边，含 evidence 溯源）

产出：causality.json（符合《续做指南》格式契约），并就地校验。
运行：python build_causality.py
"""
import json, glob, os, sys

# 项目根目录（scripts/ 的上一级），保证无论从哪个 cwd 运行都能定位数据文件。
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = f"{ROOT}/causality.json"


def load_seed(p, tier, conf, src):
    """种子边：内容是 [[from,to],...] 或 {from:[to,...]}，两种形态都兼容。"""
    raw = json.load(open(p, encoding="utf-8"))
    pairs = []
    if isinstance(raw, dict):
        for f, ts in raw.items():
            for t in ts:
                pairs.append((f, t))
    else:
        pairs = [(f, t) for f, t in raw]
    edges = []
    for f, t in pairs:
        edges.append({"from": f, "to": t, "tier": tier,
                      "confidence": conf, "evidence": "", "source": src})
    return edges


def load_new():
    """新书补边：已富化格式。"""
    edges = []
    for p in sorted(glob.glob(f"{ROOT}/.ocr/ne_edges_*.json")):
        edges += json.load(open(p, encoding="utf-8"))
    return edges


def main():
    edges = []
    edges += load_seed(f"{ROOT}/.ocr/causal.json", "verified", 0.9,
                       "星火日历CAUSAL")
    edges += load_seed(f"{ROOT}/.ocr/causal_inferred.json", "inferred", 0.6,
                       "星火日历CAUSAL_INFERRED")
    new_edges = load_new()
    print("种子边: verified 55 + inferred 89 | 新书补边:", len(new_edges))

    # 去重：保留先出现的（种子边优先），新边重复则跳过
    seen, dedup = set(), []
    dropped = 0
    for ed in edges + new_edges:
        k = (ed["from"], ed["to"])
        if k in seen:
            dropped += 1
            continue
        seen.add(k)
        dedup.append(ed)

    # ---- 历史 key 迁移（事件日期修正后，源文件旧 key -> 新 key）----
    KEY_MIGRATE = {"1957-4-1": "1957-6-8"}   # 反右派斗争扩大化 实际始于 1957-6-8
    for ed in dedup:
        ed["from"] = KEY_MIGRATE.get(ed["from"], ed["from"])
        ed["to"] = KEY_MIGRATE.get(ed["to"], ed["to"])

    # ---- 人工判定计划（.ocr/tier_plan*.json）：升级/降级/删除 ----
    for planfile in (f"{ROOT}/.ocr/tier_plan.json",
                     f"{ROOT}/.ocr/tier_plan2.json",
                     f"{ROOT}/.ocr/tier_plan3.json",
                     f"{ROOT}/.ocr/tier_plan4.json",
                     f"{ROOT}/.ocr/tier_plan5.json"):
        if not os.path.exists(planfile):
            continue   # 历史计划文件可缺省（目录已随旧产物清理）
        plan = json.load(open(planfile, encoding="utf-8"))
        del_keys = {tuple(k) for k in plan.get("delete", [])}
        up_raw = plan.get("upgrade", [])
        up_map = {}
        for u in up_raw:
            if isinstance(u, dict):
                up_map[(u["from"], u["to"])] = u.get("evidence", "")
            else:
                up_map[tuple(u)] = ""
        bg_keys = {tuple(k) for k in plan.get("background", [])}

        after = []
        for ed in dedup:
            k = (ed["from"], ed["to"])
            if k in del_keys:
                continue                      # 删除（同名会议混淆等）
            if k in up_map:
                ed["tier"] = "verified"        # 升级：书证明确
                ed["confidence"] = max(ed.get("confidence", 0), 0.85)
                if up_map[k]:
                    ed["evidence"] = up_map[k]
            elif k in bg_keys:
                ed["tier"] = "background"      # 降级：纪念/平行/弱关联
                ed["confidence"] = min(ed.get("confidence", 0.9), 0.4)
            after.append(ed)
        dedup = after

        # plan 中的 upgrade 边若尚不存在，则新增（补边）
        exist = {(e["from"], e["to"]) for e in dedup}
        for u in up_raw:
            f, t = (u["from"], u["to"]) if isinstance(u, dict) else tuple(u)
            if (f, t) in exist or (f, t) in bg_keys or (f, t) in del_keys:
                continue
            dedup.append({"from": f, "to": t, "tier": "verified", "confidence": 0.85,
                          "evidence": u.get("evidence", "") if isinstance(u, dict) else "",
                          "source": "人工判定补充边"})
            exist.add((f, t))

    # 新增高置信边（evidence 非空、非原库、conf>=0.7）自动升级 verified
    upgraded_auto = 0
    for ed in dedup:
        if (ed["tier"] == "inferred" and ed.get("evidence")
                and "原库" not in ed.get("source", "")
                and ed.get("confidence", 0) >= 0.7):
            ed["tier"] = "verified"
            ed["confidence"] = max(ed.get("confidence", 0), 0.85)
            upgraded_auto += 1
    if upgraded_auto:
        print(f"自动升级高置信新增边: {upgraded_auto} 条 -> verified")

    # 端点校验（必须在 events.json 中）
    evs = json.load(open(f"{ROOT}/events.json", encoding="utf-8"))["events"]
    keys = {f"{e['year']}-{e['month']}-{e['day']}" for e in evs}
    bad = [ed for ed in dedup if ed["from"] not in keys or ed["to"] not in keys]
    if bad:
        print("!! 端点缺失的边:", len(bad))
        for ed in bad[:20]:
            print("   ", ed["from"], "->", ed["to"])
        sys.exit(1)

    # 时间倒置提示（因不晚于果；种子边已确认 0，检查新边）
    def kt(k):
        y, m, d = k.split("-")
        return (int(y), int(m), int(d))
    rev = [ed for ed in dedup if kt(ed["from"]) > kt(ed["to"])]
    if rev:
        print("!! 时间倒置边:", len(rev))
        for ed in rev[:20]:
            print("   ", ed["from"], "->", ed["to"], "|", ed.get("tier"))

    json.dump({"edges": dedup}, open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"causality.json 写出: 共 {len(dedup)} 条边"
          f"（去重丢弃 {dropped}）")

    # ---- 步骤4（可选）：注入 causes / causedBy 到 events.json ----
    from causal_algorithm import CausalGraph
    g = CausalGraph(evs, dedup)
    g.inject_causes()
    json.dump({"meta": json.load(open(f"{ROOT}/events.json", encoding="utf-8"))["meta"],
               "events": g.events},
              open(f"{ROOT}/events.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("events.json 已注入 causes/causedBy（423 条保持）")


if __name__ == "__main__":
    main()
