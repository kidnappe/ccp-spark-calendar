# -*- coding: utf-8 -*-
# ============================================================================
# 生成器（唯一事实源 = events.json + causality.json）
# 运行: python build_data.py
# 作用: 读取 events.json(事件库) 与 causality.json(因果链)，
#       重写 index.html 中的 historyData / CAUSAL / CAUSAL_INFERRED 三块数据，
#       并在构建期预计算因果图力导向布局、烘焙为 CAUSAL_LAYOUT（运行期零布局开销）。
# 注意: index.html 的数据块由本脚本生成，请勿在 index.html 中手工维护数据；
#       改数据请改 events.json / causality.json 后重跑本脚本。
# ----------------------------------------------------------------------------
# 字段约定:
#   - 事件主键 = "年-月-日"（月日不补零，如 1921-7-23），与 index.html 的 keyOf 一致。
#   - 因果边 tier: "verified" -> CAUSAL(实线/已证实)；其余("background"等)-> CAUSAL_INFERRED(虚线)。
#   - 方向 = 因 -> 果；"前因"(causedBy) 由 index.html 程序反向推导。
# ============================================================================
import re, json, sys, math, random, os

# 项目根目录（scripts/ 的上一级），保证无论从哪个 cwd 运行都能定位数据文件。
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV_PATH = os.path.join(ROOT, "events.json")
CA_PATH = os.path.join(ROOT, "causality.json")
HTML_PATH = os.path.join(ROOT, "index.html")


def load():
    ev = json.load(open(EV_PATH, encoding="utf-8"))["events"]
    ca = json.load(open(CA_PATH, encoding="utf-8"))["edges"]
    return ev, ca


def key_of(e):
    # 与 index.html keyOf 完全一致：不补零
    return f"{e['year']}-{e['month']}-{e['day']}"


def build_history(ev):
    out = []
    for e in ev:
        item = {
            "month": e["month"], "day": e["day"], "year": e["year"],
            "title": e["title"], "desc": e["desc"], "cat": e.get("cat", "party"),
        }
        if e.get("source"):
            item["source"] = e["source"]
        # 史料原文（ocrDesc）与核验标记（ocrVerified/ocrFlagged）：仅当存在时透传，
        # 供详情弹窗「史料原文」区块使用；未核验事件不显示，避免脏数据上页面。
        if e.get("ocrDesc"):
            item["ocrDesc"] = e["ocrDesc"]
        if e.get("ocrVerified"):
            item["ocrVerified"] = e["ocrVerified"]
        if e.get("ocrFlagged"):
            item["ocrFlagged"] = e["ocrFlagged"]
        # 史料详情面板字段（背景/历史意义/重要论述/相关人物/文献出处/延伸阅读）：
        # 仅当存在（非空串/非空数组）时透传，供详情弹窗「史料详情」面板使用；空则不在页面出现。
        for k in ("soft", "bg", "significance", "quotes", "figures", "srcCite", "furtherReading"):
            v = e.get(k)
            if v not in (None, "", [], {}):
                item[k] = v
        out.append(item)
    return out


def build_causal_maps(ca):
    verified, inferred = {}, {}
    for e in ca:
        f, t = e["from"], e["to"]
        tier = e.get("tier", "background")
        target = verified if tier == "verified" else inferred
        target.setdefault(f, [])
        if t not in target[f]:
            target[f].append(t)
    return verified, inferred


def sort_map(m):
    # 按 (年,月,日) 时间顺序排主键，避免 "1921-10" 排在 "1921-7" 前的不直观顺序
    def keynote(k):
        y, mo, d = k.split("-")
        return (int(y), int(mo), int(d))
    return {k: m[k] for k in sorted(m, key=keynote)}


def replace_block(html, name, body):
    # name: "historyData" / "CAUSAL" / "CAUSAL_INFERRED"
    # body: 已 JSON 序列化的数组或对象字符串（不含 "const NAME = " 前缀）
    if name == "historyData":
        open_pat = r"const historyData = \["
        close_pat = r"\n\];"
        new = "const historyData = " + body + ";"
    else:
        open_pat = r"const " + re.escape(name) + r" = \{"
        close_pat = r"\n\};"
        new = "const " + name + " = " + body + ";"
    m = re.search(open_pat + r".*?" + close_pat, html, re.S)
    if not m:
        raise SystemExit(f"未找到 {name} 定义")
    return html[:m.start()] + new + html[m.end():]


