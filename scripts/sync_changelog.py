#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_changelog.py —— 用 CHANGELOG.md 重新生成 index.html 的「关于 → 更新日志」块
轻量（秒级），无需跑完整构建。全量构建（build_data.py）时也会自动刷新同一块。

运行：python scripts/sync_changelog.py
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from changelog_html import md_to_log_html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD_PATH = os.path.join(ROOT, "CHANGELOG.md")
HTML_PATH = os.path.join(ROOT, "index.html")


def main():
    md = open(MD_PATH, encoding="utf-8").read()
    log_html = md_to_log_html(md)
    html = open(HTML_PATH, encoding="utf-8").read()
    # 替换整个 const logHTML = [ ... ].join(''); 块（该块以 ].join(''); 收尾）
    pat = r"const logHTML = \[.*?\]\.join\(''\);"
    if not re.search(pat, html, re.S):
        raise SystemExit("未找到 index.html 中的 logHTML 块")
    new = "const logHTML = [" + json.dumps(log_html, ensure_ascii=False) + "].join('');"
    html = re.sub(pat, lambda m: new, html, count=1, flags=re.S)
    open(HTML_PATH, "w", encoding="utf-8").write(html)
    print(f"已用 CHANGELOG.md 刷新页面更新日志（{len(log_html)} 字符 HTML）")


if __name__ == "__main__":
    main()
