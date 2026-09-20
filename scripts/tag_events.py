#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tag_events.py —— 语义标签自动打标（规则 + 本地 LLM）

为每条事件打三维标签：
  period : 历史时期（纯规则，年份映射）
  nature : 事件性质（规则优先，未命中走 LLM）
  theme  : 主题分类（LLM 8 选 1）

用法：
  python scripts/tag_events.py                    # 全量打标（需 Ollama 运行）
  python scripts/tag_events.py --rules-only       # 仅规则（period + nature），不调 LLM
  python scripts/tag_events.py --key 1921-7-23    # 单条测试
  python scripts/tag_events.py --review           # 输出低置信度复核清单

可选：
  --model qwen2.5:local7b
  --base  http://127.0.0.1:11434
  --dry-run   不写入 events.json，仅输出到 stdout
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
EVENTS_PATH = os.path.join(ROOT, "events.json")

DEFAULT_BASE = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5:local7b"

# ========== 时期（纯规则） ==========
PERIODS = [
    (1911, 1918, "辛亥革命与北洋时期"),
    (1919, 1927, "建党与大革命"),
    (1927, 1937, "土地革命战争"),
    (1937, 1945, "抗日战争"),
    (1945, 1949, "解放战争"),
    (1949, 1956, "社会主义改造"),
    (1956, 1966, "全面建设社会主义"),
    (1966, 1976, "文化大革命"),
    (1976, 1978, "拨乱反正"),
    (1978, 2012, "改革开放"),
    (2012, 9999, "新时代"),
]

def tag_period(year):
    for lo, hi, name in PERIODS:
        if lo <= year <= hi:
            return name
    return "其他"

# ========== 性质（规则优先） ==========
NATURE_RULES = [
    (r"代表大会|全会|会议|座谈会|政治局.*会|工作会议|代表会议|协商会议|人民代表大会", "会议"),
    (r"战役|战斗|起义|暴动|战争|进攻|防御|突围|长征|渡江|淮海|平津|辽沈|百团大战|反围剿|反\"围剿\"", "军事行动"),
    (r"条约|协定|协议|联合声明|公报|停战", "条约协定"),
    (r"法|条例|决议|决定|指示|通知|纲要|规划|方案|意见|办法|规定|宣言", "政策法令"),
    (r"运动|整风|三反|五反|大跃进|人民公社化|社会主义教育", "政治运动"),
    (r"成立|建立|组建|创办|创建|设立|开幕|揭牌", "机构创设"),
    (r"发射|建成|投产|通车|首飞|下水|并网|竣工|试飞|试车", "建设成就"),
    (r"逝世|殉国|牺牲|遇难", "人物逝世"),
    (r"选举|任命|当选|就任|卸任|罢免|改组", "人事变动"),
    (r"示威|游行|罢工|罢课|抗议|请愿|集会|惨案|事件", "群众事件"),
    (r"发表|出版|刊发|刊登|公布|发布", "文告发表"),
    (r"外交|建交|断交|访问|出访|会晤|会谈|接见", "外交活动"),
]

NATURE_LIST = ["会议", "军事行动", "条约协定", "政策法令", "政治运动",
               "机构创设", "建设成就", "人物逝世", "人事变动", "群众事件",
               "文告发表", "外交活动", "其他"]

def tag_nature_rules(title, desc):
    text = title + " " + (desc or "")
    for pattern, label in NATURE_RULES:
        if re.search(pattern, text):
            return label, True
    return None, False

# ========== 主题（LLM） ==========
THEME_LIST = ["军事", "政治", "经济", "外交", "思想文化", "科技教育", "社会民生", "组织制度"]

THEME_SYSTEM = (
    "你是中共党史分类专家。任务：为给定事件选择最合适的主题分类。\n"
    "可选主题（8选1）：军事、政治、经济、外交、思想文化、科技教育、社会民生、组织制度\n"
    "规则：\n"
    "1. 只输出 JSON，格式 {\"theme\":\"...\",\"confidence\":0.0-1.0}\n"
    "2. confidence 表示你对分类的确信程度\n"
    "3. 如果事件跨多个主题，选最主要的\n"
    "4. 不要输出任何解释"
)

