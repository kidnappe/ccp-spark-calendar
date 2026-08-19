#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ocrDesc 质量 triage（窄口径、CPU 跑、零 token 消耗）
---------------------------------------------------
目标：在 events.json 的 277 条 ocrDesc 中，用确定性规则把
「看起来干净但仍可能有问题」的条目挑出来，交给人工/模型复核。
注意：本脚本只能抓『高精度、低召回』的明显问题；
合法汉字但 OCR 认错（已/己、戊/戌/戍等）无法自动判定，须靠
人工抽样或《简史》干净源文本 diff。

用法：
    python scripts/qc_ocr.py                # 扫描 events.json
    python scripts/qc_ocr.py .ocr_work/clean_00.json  # 扫描指定文件(含 items[])
输出：
    控制台打印汇总；同时写 scripts/qc_ocr_shortlist.md（待复核清单）
"""
import json, re, sys, os

TARGET = sys.argv[1] if len(sys.argv) > 1 else "events.json"

# ---------- 确定性检查规则 ----------
# C1: 嵌入拉丁串（OCR 噪声如 bd/ea/RS7/Se/wsN，须>=2字母）
RE_LATIN = re.compile(r'[a-zA-Z]{2,}')
# C1b: ASCII 杂符——只抓明显噪声，放行正文常见符号(%)、括号、引号、标点
RE_ASCII_SYM = re.compile(r'[@#$&*=|\\/~\[\]{}<>]')
# C1c: 连续 >=5 位数字（如 1971205 这类年份粘连 / 1971205年间）
RE_LONGDIGIT = re.compile(r'\d{5,}')
# C3: 过短（疑似截断/不完整）——阈值调低，避免把完整短段落误判
MIN_LEN = 20
# C4: 易混字（仅提示，不强制判错，需结合语境）
CONFUSABLE = {
    '戊': '戌/戍/戎', '戌': '戊/戍', '戍': '戊/戌', '戎': '戍/戌',
    '已': '己/巳', '己': '已/巳', '巳': '已/己',
    '末': '未', '未': '末',
    '人': '入/八', '入': '人/八', '八': '人/入',
    '赢': '羸/嬴', '羸': '赢/嬴', '嬴': '赢/羸',
    '蓝': '篮', '篮': '蓝', '概': '慨', '慨': '概',
    '籍': '藉', '藉': '籍', '候': '侯', '侯': '候',
    '崇': '祟', '祟': '崇', '管': '菅', '菅': '管',
    '徒': '徙', '徙': '徒', '茶': '荼', '荼': '茶',
    '灸': '炙', '炙': '灸', '肓': '盲', '盲': '肓',
    '栗': '粟', '粟': '栗', '塌': '榻', '榻': '塌',
    '绌': '拙', '拙': '绌', '缀': '掇', '掇': '缀',
    '蔼': '霭', '霭': '蔼', '黯': '暗', '暗': '黯',
    '辨': '辩/辫', '辩': '辨/辫', '辫': '辨/辩',
    '暄': '喧', '喧': '暄', '颍': '颖', '颖': '颍',
    '诏': '昭', '昭': '诏', '鹜': '骛', '骛': '鹜',
    '沓': '杳', '杳': '沓', '第': '弟', '弟': '第',
    '窜': '蹿', '蹿': '窜', '练': '炼', '炼': '练',
    '刚': '纲', '纲': '刚', '凌': '棱', '棱': '凌',
}

def load_items(path):
    d = json.load(open(path, encoding='utf-8'))
    if isinstance(d, dict) and 'events' in d:
        return [(i, e) for i, e in enumerate(d['events'])]
    if isinstance(d, dict) and 'items' in d:
        return [(it.get('index'), it) for it in d['items']]
    if isinstance(d, list):
        return [(i, e) for i, e in enumerate(d)]
    return []

def check(text):
    """返回 (hard_flags:list, soft_hints:list)"""
    hard, soft = [], []
    if RE_LATIN.search(text):
        hard.append('嵌入拉丁串')
    if RE_ASCII_SYM.search(text):
        hard.append('ASCII杂符')
    if RE_LONGDIGIT.search(text):
        hard.append('连续>=5位数字(年份粘连?)')
    if len(text) < MIN_LEN:
        hard.append(f'过短({len(text)}字,疑似截断)')
    # 易混字提示
    found = {}
    for ch in text:
        if ch in CONFUSABLE:
            found.setdefault(ch, CONFUSABLE[ch])
    if found:
        soft.append('易混字:' + '、'.join(f'{k}→{v}' for k, v in found.items()))
    return hard, soft

def main():
    items = load_items(TARGET)
    rows = [(idx, e.get('ocrDesc', '')) for idx, e in items if e.get('ocrDesc')]
    total = len(rows)
    hard_set, soft_set = [], []
    shortlist = []
    for idx, txt in rows:
        hard, soft = check(txt)
        if hard:
            hard_set.append(idx)
            shortlist.append((idx, 'HARD', hard, txt))
        elif soft:
            soft_set.append(idx)
            shortlist.append((idx, 'SOFT', soft, txt))
    clean = total - len(hard_set) - len(soft_set)

    print(f"扫描目标: {TARGET}")
    print(f"含 ocrDesc 条数: {total}")
    print(f"  HARD（确定有问题，必须复核）: {len(hard_set)}  -> {hard_set[:40]}")
    print(f"  SOFT（含易混字，建议复核）  : {len(soft_set)}")
    print(f"  通过所有启发式（仍仅『未验证』）: {clean}")

    # 写待复核清单
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'qc_ocr_shortlist.md')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(f"# ocrDesc 待复核清单（{TARGET}）\n\n")
        f.write(f"- 总条数: {total} | HARD: {len(hard_set)} | SOFT: {len(soft_set)} | 通过: {clean}\n\n")
        for idx, lvl, reasons, txt in shortlist:
            f.write(f"## [{lvl}] #{idx}  —— {', '.join(reasons)}\n")
            f.write(f"> {txt}\n\n")
    print(f"\n待复核清单已写: {out}")

if __name__ == '__main__':
    main()
