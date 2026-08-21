#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""changelog_html.py —— 把 CHANGELOG.md 转成页面「关于 → 更新日志」用的 HTML
单一事实源：CHANGELOG.md；页面 logHTML 由构建期生成，避免双份维护。

支持的 Markdown 子集（CHANGELOG.md 实际使用的）：
  ## [v1.8] - 2026-08-21 标题        → <h4><span class="ver">v1.8</span> 标题 <small>2026-08-21</small></h4>
  ### 新增 / ### 更改 / ### 移除     → <h5>…
  - 条目                             → <li>…（自动包裹 <ul>）
  内联：**加粗** → <b>；`代码` → <code>；[文字](链接) → <a>
"""
import re


def inline(s):
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)
    return s


def md_to_log_html(md):
    """CHANGELOG.md 全文 → 更新日志面板 HTML（含「最后更新」行）。"""
    out, in_ul, first_date, started = [], False, None, False
    for raw in md.splitlines():
        s = raw.rstrip()
        st = s.strip()
        if not st:
            continue
        if st.startswith("# "):            # 文档主标题，跳过
            continue
        if st.startswith("### "):
            if in_ul: out.append("</ul>"); in_ul = False
            if started:
                out.append("<h5>" + inline(st[4:]) + "</h5>")
        elif st.startswith("## "):
            if in_ul: out.append("</ul>"); in_ul = False
            h = st[3:]
            m = re.match(r"\[(v?[\d.]+)\]\s*(?:-\s*(\d{4}-\d{2}-\d{2}(?:\s*~\s*\d{2}-\d{2})?))?\s*(.*)", h)
            if m:
                started = True
                ver, date, title = m.group(1), m.group(2) or "", m.group(3)
                if date and first_date is None:
                    first_date = date[:10]
                small = f" <small>{date}</small>" if date else ""
                out.append(f'<h4><span class="ver">{ver}</span> {inline(title)}{small}</h4>')
            else:
                out.append("<h4>" + inline(h) + "</h4>")
        elif st.startswith(("- ", "* ")):
            if not started:
                continue                     # 首个版本条目前的说明文字，跳过
            if not in_ul:
                out.append("<ul>"); in_ul = True
            out.append("<li>" + inline(st[2:]) + "</li>")
        else:
            if not started:
                continue                     # 首个版本条目前的说明文字，跳过
            if in_ul: out.append("</ul>"); in_ul = False
            out.append("<p>" + inline(st) + "</p>")
    if in_ul:
        out.append("</ul>")
    body = "\n".join(out)
    top = f'<p class="log-updated">最后更新：{first_date}</p>\n' if first_date else ""
    return top + body


def log_html_to_js_array(log_html):
    """HTML → `const logHTML = [\"...\"].join('');` 的数组字面量内容（单元素）。"""
    return "[" + json_dumps(log_html) + "]"


def json_dumps(s):
    import json
    return json.dumps(s, ensure_ascii=False)
