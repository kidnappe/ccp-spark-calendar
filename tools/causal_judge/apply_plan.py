#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_plan.py —— 把 tier_plan 草稿外科手术式应用到 causality.json
背景：build_causality.py 是「种子全量重建」模式，依赖的 .ocr 历史种子文件已遗失；
     全量重跑会丢边。本工具把计划语义（与 build_causality 计划段一致）直接应用到现存库：
       upgrade   → tier=verified, conf=max(conf,0.85), evidence 填入（含新增边场景）
       background→ tier=background, conf=min(conf,0.4)
       delete    → 移除该边
用法：
  python apply_plan.py <plan.json> [--dry]
安全：写前自动备份 causality.json 到 backups/。
"""
import io
import json
import os
import shutil
import sys
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

CAL = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CP = os.path.join(CAL, "causality.json")
BACKUP_DIR = os.path.join(CAL, "backups")


def main():
    if len(sys.argv) < 2:
        print("usage: python apply_plan.py <plan.json> [--dry]"); sys.exit(1)
    plan_path = os.path.abspath(sys.argv[1])
    dry = "--dry" in sys.argv[2:]
    plan = json.load(open(plan_path, encoding="utf-8"))

    ca = json.load(open(CP, encoding="utf-8"))
    edges = ca["edges"]
    index = {(e["from"], e["to"]): i for i, e in enumerate(edges)}

    up_raw = plan.get("upgrade", [])
    bg_keys = [tuple(k) for k in plan.get("background", [])]
    del_keys = [tuple(k) for k in plan.get("delete", [])]

    n_up = n_bg = n_del = n_new = skipped = 0
    for u in up_raw:
        f, t = (u["from"], u["to"]) if isinstance(u, dict) else tuple(u)
        ev = u.get("evidence", "") if isinstance(u, dict) else ""
        i = index.get((f, t))
        if i is None:
            print(f"[新增边] {f} → {t}")
            edges.append({"from": f, "to": t, "tier": "verified",
                          "confidence": 0.85, "evidence": ev,
                          "source": "因果裁判人工判定补充边"})
            index[(f, t)] = len(edges) - 1
            n_new += 1
            continue
        e = edges[i]
        if e.get("tier") == "verified" and (e.get("evidence") or "").strip() and not dry:
            pass  # 已有书证的实线：仍允许覆盖 evidence
        e["tier"] = "verified"
        e["confidence"] = max(e.get("confidence", 0), 0.85)
        if ev:
            e["evidence"] = ev
        n_up += 1
    for k in bg_keys:
        i = index.get(k)
        if i is None:
            print(f"[跳过·降级目标不存在] {k}"); skipped += 1; continue
        e = edges[i]
        e["tier"] = "background"
        e["confidence"] = min(e.get("confidence", 0.9), 0.4)
        n_bg += 1
    del_set = set(del_keys)
    before = len(edges)
    edges = [e for e in edges if (e["from"], e["to"]) not in del_set]
    n_del = before - len(edges)

    print(f"\n== {'干跑' if dry else '应用'}结果 ==")
    print(f"升级/补证 {n_up}(含新增{n_new})｜降级 {n_bg}｜删除 {n_del}｜跳过 {skipped}")
    print(f"边总数: {before} → {len(edges)}")

    if dry:
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    tsx = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = os.path.join(BACKUP_DIR, f"causality.json.bak-applyplan-{tsx}")
    shutil.copy2(CP, dst)
    print("备份:", os.path.basename(dst))
    json.dump({"edges": edges}, open(CP, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("causality.json 已更新")


if __name__ == "__main__":
    main()
