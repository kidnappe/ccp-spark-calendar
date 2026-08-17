#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
清洗 events.json 中的 ocrDesc（《中国共产党简史》OCR 长文本）：
  1) 自动补回被 OCR 漏掉的日期头（文本以「年」开头→补年份；以「月」开头→补「年月」；其余→补完整日期头）
  2) 套用手工核对的 OCR 错字修正表（仅少量、已确认）
  3) 修正归属：有 ocrDesc 但 source 未标《简史》的事件，补上《中国共产党简史》来源
  4) 输出清洗报告（stdout + scripts/clean_ocr_report.md），并打可疑标记供人工复核

脚本会先把原始 events.json 备份为 events.json.bak-<时间戳>，再原地写回。
幂等：重跑不会重复补日期头（靠「{year}年」是否在文中」判断）。
"""
import json
import shutil
import os
import datetime

SRC = "events.json"
HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "..", SRC)
PATH = os.path.normpath(PATH)

# 手工核对过的 OCR 错字修正（保守、已确认）
# 第一阶段：4 条；第二阶段：并入全量扫描确认的 10 组事实错误（人名/地名/史实词）
ERROR_MAP = [
    ("周佛海2包惠僧", "周佛海、包惠僧"),   # 1921 多余数字 2
    ("前政委员会",   "前敌委员会"),        # 1927 前政→前敌
    ("中昔军委",     "中央军委"),          # 1934 中昔→中央
    ("彻底和否定",   "彻底否定"),          # 1978 多余「和」
    # ── 第二阶段（2026-08-18 全量扫描确认，19 处）──
    ("围闽",         "围剿"),              # 反“围剿”
    ("转得",         "围剿"),              # 反“围剿”
    ("葛斯科",       "莫斯科"),            # 《中苏友好同盟互助条约》签订地
    ("坦旋",         "斡旋"),              # 外交斡旋
    ("唱到",         "遭到"),              # 皖南事变“遭到伏击”
    ("镇奈",         "镇压"),              # 军警镇压
    ("雄超直气昂昂", "雄赳赳气昂昂"),       # 志愿军过鸭绿江
    ("谤振十",       "辜振甫"),            # 海基会董事长
    ("乌效别克斯坦", "乌兹别克斯坦"),       # 上合组织六国
    ("习近乎",       "习近平"),            # 领导人姓名
    # ── 第三批（2026-08-18 抽样核对 + 权威源确认：人民网党史库/《简史》在线/12371.cn）──
    # 汉字字形认错
    ("阑明",         "阐明"),              # 系统阐明
    ("会姜吗",       "会亡吗"),            # 《论持久战》"中国会亡吗？答复：不会亡"
    ("三文势力",     "三股势力"),          # 吴佩孚、孙传芳、张作霖
    ("林此",         "林彪"),              # 林彪反革命集团
    ("对嵌",         "对峙"),              # 三政权对峙
    ("输重",         "辎重"),              # 缴获一批辎重
    ("踩蹦",         "蹂躏"),              # 妇女遭蹂躏
    ("哪移边境",     "鄂豫边境"),          # 鄂豫边境的中原解放区
    ("晋蔓鲁豫",     "晋冀鲁豫"),          # 晋冀鲁豫野战军
    ("黄百帮",       "黄百韬"),            # 淮海战役碾庄被歼
    ("杜嫌明",       "杜聿明"),            # 陈官庄被围
    ("苑清泉",       "邱清泉"),            # 陈官庄被围三个兵团之一
    ("守政",         "守军"),              # 天津守军
    # 数字乱入删除
    ("争取73抗战",   "争取抗战"),          # 洛川会议宣传提纲
    ("执委82王明",   "执委王明"),          # 共产国际执委王明
    ("系98统化",     "系统化"),            # 经验系统化
    ("国民31政府",   "国民政府"),          # 南京国民政府
    ("双清别136墅",  "双清别墅"),          # 北平香山双清别墅
    ("生产181合作小组", "手工业生产合作小组"),  # 三大改造
    ("张太雷38",     "张太雷"),            # 广州起义
    ("白色32恐怖",   "白色恐怖"),          # 马日事变后
    ("红一方47面军", "红一方面军"),        # 反"围剿"
]


def truncated(t, y):
    """ocrDesc 是否缺年份头：前 60 字符里没有 '{y}年'"""
    return bool(t) and (f"{y}年" not in t[:60])


def prefix_date(t, y, m, d):
    """按事件准确年月日补回被 OCR 漏掉的日期头"""
    if f"{y}年" in t:                       # 已含年份，不动
        return t
    if t.startswith("年"):                   # 漏了「年份」，文本为「年M月D日…」
        return f"{y}{t}"
    if t.startswith("月"):                   # 漏了「年月」，文本为「月…」
        return f"{y}年{m}{t}"
    # 其它情况：补完整日期头
    if d:
        return f"{y}年{m}月{d}日，" + t
    return f"{y}年{m}月，" + t


def main():
    with open(PATH, encoding="utf-8") as f:
        data = json.load(f)
    events = data["events"]

    before_trunc = sum(1 for e in events
                       if truncated(e.get("ocrDesc", "") or "", e.get("year", 0)))
    before_missing = sum(1 for e in events if not (e.get("ocrDesc", "") or "").strip())
    before_src = sum(1 for e in events
                     if (e.get("ocrDesc", "") or "").strip()
                     and "简史" not in (e.get("source", "") or ""))

    stats = {"date_prefixed": 0, "char_fixed": 0, "source_fixed": 0,
             "missing_ocr": 0, "flagged": []}

    for e in events:
        y = e.get("year")
        m = e.get("month")
        d = e.get("day")
        t = (e.get("ocrDesc", "") or "").strip()
        if not t:
            stats["missing_ocr"] += 1
            continue
        # 1) 日期头
        if f"{y}年" not in t:
            t = prefix_date(t, y, m, d)
            stats["date_prefixed"] += 1
        # 2) 错字修正
        for bad, good in ERROR_MAP:
            if bad in t:
                t = t.replace(bad, good)
                stats["char_fixed"] += 1
        e["ocrDesc"] = t
        # 3) 归属
        src = e.get("source", "") or ""
        if "简史" not in src:
            e["source"] = "《中国共产党简史》+ 星火日历"
            stats["source_fixed"] += 1
        # 4) 可疑标记
        if f"{y}年" not in t:
            stats["flagged"].append((f"{y}-{m}-{d}", "补头后仍无年份"))
        if len(t) < 40:
            stats["flagged"].append((f"{y}-{m}-{d}", "ocrDesc 过短(<40字)"))

    after_trunc = sum(1 for e in events
                      if truncated(e.get("ocrDesc", "") or "", e.get("year", 0)))
    after_missing = sum(1 for e in events if not (e.get("ocrDesc", "") or "").strip())
    after_src = sum(1 for e in events
                    if (e.get("ocrDesc", "") or "").strip()
                    and "简史" not in (e.get("source", "") or ""))

    # 备份 + 写回
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = PATH + f".bak-{ts}"
    shutil.copy2(PATH, bak)
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 报告
    report = []
    report.append("# ocrDesc 清洗报告")
    report.append("")
    report.append(f"- 备份文件：`{os.path.basename(bak)}`")
    report.append("")
    report.append("## 变更统计")
    report.append("")
    report.append(f"| 指标 | 清洗前 | 清洗后 |")
    report.append(f"| --- | --- | --- |")
    report.append(f"| 缺年份头(前60字无年份) | {before_trunc} | {after_trunc} |")
    report.append(f"| 无 ocrDesc(仅短desc) | {before_missing} | {after_missing} |")
    report.append(f"| 有ocrDesc但source未标《简史》 | {before_src} | {after_src} |")
    report.append("")
    report.append("## 本次执行的修复")
    report.append("")
    report.append(f"- 自动补日期头：`{stats['date_prefixed']}` 条")
    report.append(f"- 错字修正（套用修正表）：`{stats['char_fixed']}` 处")
    report.append(f"- 修正来源归属（补《简史》）：`{stats['source_fixed']}` 条")
    report.append(f"- 仍缺 ocrDesc（待后续填充）：`{stats['missing_ocr']}` 条")
    report.append("")
    report.append("## 可疑项（需人工复核，脚本未擅自改写）")
    report.append("")
    if stats["flagged"]:
        for k, why in stats["flagged"]:
            report.append(f"- `{k}`：{why}")
    else:
        report.append("- 无")
    report.append("")
    report.append(f"## 错字修正表（{len(ERROR_MAP)} 条，均经人工核对）")
    report.append("")
    for bad, good in ERROR_MAP:
        report.append(f"- `{bad}` → `{good}`")
    report.append("")

    text = "\n".join(report)
    rep_path = os.path.join(HERE, "clean_ocr_report.md")
    with open(rep_path, "w", encoding="utf-8") as f:
        f.write(text)

    print(text)
    print(f"\n[done] 备份: {bak}")
    print(f"[done] 报告: {rep_path}")


if __name__ == "__main__":
    main()
