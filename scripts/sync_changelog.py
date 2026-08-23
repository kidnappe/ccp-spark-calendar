#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_changelog.py —— 用 CHANGELOG.md 生成站内 changelog.json
单一事实源：CHANGELOG.md；页面「关于 → 更新日志」运行时 fetch('changelog.json') 渲染，
页面不再内嵌日志 HTML，改日志只需改 CHANGELOG.md 再跑本脚本，无需改动 index.html。
轻量（秒级），无需跑完整构建。全量构建（build_data.py）时也会自动生成同一文件。

运行：python scripts/sync_changelog.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from changelog_html import md_to_log_html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD_PATH = os.path.join(ROOT, "CHANGELOG.md")
JSON_PATH = os.path.join(ROOT, "changelog.json")


def build_changelog_json(md_text):
    """CHANGELOG.md 全文 → 页面渲染用的 changelog.json 内容（dict）。"""
    html = md_to_log_html(md_text)
    # 最后更新日期：取 html 里 <p class="log-updated">…</p> 中的日期（与页面展示一致）
    last_updated = ""
    for line in html.splitlines():
        line = line.strip()
        if line.startswith('<p class="log-updated">'):
            import re
            m = re.search(r"\d{4}-\d{2}-\d{2}", line)
            last_updated = m.group(0) if m else ""
            break
    return {"lastUpdated": last_updated, "html": html}


def write_changelog_json(md_text, path=JSON_PATH):
    """生成 changelog.json（根目录，与 index.html 同级）。返回 html 长度。"""
    data = build_changelog_json(md_text)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return len(data["html"])


def main():
    md = open(MD_PATH, encoding="utf-8").read()
    n = write_changelog_json(md)
    data = build_changelog_json(md)
    print(f"已生成 changelog.json（lastUpdated={data['lastUpdated']}，HTML {n} 字符）")
    print("页面「关于 → 更新日志」运行时加载此文件，无需再改 index.html")


if __name__ == "__main__":
    main()
