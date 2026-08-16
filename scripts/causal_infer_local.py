# -*- coding: utf-8 -*-
"""
=====================================================================
本地因果推断算法  (causal_infer_local.py)
=====================================================================
用途：仅用 index.html 内已有的 historyData 文本字段，零外部依赖、零网络，
      自动推断"谁和谁有因果关系"，产出 CAUSAL_INFERRED（算法推断边表）。

设计哲学（见《因果图外部增强方案.md》）：
  - 严格意义的"因果"无法纯靠文本算出，算法算出的本质是"强关联/相关"。
  - 因此分两层，并明确标注置信度：
      强信号 = 交叉引用：B.desc 字面提及 A 的标题关键词 → A→B（高置信）
      弱信号 = TF-IDF 文本相似：A、B 主题向量余弦相似 ≥ 阈值 → A→B（中等置信）
  - 两层都必须满足"时间方向约束"：因的日期 ≤ 果的日期。
  - 已证实层 CAUSAL（金标准）中的边不重复生成；所有推断边都标"推断"。

说明：本文件是对线上已部署算法的忠实重建（原始临时脚本已删除），
      阈值/停用词可能与线上 CAUSAL_INFERRED 有细微差异，逻辑等价。
=====================================================================

运行：python causal_infer_local.py
依赖：仅 Python 标准库（re / json / math / collections）
"""

import re
import json
import math
from collections import defaultdict


# -------------------------------------------------------------------
# 0. 工具：把 "1911-10-10" 这样的键解析成可比较的 (年,月,日) 元组
#    （注意：线上键的日/月未补零，不能直接字符串比较，必须按数值比）
# -------------------------------------------------------------------
def ktuple(k):
    y, m, d = k.split('-')
    return (int(y), int(m), int(d))


def key_of(e):
    return '%d-%d-%d' % (e['year'], e['month'], e['day'])


# -------------------------------------------------------------------
# 1. 从 index.html 抽取 historyData（事件数组）与 CAUSAL（已证实边）
#    两者键均带引号，是合法 JSON；用括号配平法稳健截取，避免误截断。
# -------------------------------------------------------------------
def _extract_bracket(html, varname, open_ch, close_ch):
    marker = 'const %s = %s' % (varname, open_ch)
    # 找到 "const VAR = [" 或 "const VAR = {" 的位置
    i = html.index('const %s = %s' % (varname, open_ch))
    i += len('const %s = %s' % (varname, open_ch)) - 1   # 指向 open_ch
    depth = 0
    for j in range(i, len(html)):
        if html[j] == open_ch:
            depth += 1
        elif html[j] == close_ch:
            depth -= 1
            if depth == 0:
                return html[i:j + 1]
    raise ValueError('未找到 %s 的闭合括号' % varname)


def load_data(html_path):
    html = open(html_path, encoding='utf-8').read()
    arr_txt = _extract_bracket(html, 'historyData', '[', ']')
    arr_txt = re.sub(r',\s*]', ']', arr_txt)      # 去掉可能的尾随逗号
    arr_txt = re.sub(r',\s*}', '}', arr_txt)
    history_data = json.loads(arr_txt)

    causal_txt = _extract_bracket(html, 'CAUSAL', '{', '}')
    causal_txt = re.sub(r',\s*]', ']', causal_txt)
    causal_txt = re.sub(r',\s*}', '}', causal_txt)
    verified = json.loads(causal_txt)
    return history_data, verified


# -------------------------------------------------------------------
# 2. 文本预处理
# -------------------------------------------------------------------
# 中文停用词（标题/描述里的高频无判别力词）
STOP = set(
    "的 了 在 是 和 与 及 对 为 由 等 年 月 日 中 国 后 上 下 内 外 大 小 "
    "会 会议 大会 举行 召开 通过 关于 进行 表示 指出 强调 以来 期间 "
    "成为 实现 取得 推进 发展 建设 工作 同志 同志 领导 中央 全国 全党 "
    "主义 思想 精神 决议 决定 报告 讲话 纪念 庆祝 成立 建立 开始 结束"
    .split()
)


