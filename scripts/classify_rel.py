#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""classify_rel.py —— 事件分类：区分「强党史 / 国家成就(弱政治) / 其他力量」
用途：把 423 条事件中与党史"非强关联、政治性较弱"的国家级事件（科技/工程/外交/
      回归/体育/灾害/民生等）识别出来，归入 cat='nation'，供页面做颜色区分与过滤。

流程（两步走）：
  1) 仅审查：python scripts/classify_rel.py            -> 产出 scripts/rel_candidates.md（不写 events.json）
  2) 确认后落库：python scripts/classify_rel.py --write -> 把候选集写入 events.json 的 cat 字段（写前自动备份）

说明：
  - cat='kmt'（42 条，国民党/其他力量）维持不变。
  - 候选集 = 显式清单（人工判定，含争议标注）+ 关键词兜底（防止显式清单漏项）。
  - 默认只把「明确国家成就类」写入；争议项（borderline）默认不写，留给用户决定，
    可通过 --write-borderline 一并写入。
"""
import json, os, re, shutil, sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV_PATH = os.path.join(ROOT, "events.json")
OUT_REPORT = os.path.join(ROOT, "scripts", "rel_candidates.md")

# ---------------------------------------------------------------------------
# 显式候选清单（标题精确匹配）。reason: 归类理由；borderline: 是否属"争议项"
# ---------------------------------------------------------------------------
NATION = {
    # —— 科技 / 工程 / 国防装备 / 基建 ——
    "成渝铁路通车": ("国家基建", False),
    "武汉长江大桥通车": ("国家基建", False),
    "大庆油田发现": ("国家基建", False),
    "北京电视台试播": ("文化建设", True),
    "中国登山队登顶珠峰": ("体育探险", True),
    "红旗渠总干渠通水": ("民生工程", True),
    "人工合成结晶牛胰岛素": ("科技成就", False),
    "南京长江大桥通车": ("国家基建", False),
    "东方红一号卫星": ("科技成就", False),
    "葛洲坝水利枢纽动工": ("国家基建", False),
    "刘家峡水电站建成": ("国家基建", False),
    "洲际导弹发射成功": ("国防科技", False),
    "863计划启动": ("国家科技战略", True),
    "国家最高科学技术奖首次颁发": ("科技制度", False),
    "西气东输开工": ("国家工程", False),
    "神舟五号载人飞行": ("航天成就", False),
    "神舟六号": ("航天成就", False),
    "青藏铁路通车": ("国家基建", False),
    "嫦娥一号": ("航天成就", False),
    "神舟七号出舱": ("航天成就", False),
    "嫦娥二号": ("航天成就", False),
    "天宫一号对接": ("航天成就", False),
    "神舟八号与天宫一号对接": ("航天成就", False),
    "神舟九号": ("航天成就", False),
    "辽宁舰入列": ("国防装备", False),
    "神舟十号": ("航天成就", False),
    "神舟十一号": ("航天成就", False),
    "C919大型客机首飞": ("科技成就", False),
    "首艘国产航母下水": ("国防装备", False),
    # —— 外交 / 国际 / 回归 ——
    "基辛格秘密访华": ("外交", False),
    "中法建交": ("外交", False),
    "恢复联合国合法席位": ("外交·国际地位", False),
    "尼克松访华": ("外交", False),
    "中日邦交正常化": ("外交", False),
    "苏联解体": ("国际背景", True),
    "中英香港谈判": ("外交", False),
    "中英草签联合声明": ("外交", False),
    "中英联合声明": ("外交", False),
    "中葡联合声明": ("外交", False),
    "香港回归祖国": ("回归·国家大事", False),
    "澳门回归祖国": ("回归·国家大事", False),
    "安理会五常首脑首次会晤": ("外交", False),
    "上海合作组织成立": ("国际组织", False),
    "加入世界贸易组织": ("外交经济", False),
    "中国正式加入世贸组织": ("外交经济", False),
    "上海获世博会主办权": ("国际活动", False),
    "上海世博会": ("国际活动", False),
    "上海世博会开幕": ("国际活动", False),
    "APEC北京峰会": ("国际会议", False),
    "亚投行成立": ("国际金融", False),
    "第二届世界互联网大会": ("国际会议", False),
    "G20杭州峰会": ("国际会议", False),
    "首届进博会": ("国际经贸", False),
    "第二届“一带一路”论坛": ("国际会议", False),
    "生物多样性大会": ("国际会议", False),
    "澳门回归20周年": ("回归纪念", True),
    "澳门回归25周年": ("回归纪念", True),
    # —— 体育 / 大型活动 ——
    "中国女排首夺世界冠军": ("体育", False),
    "奥运首金": ("体育", False),
    "北京亚运会": ("体育", False),
    "北京申奥成功": ("体育·国际活动", False),
    "北京奥运会": ("体育·国际活动", False),
    "北京获2022年冬奥会主办权": ("体育·国际活动", False),
    "北京冬奥会": ("体育·国际活动", False),
    "巴黎奥运会": ("体育", False),
    # —— 灾害 / 民生 / 制度 ——
    "唐山大地震": ("自然灾害", True),
    "抗洪抢险": ("救灾·民生", True),
    "汶川特大地震": ("自然灾害", True),
    "抗击非典": ("公共卫生", True),
    "恢复高考": ("民生·教育决策", True),
    "双休日制度实行": ("民生制度", False),
    "物权法通过": ("立法·民生", True),
    "废止《农业税条例》": ("民生政策", False),
    "废止农业税条例": ("民生政策", False),
    "全面取消农业税": ("民生政策", False),
    "海军赴亚丁湾护航": ("军事·国际行动", True),
    "首个国家公祭日": ("国家纪念制度", True),
    "防汛抗洪救灾": ("救灾·民生", True),
}

# 关键词兜底（显式清单外的补充命中；命中即 candidate，borderline 标记由人工复查）
NATION_KW = ["原子弹", "氢弹", "卫星", "两弹一星", "神舟", "嫦娥", "天宫", "北斗",
             "航母", "导弹", "核潜艇", "三峡", "水电站", "油田", "铁路通车", "大桥通车",
             "港珠澳", "高铁", "入世", "世贸", "奥运", "亚运", "世界杯", "申奥",
             "女排", "杂交水稻", "航天", "探月", "空间站", "回归祖国", "建交", "邦交",
             "联合国", "峰会", "博览会", "冬奥", "亚丁湾", "生物多样性", "农业税"]


def load():
    return json.load(open(EV_PATH, encoding="utf-8"))


def classify(ev):
    """返回 {key: cat}, key = 年-月-日"""
    out = {}
    found = {}
    for e in ev:
        key = f"{e['year']}-{e['month']}-{e['day']}"
        title = e["title"]
        if e.get("cat") == "kmt":
            out[key] = "kmt"
            continue
        if title in NATION:
            out[key] = "nation"
            found[title] = NATION[title]
        elif any(k in title for k in NATION_KW):
            out[key] = "nation"
            found[title] = ("关键词命中", False)
        else:
            out[key] = "party"
    return out, found


def build_report(ev, found, write_flag, write_borderline):
    lines = []
    lines.append("# 事件分类候选报告（强党史 / 国家成就 nation / 其他力量 kmt）\n")
    kmt = sum(1 for e in ev if e.get("cat") == "kmt")
    n_nation = len(found)
    n_party = len(ev) - kmt - n_nation
    lines.append(f"- 总事件：{len(ev)} ｜ kmt（其他力量）：{kmt} ｜ nation 候选：{n_nation} ｜ party（强党史）：{n_party}\n")
    lines.append("> 说明：`nation`=国家成就/弱政治（科技/工程/外交/回归/体育/灾害/民生），"
                 "`borderline`=争议项（可能偏党史，请人工确认）。\n")
    lines.append("| 日期 | 标题 | 理由 | 争议 |")
    lines.append("|---|---|---|---|")
    for e in ev:
        if e["title"] in found:
            reason, bl = found[e["title"]]
            lines.append(f"| {e['year']}-{e['month']:02d}-{e['day']:02d} | {e['title']} | {reason} | {'⚠️' if bl else ''} |")
    lines.append("\n## 近似重复条目（暂不自动合并，供参考）")
    lines.append("- 加入世贸 ×2：2001-11-11 加入世界贸易组织 / 2001-12-11 中国正式加入世贸组织")
    lines.append("- 废止农业税 ×3：2005-12-29 废止《农业税条例》/ 2006-01-01 废止农业税条例 / 2006-03-01 全面取消农业税")
    lines.append("- 上海世博会 ×2：2010-01-01 上海世博会 / 2010-05-01 上海世博会开幕")
    if write_flag:
        written = n_nation if write_borderline else sum(1 for _, (_, bl) in found.items() if not bl)
        lines.append(f"\n## 本次落库：{written} 条已写入 cat='nation'" + ("" if write_borderline else "（不含 borderline 争议项）"))
    else:
        lines.append("\n## 未落库（审查模式）：确认后运行 `python scripts/classify_rel.py --write` [--write-borderline] 写入")
    return "\n".join(lines) + "\n"


def main():
    write_flag = "--write" in sys.argv
    write_borderline = "--write-borderline" in sys.argv
    data = load()
    ev = data["events"]
    _, found = classify(ev)
    report = build_report(ev, found, write_flag, write_borderline)
    os.makedirs(os.path.dirname(OUT_REPORT), exist_ok=True)
    open(OUT_REPORT, "w", encoding="utf-8").write(report)
    print(f"候选 nation 数：{len(found)}；报告已写 {OUT_REPORT}")
    if write_flag:
        keys = set()
        for e in ev:
            if e["title"] in NATION:
                if write_borderline or not NATION[e["title"]][1]:
                    keys.add(f"{e['year']}-{e['month']}-{e['day']}")
            elif any(k in e["title"] for k in NATION_KW):
                keys.add(f"{e['year']}-{e['month']}-{e['day']}")
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        BAK = os.path.join(ROOT, "backups")
        os.makedirs(BAK, exist_ok=True)
        shutil.copy2(EV_PATH, os.path.join(BAK, f"events.json.bak-rel-{ts}"))
        shutil.copy2(os.path.join(ROOT, "causality.json"),
                     os.path.join(BAK, f"causality.json.bak-rel-{ts}"))
        n = 0
        for e in ev:
            k = f"{e['year']}-{e['month']}-{e['day']}"
            if k in keys:
                e["cat"] = "nation"
                n += 1
        json.dump(data, open(EV_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"已写入 {n} 条 cat='nation'；备份 backups/events.json.bak-rel-{ts}")


if __name__ == "__main__":
    main()
