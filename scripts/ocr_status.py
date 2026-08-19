#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR 清洗进度盘点（一眼看清哪些批做完、哪些没做、每条事件处在哪一步）
用法: python scripts/ocr_status.py
输出: 控制台摘要 + scripts/ocr_status.md 报告
"""
import json, os, re, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, '.ocr_work')
EVF = os.path.join(ROOT, 'events.json')

# 排除 harness 调试/探针文件
def is_real(fname):
    if fname.startswith('_'): return False
    if 'probe' in fname: return False
    if fname.endswith('.txt'): return False
    return True

def load(p):
    try: return json.load(open(p, encoding='utf-8'))
    except Exception: return None

# ---- 载入 events.json ----
ev = load(EVF)['events']
N = len(ev)

# ---- 扫描 .ocr_work ----
clean_out, fill_out, clean_in, fill_in = {}, {}, {}, {}
for f in sorted(os.listdir(WORK)):
    if not is_real(f): continue
    p = os.path.join(WORK, f)
    d = load(p)
    if not d: continue
    items = d['items'] if isinstance(d, dict) and 'items' in d else (d if isinstance(d, list) else [])
    # 判定文件角色
    if re.match(r'^clean_c\d+\.json$', f):
        clean_out[f] = items
    elif re.match(r'^clean_\d+\.json$', f):
        clean_out[f] = items
    elif re.match(r'^fill_f\d+\.json$', f):
        fill_out[f] = items
    elif re.match(r'^c\d+\.json$', f):
        clean_in[f] = items
    elif re.match(r'^f\d+\.json$', f):
        fill_in[f] = items

# 索引 -> (corrected/filled, flagged, srcfile)  for outputs
clean_map, fill_map = {}, {}
for fname, items in clean_out.items():
    for it in items:
        i = it.get('index')
        if i is not None:
            clean_map[i] = (it.get('corrected', ''), bool(it.get('flagged')), fname)
for fname, items in fill_out.items():
    for it in items:
        i = it.get('index')
        if i is not None:
            fill_map[i] = (it.get('filled', ''), bool(it.get('flagged')), fname)

# ---- 逐事件分类 ----
cat = {'clean_merged':[], 'clean_ai_unmerged':[], 'clean_flagged':[], 'raw_clean':[],
       'fill_merged':[], 'fill_ai_unmerged':[], 'fill_flagged':[], 'raw_fill':[]}
for i, e in enumerate(ev):
    ocr = e.get('ocrDesc', '')
    if ocr:  # 需清洗类
        if i in clean_map:
            corr, fl, src = clean_map[i]
            if fl:
                cat['clean_flagged'].append(i)
            elif ocr.strip() == str(corr).strip():
                cat['clean_merged'].append(i)
            else:
                cat['clean_ai_unmerged'].append(i)
        else:
            cat['raw_clean'].append(i)
    else:     # 需补缺类
        if i in fill_map:
            fill, fl, src = fill_map[i]
            if fl:
                cat['fill_flagged'].append(i)
            elif ocr.strip() == str(fill).strip() and ocr:
                cat['fill_merged'].append(i)
            else:
                cat['fill_ai_unmerged'].append(i)
        else:
            cat['raw_fill'].append(i)

# ---- 批次完成度 ----
def batch_done(in_map, out_map, prefix):
    """返回 (已完成批, 未完成批[含输入条数])"""
    done, pending = [], []
    for bf, items in in_map.items():
        bid = re.search(r'\d+', bf).group()
        # 该批输入索引集合
        idxs = [it.get('index') for it in items if 'index' in it]
        # 是否有对应 output 覆盖
        has_out = any(i in (clean_map if prefix=='c' else fill_map) for i in idxs)
        if has_out:
            done.append((bf, len(idxs)))
        else:
            pending.append((bf, len(idxs)))
    return done, pending

cdone, cpending = batch_done(clean_in, clean_out, 'c')
fdone, fpendening = batch_done(fill_in, fill_out, 'f')

# ---- 产出统计 ----
def out_stats(out_map):
    tot = sum(len(v) for v in out_map.values())
    fl = sum(1 for items in out_map.values() for it in items if it.get('flagged'))
    return tot, fl
ctot, cfl = out_stats(clean_out)
ftot, ffl = out_stats(fill_out)

# ---- 打印 ----
print("="*64)
print(f"OCR 清洗进度盘点  (events.json 共 {N} 条)")
print("="*64)
print(f"\n【清洗批 CLEAN】")
print(f"  ✅ 产出文件(已完成, 共 {len(clean_out)} 个, 覆盖 {ctot} 条, flagged={cfl}):")
for f, items in sorted(clean_out.items()):
    print(f"     {f:16} {len(items)} 条")
print(f"  ❌ 待跑(仅有输入批、无产出): {[b+f'({n}条)' for b,n in cpending]}")
print(f"\n【补缺批 FILL】")
print(f"  ✅ 产出文件(已完成, 共 {len(fill_out)} 个, 覆盖 {ftot} 条, flagged={ffl}):")
for f, items in sorted(fill_out.items()):
    print(f"     {f:16} {len(items)} 条")
print(f"  ❌ 待跑(仅有输入批、无产出): {[b+f'({n}条)' for b,n in fpendening]}")

print(f"\n【每条事件所处阶段】")
print(f"  清洗类(有ocrDesc {len(cat['raw_clean'])+len(clean_map)} 条):")
print(f"    ✅ AI已合并进events.json : {len(cat['clean_merged'])}")
print(f"    🟡 AI产出未合并         : {len(cat['clean_ai_unmerged'])}")
print(f"    🚩 AI标flagged未合并     : {len(cat['clean_flagged'])}")
print(f"    ⚪ 仅机械/未洗(raw)      : {len(cat['raw_clean'])}")
print(f"  补缺类(原无ocrDesc {N-len(cat['raw_clean'])-len(clean_map)} 条):")
print(f"    ✅ AI补缺已合并          : {len(cat['fill_merged'])}")
print(f"    🟡 AI补缺未合并          : {len(cat['fill_ai_unmerged'])}")
print(f"    🚩 AI补缺flagged未合并   : {len(cat['fill_flagged'])}")
print(f"    ⚪ 未补缺(raw)           : {len(cat['raw_fill'])}")

# ---- 写报告 ----
rep = os.path.join(ROOT, 'scripts', 'ocr_status.md')
with open(rep, 'w', encoding='utf-8') as r:
    r.write("# OCR 清洗进度盘点\n\n")
    r.write(f"- events.json 共 **{N}** 条\n")
    r.write(f"- 清洗输出文件 {len(clean_out)} 个, 覆盖 {ctot} 条 (flagged {cfl})\n")
    r.write(f"- 补缺输出文件 {len(fill_out)} 个, 覆盖 {ftot} 条 (flagged {ffl})\n\n")
    r.write("## 批次完成度\n")
    r.write("### 清洗 CLEAN（产出文件）\n")
    for f, items in sorted(clean_out.items()):
        r.write(f"- ✅ {f}: {len(items)} 条\n")
    r.write(f"### 清洗 CLEAN（待跑，仅有输入批）\n- " + ", ".join(f"{b}({n})" for b,n in cpending) + "\n\n")
    r.write("### 补缺 FILL（产出文件）\n")
    for f, items in sorted(fill_out.items()):
        r.write(f"- ✅ {f}: {len(items)} 条\n")
    r.write(f"### 补缺 FILL（待跑，仅有输入批）\n- " + ", ".join(f"{b}({n})" for b,n in fpendening) + "\n\n")
    r.write("## 每事件阶段\n")
    for k, v in cat.items():
        r.write(f"- {k}: {len(v)} 条\n")
    if cat['clean_ai_unmerged'] or cat['clean_flagged']:
        r.write(f"\n### 清洗未合并索引\n- 未合并: {cat['clean_ai_unmerged']}\n- flagged: {cat['clean_flagged']}\n")
    if cat['fill_ai_unmerged'] or cat['fill_flagged']:
        r.write(f"\n### 补缺未合并索引\n- 未合并: {cat['fill_ai_unmerged']}\n- flagged: {cat['fill_flagged']}\n")
print(f"\n报告已写: {rep}")
