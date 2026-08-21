# -*- coding: utf-8 -*-
"""合并 .ocr_work/clean_*.json 与 fill_*.json 的结果，应用到 events.json。
策略：flagged=true 的条目不应用（保持原文，等待人工核对）；flagged=false 应用修正/补写。
先备份 events.json 再写回。
结果目录：优先用 .ocr_work/清洗完成/（GUI 输出位置），否则 .ocr_work/。"""
import json, glob, os, shutil, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根（scripts 的上一级）
SRC = os.path.join(ROOT, 'events.json')
WORK = os.path.join(ROOT, '.ocr_work')
# 结果文件所在目录：清洗完成/ 优先，其次 .ocr_work/ 根
RESULT_DIR = os.path.join(WORK, '清洗完成') if os.path.isdir(os.path.join(WORK, '清洗完成')) else WORK

with open(SRC, encoding='utf-8') as f:
    data = json.load(f)
events = data['events']

clean_files = sorted(glob.glob(os.path.join(RESULT_DIR, 'clean_*.json')))
fill_files = sorted(glob.glob(os.path.join(RESULT_DIR, 'fill_*.json')))

applied_clean, skipped_clean = [], []
for cf in clean_files:
    with open(cf, encoding='utf-8') as f:
        items = json.load(f)['items']
    for it in items:
        idx = it['index']
        if idx < 0 or idx >= len(events):
            print(f"[warn] clean 越界 index {idx} in {cf}")
            continue
        if it.get('flagged'):
            skipped_clean.append((idx, it.get('note', '')))
            continue
        if it.get('corrected'):
            events[idx]['ocrDesc'] = it['corrected']
            applied_clean.append(idx)

applied_fill, skipped_fill = [], []
for ff in fill_files:
    with open(ff, encoding='utf-8') as f:
        items = json.load(f)['items']
    for it in items:
        idx = it['index']
        if idx < 0 or idx >= len(events):
            print(f"[warn] fill 越界 index {idx} in {ff}")
            continue
        if it.get('flagged'):
            skipped_fill.append((idx, it.get('note', '')))
            continue
        if it.get('filled'):
            events[idx]['ocrDesc'] = it['filled']
            events[idx]['ocrSource'] = it.get('source', '')
            applied_fill.append(idx)

# 备份 + 写回（统一备份到 backups/）
ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
BAK_DIR = os.path.join(ROOT, 'backups')
os.makedirs(BAK_DIR, exist_ok=True)
bak = os.path.join(BAK_DIR, f'events.json.bak-apply-{ts}')
shutil.copy2(SRC, bak)
with open(SRC, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"清洗应用: {len(applied_clean)} 条（跳过 flagged {len(skipped_clean)} 条）")
print(f"补缺应用: {len(applied_fill)} 条（跳过 flagged {len(skipped_fill)} 条）")
print(f"备份: {os.path.basename(bak)}")
with open(os.path.join(WORK, 'apply_report.txt'), 'w', encoding='utf-8') as f:
    f.write(f"清洗应用 {len(applied_clean)}: {applied_clean}\n")
    f.write(f"清洗跳过 {len(skipped_clean)}: {skipped_clean}\n")
    f.write(f"补缺应用 {len(applied_fill)}: {applied_fill}\n")
    f.write(f"补缺跳过 {len(skipped_fill)}: {skipped_fill}\n")
print(f"报告: {os.path.join(WORK, 'apply_report.txt')}")
