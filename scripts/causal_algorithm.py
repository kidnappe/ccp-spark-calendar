# -*- coding: utf-8 -*-
"""
因果算法引擎  causal_algorithm.py
================================
把"因果"建模为「事件节点 + 有向边」(因 -> 果) 的图结构，并提供一套
可复用的算法：反向边推导、传递闭包、因果链追溯、两事件间最短因果路径、
启发式候选边推断、一致性校验。

设计目标（对齐项目《因果关系跳转方案》《因果图外部增强方案》）：
- 单一方向标注：只存 causes(因->果)，causedBy 由程序反向推导，避免重复维护。
- 三层边：verified(已证实/实线) / inferred(推断/虚线) / background(弱因果背景)。
- 每个边可溯源：带 evidence(书中原句) + source(出处)，杜绝"凭空编因果"。
- 零依赖：纯标准库，可离线运行，也可被前端/构建脚本 import 复用。

事件主键约定：key = f"{year}-{month}-{day}"，例如 "1921-7-23"。
"""
import json
import re
from collections import deque, defaultdict


def make_key(year, month, day):
    """事件唯一键：年-月-日（月/日不补零，与 index.html 保持一致）。"""
    return f"{year}-{month}-{day}"


# 中文因果信号词（用于启发式推断与证据识别）
CAUSAL_KEYWORDS = [
    "标志着", "奠定了", "奠定", "由此", "促使", "引发", "导致", "拉开", "揭开",
    "宣告", "开启", "成为", "转折点", "从而", "推动了", "促进", "为.*?奠定",
    "为.*?提供", "在此基础上", "序幕", "开端", "起点", "直接原因", "根本原因",
    "导火线", "创造条件", "准备了", "做了准备", "起了.*?作用",
]


