# -*- coding: utf-8 -*-
"""随机抽样 ocrDesc 用于人工核对错误率；并精化 A 类（排除更多合法量词）输出精确清单"""
import json, re, random

with open('events.json', encoding='utf-8') as f:
    data = json.load(f)
events = data['events']
ocr = [e for e in events if e.get('ocrDesc')]

# 精化 A 类：排除更多合法单位
UNIT = r'(?:年|月|日|时|分|秒|周|星期|天|位|点|第|万|亿|千|百|十|个|名|人|军|师|旅|团|营|连|排|路|届|次|处|种|家|所|条|篇|章|节|页|件|元|角|倍|%|％|号|多|至|共|余|名|里|公里|千米|米|斤|吨|岁|位|项|批|支|架|辆|艘|枚|发|卷|期|版|类|项|款|条|句|字|词|段|行|册|集|首|座|台|门|部|级|层|所|项|列)'
digit_re = re.compile(r'([\u4e00-\u9fff])([0-9]{1,4})([\u4e00-\u9fff])')
def is_legal(seg):
    if seg[1] == '第': return True
    return bool(re.match(UNIT + '$', seg[2])) or seg[2] in '年月日时分秒'

print('===== 抽样 20 条完整 ocrDesc（人工核对）=====')
random.seed(42)
for e in random.sample(ocr, 20):
    print(f"\n[{e.get('year')}-{e.get('month')}-{e.get('day')} | {e.get('title')}]")
    print(e['ocrDesc'][:300])

print('\n\n===== 精化后 A 类精确清单（仅疑似错误）=====')
a_hits = []
for e in ocr:
    d = e['ocrDesc']
    for m in digit_re.finditer(d):
        if not is_legal(m.group(0)):
            a_hits.append((f"{e.get('year')}-{e.get('month')}-{e.get('day')} {e.get('title')}", d[max(0,m.start()-18):m.end()+18]))
print(f"疑似错误夹字数字：{len(a_hits)} 处")
for lab, c in a_hits:
    print(f"- [{lab}] …{c}…")