def build_causal_layout(verified, inferred):
    # 复刻 index.html 原力导向 IIFE（参数/迭代/初始种子完全一致），改为构建期预计算。
    # 返回 {key: {"x": int, "y": int}}，烘焙进 index.html 的 CAUSAL_LAYOUT，运行期零布局开销。
    W, H, pad = 2200, 1500, 90
    # 复刻 cgNodes 顺序：先遍历 CAUSAL 全部键+目标，再补 CAUSAL_INFERRED 新增
    seen, nodes = set(), []
    def add(k):
        if k not in seen:
            seen.add(k); nodes.append(k)
    for k in verified:
        add(k)
        for t in verified[k]:
            add(t)
    for k in inferred:
        add(k)
        for t in inferred[k]:
            add(t)
    n = len(nodes)
    pos = []
    for i, k in enumerate(nodes):
        x = pad + (W - 2 * pad) * ((i * 0.61803398875) % 1)
        y = pad + (H - 2 * pad) * ((i * 0.7548776662) % 1)
        pos.append([x, y, 0.0, 0.0])  # x, y, vx, vy
    idx = {k: i for i, k in enumerate(nodes)}
    edges = []
    for s in verified:
        for t in verified[s]:
            edges.append((s, t))
    for s in inferred:
        for t in inferred[s]:
            edges.append((s, t))
    random.seed(20240815)
    kRep, kSpring, L, kCenter, damp = 30000, 0.02, 150, 0.008, 0.86
    print(f"开始力导向布局计算（节点 {n}，约 5-10 分钟，进度见输出）")
    for it in range(640):
        for i in range(n):
            for j in range(i + 1, n):
                dx = pos[i][0] - pos[j][0]; dy = pos[i][1] - pos[j][1]
                d2 = dx * dx + dy * dy
                if d2 < 1: d2 = 1
                d = d2 ** 0.5
                f = kRep / d2; fx = f * dx / d; fy = f * dy / d
                pos[i][2] += fx; pos[i][3] += fy
                pos[j][2] -= fx; pos[j][3] -= fy
        if (it + 1) % 80 == 0:
            print(f"布局迭代 {it + 1}/640（力导向斥力/弹簧）")
        for s, t in edges:
            a = idx[s]; b = idx[t]
            dx = pos[b][0] - pos[a][0]; dy = pos[b][1] - pos[a][1]
            d = (dx * dx + dy * dy) ** 0.5 or 1
            f = kSpring * (d - L); fx = f * dx / d; fy = f * dy / d
            pos[a][2] += fx; pos[a][3] += fy
            pos[b][2] -= fx; pos[b][3] -= fy
        for i in range(n):
            pos[i][2] += (W / 2 - pos[i][0]) * kCenter
            pos[i][3] += (H / 2 - pos[i][1]) * kCenter
            pos[i][2] *= damp; pos[i][3] *= damp
            pos[i][0] += pos[i][2]; pos[i][1] += pos[i][3]
            pos[i][0] = max(pad, min(W - pad, pos[i][0]))
            pos[i][1] = max(pad, min(H - pad, pos[i][1]))
        # 碰撞分离（含完全重合的随机微扰，避免沿固定轴卡死）
        minDist = 46
        for i in range(n):
            for j in range(i + 1, n):
                dx = pos[j][0] - pos[i][0]; dy = pos[j][1] - pos[i][1]
                d = (dx * dx + dy * dy) ** 0.5
                if d < 1e-6:
                    ang = random.random() * 6.283185307
                    dx = math.cos(ang); dy = math.sin(ang); d = 1.0
                if d < minDist:
                    push = (minDist - d) / 2; ux = dx / d; uy = dy / d
                    pos[i][0] -= ux * push; pos[i][1] -= uy * push
                    pos[j][0] += ux * push; pos[j][1] += uy * push
    # 去重叠终处理：反复碰撞分离直到最小间距达标（构建期不计运行成本，保证零重叠）
    minDist = 50
    for sep in range(6000):
        moved = False
        for i in range(n):
            for j in range(i + 1, n):
                dx = pos[j][0] - pos[i][0]; dy = pos[j][1] - pos[i][1]
                d = (dx * dx + dy * dy) ** 0.5
                if d < 1e-6:
                    ang = random.random() * 6.283185307
                    dx = math.cos(ang); dy = math.sin(ang); d = 1.0
                if d < minDist:
                    moved = True
                    push = (minDist - d) / 2; ux = dx / d; uy = dy / d
                    pos[i][0] -= ux * push; pos[i][1] -= uy * push
                    pos[j][0] += ux * push; pos[j][1] += uy * push
        if not moved:
            break
        if (sep + 1) % 500 == 0:
            print(f"间距优化 {sep + 1}/6000（节点去重叠）")
        for i in range(n):
            pos[i][0] += (W / 2 - pos[i][0]) * 0.003
            pos[i][1] += (H / 2 - pos[i][1]) * 0.003
            pos[i][0] = max(pad, min(W - pad, pos[i][0]))
            pos[i][1] = max(pad, min(H - pad, pos[i][1]))
    return {nodes[i]: {"x": round(pos[i][0]), "y": round(pos[i][1])} for i in range(n)}


