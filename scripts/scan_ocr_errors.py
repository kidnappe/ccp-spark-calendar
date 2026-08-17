# -*- coding: utf-8 -*-
"""全量扫描 events.json 的 ocrDesc 异常清单（改进版）
   输出 UTF-8 报告到 scan_ocr_report.md，只读不改。
   A 类：异常夹字数字（过滤正常日期/量词）
   B 类：夹字拉丁字母
   C 类：疑似事实错误（字形认错启发式对照表）"""
import json
import re
from collections import Counter

SRC = 'events.json'
OUT = 'scan_ocr_report.md'

with open(SRC, encoding='utf-8') as f:
    data = json.load(f)
events = data['events']
has_ocr = [e for e in events if e.get('ocrDesc')]

# 数字后接合法单位（日期/量词）→ 排除
UNIT = r'(?:年|月|日|时|分|秒|周|星期|天|位|点|第|万|亿|千|百|十|个|名|人|军|师|旅|团|营|连|排|路|届|次|处|种|家|所|条|篇|章|节|页|件|元|角|分|倍|%|％|公里|千米|米|里|斤|吨|岁)'
# A: 汉字+数字+汉字，且数字后不是合法单位
digit_re = re.compile(r'([\u4e00-\u9fff])([0-9]{1,4})([\u4e00-\u9fff])')
def is_legal_digit(s):
    # s 形如 "X12Y"，判断 12 后是否跟单位（Y 是单位）或前面是第
    return bool(re.match(UNIT + '$', s[2])) or s[1] == '第'

latin_re = re.compile(r'([\u4e00-\u9fff])([A-Za-z]{1,5})([\u4e00-\u9fff])')

SUSPECT = [
    ('围闽', '围剿'), ('转得', '围剿'), ('葛斯科', '莫斯科'), ('坦旋', '斡旋'),
    ('唱到', '遭到'), ('镇奈', '镇压'), ('雄超直气昂昂', '雄赳赳气昂昂'),
    ('谤振十', '辜振甫'), ('乌效别克斯坦', '乌兹别克斯坦'), ('习近乎', '习近平'),
    ('前政委员会', '前敌委员会'), ('中昔军委', '中央军委'),
    ('周佛海2包惠僧', '周佛海、包惠僧'), ('彻底和否定', '彻底否定'),
]
suspect_re = re.compile('|'.join(re.escape(p[0]) for p in SUSPECT))

def ctx(d, s, e, pad=20):
    return d[max(0, s - pad):e + pad]

def ev_label(e):
    return f"{e.get('year','?')}-{e.get('month','?')}-{e.get('day','?')}  {e.get('title','?')}"

lines = []
lines.append('# ocrDesc 全量异常扫描报告')
lines.append('')
lines.append(f"- 扫描时间：{__import__('datetime').datetime.now().isoformat(timespec='seconds')}")
lines.append(f"- 事件总数 {len(events)}，带 ocrDesc {len(has_ocr)}")
lines.append('- 原则：只读标记，不修改数据；机械优先、打标不编造')
lines.append('')

# ---- A 类 ----
a_hits, a_toks = [], Counter()
for e in has_ocr:
    d = e['ocrDesc']; lab = ev_label(e)
    for m in digit_re.finditer(d):
        seg = m.group(0)
        if is_legal_digit(seg):
            continue
        a_hits.append((lab, ctx(d, m.start(), m.end())))
        a_toks[m.group(2)] += 1
lines.append(f"## A 类：异常夹字数字（已过滤合法日期/量词）= {len(a_hits)} 处")
for lab, c in a_hits:
    lines.append(f"- [{lab}] …{c}…")
lines.append('')
lines.append('### A 类高频数字片段 TOP30')
for tok, n in a_toks.most_common(30):
    lines.append(f"- 「{tok}」 x{n}")
lines.append('')

# ---- B 类 ----
b_hits, b_toks = [], Counter()
for e in has_ocr:
    d = e['ocrDesc']; lab = ev_label(e)
    for m in latin_re.finditer(d):
        b_hits.append((lab, ctx(d, m.start(), m.end())))
        b_toks[m.group(2).lower()] += 1
lines.append(f"## B 类：夹字拉丁字母 = {len(b_hits)} 处")
for lab, c in b_hits:
    lines.append(f"- [{lab}] …{c}…")
lines.append('')
lines.append('### B 类高频字母片段 TOP30')
for tok, n in b_toks.most_common(30):
    lines.append(f"- 「{tok}」 x{n}")
lines.append('')

# ---- C 类 ----
c_hits = []
for e in has_ocr:
    d = e['ocrDesc']; lab = ev_label(e)
    for m in suspect_re.finditer(d):
        c_hits.append((lab, ctx(d, m.start(), m.end())))
lines.append(f"## C 类：疑似事实错误（对照表命中）= {len(c_hits)} 处")
for lab, c in c_hits:
    lines.append(f"- [{lab}] …{c}…")
lines.append('')

with open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines) + '\n')
print(f"报告已生成: {OUT}，A={len(a_hits)} B={len(b_hits)} C={len(c_hits)}")