def han_segs(text, min_len=2, max_len=4):
    """把文本切成 2~4 字的中文片段（简单、零依赖的近似分词）。"""
    text = re.sub(r'\d+', '', text)               # 去掉年份数字，避免"1911"之类干扰
    text = re.sub(r'\s+', '', text)
    segs = re.findall(r'[一-鿿]+', text)
    out = []
    for s in segs:
        n = len(s)
        for L in range(min_len, max_len + 1):
            for i in range(n - L + 1):
                out.append(s[i:i + L])
    return out


# 标题末尾的通用动词：交叉引用时 B 的 desc 常只提"辛亥革命"而非"辛亥革命爆发"，
# 故把标题末尾这类动词剥掉后再去匹配，命中率与精度更平衡。
TRAIL_VERBS = [
    '爆发', '成立', '召开', '举行', '开始', '结束', '通过', '发表', '提出', '建立',
    '宣布', '开幕', '闭幕', '启动', '实施', '胜利', '失败', '发生', '产生', '出台',
    '制定', '指示', '逝世', '去世', '诞生', '恢复', '返回', '回归', '签署', '加入',
    '获得', '实现', '完成', '召开', '爆发', '举行',
]


def candidate_phrases(e):
    """交叉引用层的候选短语：直接用"完整标题"（及剥掉末尾动词后的标题）作为短语。
    精确短语匹配比 2 字片段稳健得多，能避免'中华/成立'这类通用词把图连爆。"""
    title = e['title']
    phrases = set()
    if len(title) >= 4:
        phrases.add(title)
    t = title
    for v in TRAIL_VERBS:
        if t.endswith(v) and len(t) > len(v):
            t2 = t[: -len(v)]
            if len(t2) >= 4:
                phrases.add(t2)
            break
    return phrases


# 同质"周期会议"标记：人大/全会/党代会 之间互相相似只是同类型会议，不是因果
PERIODIC = ['人大', '全会', '党代会', '人民代表大会', '中央全会', '政协']


def is_periodic(title):
    return any(k in title for k in PERIODIC)


# -------------------------------------------------------------------
# 3. 强信号层：交叉引用检测
#    思想：若事件 B 的 desc 里"白纸黑字"出现了事件 A 的标题关键词，
#          说明原文明确点名了 A，则 A 是 B 的前因（高置信）。
#    降噪：只用"文档频率低"的关键词（rare term），过滤掉"中国/会议"
#          这类几乎出现在所有事件里的通用词，避免爆炸式误连。
# -------------------------------------------------------------------
def cross_reference_edges(events):
    # 3.1 统计每个候选短语在多少条标题里出现（文档频率 df）
    df = defaultdict(int)
    per_event_terms = []
    for a in events:
        terms = candidate_phrases(a)
        per_event_terms.append(terms)
        for t in terms:
            df[t] += 1

    # 3.2 只保留 df <= MAX_DF 的"有辨识度"短语，建立 短语 -> [事件] 倒排索引
    MAX_DF = 5
    inv = defaultdict(list)
    for a, terms in zip(events, per_event_terms):
        for t in terms:
            if df[t] <= MAX_DF:
                inv[t].append(a)

    # 3.3 扫描每条事件的 desc，命中倒排短语即生成强边（满足时间方向）
    edges = []
    seen = set()
    for b in events:
        for t, alist in inv.items():
            if t in b['desc']:
                for a in alist:
                    if key_of(a) == key_of(b):
                        continue
                    if ktuple(key_of(a)) <= ktuple(key_of(b)):   # 时间方向约束
                        pair = (key_of(a), key_of(b))
                        if pair not in seen:
                            seen.add(pair)
                            edges.append((pair[0], pair[1], 'strong'))
    return edges


# -------------------------------------------------------------------
# 4. 弱信号层：TF-IDF 文本相似度
#    思想：把每条事件的正文（标题+描述）向量化，算两两余弦相似；
#          相似度高且时间在前的，推断为可能因果（中等置信）。
#    特征：中文零依赖分词用"字符二元组(char-bigram)"，对中文稳健。
#    降噪：阈值 0.28；且排除"两头都是周期会议"的同质配对。
# -------------------------------------------------------------------
def char_bigrams(text):
    text = re.sub(r'\s+', '', text)
    text = re.sub(r'[^\u4e00-\u9fffA-Za-z0-9]', '', text)
    return [text[i:i + 2] for i in range(len(text) - 1)]