def call_ollama(base, model, system, prompt):
    payload = {
        "model": model, "prompt": prompt, "system": system,
        "format": "json", "stream": False,
        "options": {"temperature": 0, "num_ctx": 2048, "num_predict": 100},
    }
    req = urllib.request.Request(
        base.rstrip("/") + "/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode("utf-8"))
    return d.get("response", "")

def tag_theme_llm(base, model, event):
    prompt = (
        f"事件：{event['title']}\n"
        f"日期：{event['year']}年{event['month']}月{event['day']}日\n"
        f"简述：{(event.get('desc') or '')[:200]}\n\n"
        f"请选择主题分类（{'/'.join(THEME_LIST)}）："
    )
    try:
        raw = call_ollama(base, model, THEME_SYSTEM, prompt)
        d = json.loads(raw)
        theme = d.get("theme", "")
        conf = float(d.get("confidence", 0.5))
        if theme not in THEME_LIST:
            for t in THEME_LIST:
                if t in theme:
                    theme = t
                    break
            else:
                return "政治", 0.3
        return theme, conf
    except Exception as e:
        print(f"  [WARN] LLM failed for {event['key']}: {e}", file=sys.stderr)
        return None, 0.0

def tag_nature_llm(base, model, event):
    prompt = (
        f"事件：{event['title']}\n"
        f"简述：{(event.get('desc') or '')[:200]}\n\n"
        f"请从以下选项中选择事件性质（只选1个）：\n{'/'.join(NATURE_LIST)}\n"
        f'输出 JSON：{{"nature":"...","confidence":0.0-1.0}}'
    )
    system = "你是中共党史分类专家。只输出 JSON，不要解释。"
    try:
        raw = call_ollama(base, model, system, prompt)
        d = json.loads(raw)
        nature = d.get("nature", "")
        conf = float(d.get("confidence", 0.5))
        if nature not in NATURE_LIST:
            for n in NATURE_LIST:
                if n in nature:
                    nature = n
                    break
            else:
                return "其他", 0.3
        return nature, conf
    except Exception:
        return "其他", 0.3

# ========== 主流程 ==========
def process_events(events, args):
    results = []
    total = len(events)
    for i, ev in enumerate(events):
        key = ev.get("key") or f"{ev['year']}-{ev['month']}-{ev['day']}"
        title = ev["title"]
        desc = ev.get("desc", "")

        period = tag_period(ev["year"])

        nature, nature_confident = tag_nature_rules(title, desc)
        nature_conf = 0.95 if nature_confident else 0.0

        theme = None
        theme_conf = 0.0

        if not args.rules_only:
            if nature is None:
                nature, nature_conf = tag_nature_llm(args.base, args.model, ev)
            theme, theme_conf = tag_theme_llm(args.base, args.model, ev)
            time.sleep(0.3)
        else:
            if nature is None:
                nature = "其他"
                nature_conf = 0.3
            theme = "政治"
            theme_conf = 0.0

        tag = {
            "period": period,
            "nature": nature or "其他",
            "theme": theme or "政治",
        }
        conf = {
            "nature": nature_conf,
            "theme": theme_conf,
        }
        results.append({"key": key, "title": title, "tags": tag, "confidence": conf})

        if (i + 1) % 20 == 0 or i == total - 1:
            print(f"  [{i+1}/{total}] {key} → {tag['theme']}/{tag['nature']}/{tag['period']}")

    return results

def merge_tags(events, results):
    tag_map = {r["key"]: r for r in results}
    for ev in events:
        key = ev.get("key") or f"{ev['year']}-{ev['month']}-{ev['day']}"
        if key in tag_map:
            ev["tags"] = tag_map[key]["tags"]
            ev["_tagConf"] = tag_map[key]["confidence"]

def print_review(results):
    low = [r for r in results
           if r["confidence"].get("theme", 1) < 0.7 or r["confidence"].get("nature", 1) < 0.7]
    print(f"\n=== 低置信度复核清单（{len(low)} 条）===")
    for r in low:
        print(f"  {r['key']} {r['title']}")
        print(f"    theme={r['tags']['theme']} (conf={r['confidence'].get('theme',0):.2f})"
              f"  nature={r['tags']['nature']} (conf={r['confidence'].get('nature',0):.2f})")

def main():
    ap = argparse.ArgumentParser(description="语义标签自动打标")
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--rules-only", action="store_true", help="仅规则打标，不调 LLM")
    ap.add_argument("--key", help="只处理指定 key（逗号分隔）")
    ap.add_argument("--dry-run", action="store_true", help="不写入 events.json")
    ap.add_argument("--review", action="store_true", help="输出低置信度复核清单")
    args = ap.parse_args()

    with open(EVENTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    events = data["events"]

    if args.key:
        keys = set(k.strip() for k in args.key.split(","))
        events = [e for e in events
                  if (e.get("key") or f"{e['year']}-{e['month']}-{e['day']}") in keys]
        if not events:
            print("未找到指定 key 的事件", file=sys.stderr)
            sys.exit(1)

    print(f"待打标事件：{len(events)} 条")
    if not args.rules_only:
        print(f"LLM: {args.model} @ {args.base}")
    t0 = time.time()

    results = process_events(events, args)
    elapsed = time.time() - t0
    print(f"\n完成，耗时 {elapsed:.1f}s")

    if args.review:
        print_review(results)

    if args.dry_run:
        print(json.dumps(results[:10], ensure_ascii=False, indent=2))
        if len(results) > 10:
            print(f"  ... 共 {len(results)} 条（省略）")
        return

    merge_tags(data["events"], results)
    with open(EVENTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已写入 {EVENTS_PATH}")

    tagged = sum(1 for e in data["events"] if e.get("tags"))
    print(f"标签覆盖：{tagged}/{len(data['events'])}")

if __name__ == "__main__":
    main()