def replace_layout(html, layout_json):
    # 将力导向布局烘焙进 index.html：首次替换旧 IIFE，之后幂等替换 sentinel 整块。
    block = ("// === CAUSAL_LAYOUT (由 build_data.py 构建期预计算生成，请勿手工修改) ===\n"
             "const CAUSAL_LAYOUT = " + layout_json + ";\n"
             "const causalLayout = CAUSAL_LAYOUT;")
    if "=== CAUSAL_LAYOUT" in html:
        return re.sub(r"// === CAUSAL_LAYOUT.*?const causalLayout = CAUSAL_LAYOUT;",
                      block, html, flags=re.S, count=1)
    return re.sub(r"// 力导向布局[^\n]*\nconst causalLayout = \(\(\) => \{.*?\}\)\(\);",
                  block, html, flags=re.S, count=1)


def validate(ev, ca):
    issues = []
    keys = set(key_of(e) for e in ev)
    # 1) 边端点必须存在
    for e in ca:
        if e["from"] not in keys:
            issues.append(("edge-from-missing", e["from"]))
        if e["to"] not in keys:
            issues.append(("edge-to-missing", e["to"]))
    # 2) verified 不可成环（避免因果图遍历死循环）
    verified = {e["from"]: e["to"] for e in ca if e.get("tier") == "verified"}
    seen, cur = set(), None
    for start in list(verified):
        visited = set()
        node = start
        while node in verified:
            if node in visited:
                issues.append(("verified-cycle", start))
                break
            visited.add(node)
            node = verified[node]
    # 3) 年份覆盖 1911-2026
    yrs = set(e["year"] for e in ev)
    missing = [y for y in range(1911, 2027) if y not in yrs]
    if missing:
        issues.append(("missing-years", missing))
    for k, v in issues:
        print("  [warn]", k, v)
    return issues


def main():
    ev, ca = load()
    print("事件总数:", len(ev), "| 因果边总数:", len(ca))
    validate(ev, ca)

    history = build_history(ev)
    verified, inferred = build_causal_maps(ca)
    verified = sort_map(verified)
    inferred = sort_map(inferred)

    n_v = sum(len(v) for v in verified.values())
    n_i = sum(len(v) for v in inferred.values())
    print(f"CAUSAL(verified) 节点 {len(verified)} / 边 {n_v}")
    print(f"CAUSAL_INFERRED 节点 {len(inferred)} / 边 {n_i}")

    # 构建期预计算因果图力导向布局（原运行期 IIFE 迁移至此），烘焙进 CAUSAL_LAYOUT
    layout = build_causal_layout(verified, inferred)
    pts = list(layout.values())
    min_d = min(((pts[i]["x"] - pts[j]["x"]) ** 2 + (pts[i]["y"] - pts[j]["y"]) ** 2) ** 0.5
                for i in range(len(pts)) for j in range(i + 1, len(pts)))
    print(f"CAUSAL_LAYOUT 节点 {len(pts)} / 最小间距 {min_d:.1f}px (碰撞阈值 46)")

    html = open(HTML_PATH, encoding="utf-8").read()
    html = replace_block(html, "historyData",
                        json.dumps(history, ensure_ascii=False, indent=1))
    html = replace_block(html, "CAUSAL",
                        json.dumps(verified, ensure_ascii=False, indent=1))
    html = replace_block(html, "CAUSAL_INFERRED",
                        json.dumps(inferred, ensure_ascii=False, indent=1))
    html = replace_layout(html, json.dumps(layout, ensure_ascii=False, indent=1))
    open(HTML_PATH, "w", encoding="utf-8").write(html)
    print("已重写 index.html 的 historyData / CAUSAL / CAUSAL_INFERRED / CAUSAL_LAYOUT 四块数据")


if __name__ == "__main__":
    main()