def build_tfidf(events):
    N = len(events)
    docs = [(e['title'] + '。' + e.get('desc', '')) for e in events]
    toks = [char_bigrams(d) for d in docs]

    # 文档频率
    df = defaultdict(int)
    for t in toks:
        for w in set(t):
            df[w] += 1

    # TF-IDF 向量（dict 形式，省内存）
    vecs = []
    for t in toks:
        tf = defaultdict(int)
        for w in t:
            tf[w] += 1
        L = len(t) or 1
        v = {}
        for w, c in tf.items():
            idf = math.log((N + 1) / (df[w] + 1)) + 1.0
            v[w] = (c / L) * idf
        vecs.append(v)
    return vecs


def cosine(u, v):
    common = set(u) & set(v)
    if not common:
        return 0.0
    num = sum(u[w] * v[w] for w in common)
    nu = math.sqrt(sum(x * x for x in u.values()))
    nv = math.sqrt(sum(x * x for x in v.values()))
    if nu == 0 or nv == 0:
        return 0.0
    return num / (nu * nv)


WEAK_THR = 0.28


def tfidf_edges(events, vecs, thr=WEAK_THR):
    n = len(events)
    edges = []
    seen = set()
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if ktuple(key_of(events[i])) > ktuple(key_of(events[j])):
                continue  # 时间方向：因在前
            if is_periodic(events[i]['title']) and is_periodic(events[j]['title']):
                continue  # 排除同质周期会议配对
            s = cosine(vecs[i], vecs[j])
            if s >= thr:
                pair = (key_of(events[i]), key_of(events[j]))
                if pair not in seen:
                    seen.add(pair)
                    edges.append((pair[0], pair[1], 'weak', round(s, 3)))
    return edges


# -------------------------------------------------------------------
# 5. 合并两层 → CAUSAL_INFERRED（并排除已证实层、去重）
# -------------------------------------------------------------------
def merge_inferred(strong, weak, verified):
    out = defaultdict(list)
    seen = set()

    def add(a, b):
        if b in verified.get(a, []):     # 已证实层已有，不重复
            return
        if (a, b) in seen:
            return
        seen.add((a, b))
        out[a].append(b)

    for a, b, _k in strong:
        add(a, b)
    for a, b, _k, _s in weak:
        add(a, b)

    return {a: sorted(set(bs)) for a, bs in out.items() if bs}


# -------------------------------------------------------------------
# 6. 主流程 + 诊断输出
# -------------------------------------------------------------------
def main():
    import os
    # base = 项目根目录（scripts/ 的上一级），让输出的 index.html / json 落在根目录。
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html_path = os.path.join(base, 'index.html')

    events, verified = load_data(html_path)
    print('事件总数: %d | 已证实边(CAUSAL)键数: %d' % (len(events), len(verified)))

    # 强信号
    strong = cross_reference_edges(events)
    print('强信号(交叉引用)边数: %d' % len(strong))
    for e in strong[:8]:
        print('   strong:', e[0], '->', e[1])

    # 弱信号
    vecs = build_tfidf(events)
    weak = tfidf_edges(events, vecs)
    print('弱信号(TF-IDF相似)边数: %d' % len(weak))

    # 合并
    inferred = merge_inferred(strong, weak, verified)
    nodes = set(inferred.keys()) | set().union(*[set(v) for v in inferred.values()])
    print('推断边总数: %d | 推断涉及节点数: %d' % (sum(len(v) for v in inferred.values()), len(nodes)))

    # 写出可直接粘贴进 index.html 的字面量片段
    json_str = json.dumps(inferred, ensure_ascii=False, indent=2)
    out_path = os.path.join(base, 'CAUSAL_INFERRED_reconstructed.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(json_str)
    print('已写出重建结果 -> %s' % out_path)
    print('--- 预览前 6 条 ---')
    for i, (k, vs) in enumerate(inferred.items()):
        if i >= 6:
            break
        print('  %s: %s' % (k, vs))


if __name__ == '__main__':
    main()