class CausalGraph:
    """因果图：节点=事件，有向边=因果(因->果)。"""

    def __init__(self, events, edges):
        self.events = events
        self.edges = edges
        self._build()

    # ---------------------------------------------------------------- 索引
    def _build(self):
        self.by_key = {}
        for e in self.events:
            k = e.get("key") or make_key(e["year"], e["month"], e["day"])
            e["key"] = k
            # 同日可能多事件，用 list 容纳
            self.by_key.setdefault(k, []).append(e)

        self.adj = defaultdict(list)    # key -> [(to_key, edge), ...]  下游(因->果)
        self.radj = defaultdict(list)   # key -> [(from_key, edge), ...] 上游(果<-因)
        self.edge_index = {}            # (from,to) -> edge
        for ed in self.edges:
            f, t = ed["from"], ed["to"]
            self.adj[f].append((t, ed))
            self.radj[t].append((f, ed))
            self.edge_index[(f, t)] = ed

    # ---------------------------------------------------------------- 查询
    def events_of(self, key):
        return self.by_key.get(key, [])

    def causes_of(self, key):
        """直接下游(本事件导致的事件)。"""
        out = []
        for t, ed in self.adj.get(key, []):
            out.extend(self.events_of(t))
        return out

    def caused_by_of(self, key):
        """直接上游(导致本事件的事件)。"""
        out = []
        for f, ed in self.radj.get(key, []):
            out.extend(self.events_of(f))
        return out

    def upstream(self, key):
        """全部祖先(向上追溯所有前因，含传递)。"""
        return self._reach(key, self.radj)

    def downstream(self, key):
        """全部后代(向下追溯所有后续，含传递)。"""
        return self._reach(key, self.adj)

    @staticmethod
    def _reach(key, rel):
        seen, q = set(), deque([key])
        while q:
            cur = q.popleft()
            for nxt, _ in rel.get(cur, []):
                if nxt not in seen:
                    seen.add(nxt)
                    q.append(nxt)
        seen.discard(key)
        return seen

    def closure(self, key):
        """因果闭包：上溯前因 + 下探后续 + 自身（用于时间轴高亮整条脉络）。"""
        s = set([key]) | self.upstream(key) | self.downstream(key)
        return s

    def path(self, from_key, to_key):
        """两事件间最短有向因果路径(BFS)。返回 [from_key, ..., to_key] 或 None。"""
        if from_key == to_key:
            return [from_key]
        prev = {from_key: None}
        q = deque([from_key])
        while q:
            cur = q.popleft()
            for nxt, _ in self.adj.get(cur, []):
                if nxt not in prev:
                    prev[nxt] = cur
                    if nxt == to_key:
                        # 回溯
                        path, node = [], to_key
                        while node is not None:
                            path.append(node)
                            node = prev[node]
                        return path[::-1]
                    q.append(nxt)
        return None

    # -------------------------------------------------- 反向边 / 字段注入
    def inject_causes(self):
        """把边的信息反向注入事件：每个事件得到 causes(下游键) 与 causedBy(上游键)。
        只写 causes；causedBy 由程序推导（单一方向标注原则）。"""
        for e in self.events:
            e["causes"] = sorted({t for t, _ in self.adj.get(e["key"], [])})
            e["causedBy"] = sorted({f for f, _ in self.radj.get(e["key"], [])})
        return self.events

    # ------------------------------------------------------------ 校验
    def validate(self, strict_verified_acyclic=True):
        """一致性校验。返回 (errors, warnings) 两个列表。"""
        errors, warnings = [], []
        # 1) 边端点必须存在
        for ed in self.edges:
            if ed["from"] not in self.by_key:
                errors.append(f"边起点缺失: {ed['from']} -> {ed['to']}")
            if ed["to"] not in self.by_key:
                errors.append(f"边终点缺失: {ed['to']} (来自 {ed['from']})")
        # 2) 时间方向：因一般应早于或等于果（允许同日）
        for ed in self.edges:
            a = self.events_of(ed["from"])
            b = self.events_of(ed["to"])
            if a and b:
                ta = a[0]
                tb = b[0]
                if (ta["year"], ta["month"], ta["day"]) > (tb["year"], tb["month"], tb["day"]):
                    warnings.append(
                        f"时间倒置(因晚于果): {ed['from']}({ta['year']}-{ta['month']}-{ta['day']}) "
                        f"-> {ed['to']}({tb['year']}-{tb['month']}-{tb['day']}) [{ed.get('tier','?')}]"
                    )
        # 3) 已证实边不应成环
        if strict_verified_acyclic:
            verified = [(e["from"], e["to"]) for e in self.edges if e.get("tier") == "verified"]
            cyc = self._find_cycle(verified)
            if cyc:
                errors.append("已证实边存在环: " + " -> ".join(cyc))
        # 4) 孤立边（端点不在任何节点）已在上文覆盖
        return errors, warnings

    @staticmethod
    def _find_cycle(edges):
        g = defaultdict(list)
        for f, t in edges:
            g[f].append(t)
        WHITE, GRAY, BLACK = 0, 1, 2
        color = defaultdict(int)
        stack = []

        def dfs(u):
            color[u] = GRAY
            stack.append(u)
            for v in g.get(u, []):
                if color[v] == GRAY:
                    # 找到环
                    idx = stack.index(v)
                    return stack[idx:] + [v]
                if color[v] == WHITE:
                    r = dfs(v)
                    if r:
                        return r
            stack.pop()
            color[u] = BLACK
            return None

        for node in list(g.keys()):
            if color[node] == WHITE:
                r = dfs(node)
                if r:
                    return r
        return None

    # ---------------------------------------------- 启发式候选边推断
    @staticmethod
    def _tokens(text):
        """中文按字符 bigram 切分，作为轻量"词向量"。"""
        text = re.sub(r"[\s，。、；：！？“”‘’（）《》\-—,.!?()]", "", text or "")
        return set(text[i:i + 2] for i in range(len(text) - 1))

    @staticmethod
    def _jaccard(a, b):
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    def infer_candidates(self, min_score=0.32, max_per_event=3):
        """启发式推断候选因果边（对齐《外部增强方案》的流水线）：
           候选对 = 时间上 A 早于 B 的事件对；信号强度 = 文本 bigram 相似度
           + 因果关键词命中加权。仅产出"本地未标注"的候选，供人工审核入库。
        返回候选列表：[{from,to,score,reason}]。"""
        # 预计算事件文本 token
        toks = {}
        kw_hit = {}
        for e in self.events:
            txt = (e.get("title", "") + "。" + e.get("desc", ""))
            toks[e["key"]] = self._tokens(txt)
            kw_hit[e["key"]] = any(re.search(k, txt) for k in CAUSAL_KEYWORDS)

        # 当前已存在的边（避免重复建议）
        existing = set(self.edge_index.keys())
        candidates = []
        evs = sorted(self.events, key=lambda x: (x["year"], x["month"], x["day"]))
        for i, a in enumerate(evs):
            ka = a["key"]
            ta = (a["year"], a["month"], a["day"])
            scored = []
            for b in evs[i + 1:]:
                kb = b["key"]
                tb = (b["year"], b["month"], b["day"])
                # 仅考虑 A 真正早于 B（不同日）
                if (ta[0], ta[1], ta[2]) >= (tb[0], tb[1], tb[2]):
                    continue
                if (ka, kb) in existing:
                    continue
                sim = self._jaccard(toks[ka], toks[kb])
                if sim < 0.06:
                    continue
                score = sim
                reason = f"文本相似度 {sim:.2f}"
                # 关键词加权（命中因果信号词更像因果叙述）
                if kw_hit[ka] or kw_hit[kb]:
                    score += 0.12
                    reason += " + 含因果信号词"
                # 时间相近加权（相邻几年更易有直接因果）
                yr_gap = tb[0] - ta[0]
                if yr_gap <= 3:
                    score += 0.06
                    reason += f" + 时距{yr_gap}年"
                if score >= min_score:
                    scored.append((score, kb, reason))
            scored.sort(reverse=True)
            for score, kb, reason in scored[:max_per_event]:
                candidates.append({"from": ka, "to": kb, "score": round(score, 3), "reason": reason})
        return candidates

    # ----------------------------------------------------- 可视化导出
    def to_graph_json(self):
        """导出节点+边，供前端力导向图使用（与 index.html 的 cgNodes/cgEdges 对齐）。"""
        nodes, seen = [], set()
        for ed in self.edges:
            for k in (ed["from"], ed["to"]):
                if k not in seen and k in self.by_key:
                    seen.add(k)
                    ev = self.events_of(k)[0]
                    nodes.append({
                        "id": k, "year": ev["year"], "title": ev["title"],
                        "cat": ev.get("cat", "party"),
                    })
        edges = [{"from": e["from"], "to": e["to"], "type": e.get("tier", "inferred")}
                 for e in self.edges if e["from"] in seen and e["to"] in seen]
        return {"nodes": nodes, "edges": edges}


# --------------------------------------------------------- 便捷加载器
def load_project(root="."):
    """从 events.json + causality.json 构建一个 CausalGraph。"""
    with open(f"{root}/events.json", encoding="utf-8") as f:
        events = json.load(f)["events"]
    with open(f"{root}/causality.json", encoding="utf-8") as f:
        edges = json.load(f)["edges"]
    return CausalGraph(events, edges)


if __name__ == "__main__":
    import sys, os
    # 默认指向项目根目录（scripts/ 的上一级），无需手动传参也能跑。
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    g = load_project(root)
    errs, warns = g.validate()
    print(f"事件数: {len(g.events)}  边数: {len(g.edges)}")
    print(f"校验错误: {len(errs)}  警告: {len(warns)}")
    for e in errs[:20]:
        print("  ✗", e)
    for w in warns[:20]:
        print("  ⚠", w)
