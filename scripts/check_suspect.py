# -*- coding: utf-8 -*-
"""检查待加入 ERROR_MAP 的 bad 子串在全部 ocrDesc 中的出现次数与上下文（防误伤）"""
import json, re
from collections import Counter

with open('events.json', encoding='utf-8') as f:
    data = json.load(f)

texts = [(e.get('title',''), e.get('ocrDesc','') or '') for e in data['events']]

CANDIDATES = ['围闽', '转得', '葛斯科', '坦旋', '唱到', '镇奈',
              '雄超直气昂昂', '谤振十', '乌效别克斯坦', '习近乎']

for bad in CANDIDATES:
    hits = []
    for title, d in texts:
        if bad in d:
            for m in re.finditer(re.escape(bad), d):
                hits.append(f"[{title}] …{d[max(0,m.start()-15):m.end()+15]}…")
    print(f"「{bad}」 出现 {len(hits)} 次")
    for h in hits[:4]:
        print(f"    {h}")
    print()
