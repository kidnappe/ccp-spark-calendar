# -*- coding: utf-8 -*-
"""
星火日历 · HTML 备份同步脚本
================================
每次重新构建（或手动改完 index.html）后运行本脚本，
即可在 项目根/html-backups/ 下生成一份带「版本号 + 改动日期」的 HTML 备份。

命名规则：  index_v{版本号}_{YYYY-MM-DD}.html
  - 版本号：自动从 index.html 更新日志里的 <span class="ver">vX.Y</span> 读取
  - 日期  ：脚本运行当天的本地日期
  - 同一天同版本再次运行会覆盖（即“当天最新构建”），如需保留每次构建的历史，
    可把下方 DATE_FMT 改成带时分秒的格式（如 %Y-%m-%d_%H%M%S）。

用法：
  python scripts/sync_html_backup.py
也可指定版本（覆盖自动识别）：
  python scripts/sync_html_backup.py v1.5
"""
import os
import re
import sys
import shutil
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "index.html")
BACKUP_DIR = os.path.join(ROOT, "html-backups")

DATE_FMT = "%Y-%m-%d"  # 改成 "%Y-%m-%d_%H%M%S" 可保留每次构建历史


def detect_version():
    try:
        with open(SRC, encoding="utf-8") as f:
            html = f.read()
        m = re.search(r'class="ver">v([\d.]+)<', html)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "unknown"


def main():
    if not os.path.exists(SRC):
        print(f"[错误] 找不到源文件：{SRC}")
        sys.exit(1)

    version = sys.argv[1] if len(sys.argv) > 1 else detect_version()
    today = datetime.now().strftime(DATE_FMT)
    os.makedirs(BACKUP_DIR, exist_ok=True)

    dest_name = f"index_v{version}_{today}.html"
    dest = os.path.join(BACKUP_DIR, dest_name)
    shutil.copy2(SRC, dest)

    size_kb = os.path.getsize(dest) / 1024
    print(f"[完成] 已备份  v{version}  @ {today}")
    print(f"        源   : {SRC}")
    print(f"        目标 : {dest}  ({size_kb:.0f} KB)")
    print(f"        备份目录现有文件：")
    for fn in sorted(os.listdir(BACKUP_DIR)):
        print(f"          - {fn}")


if __name__ == "__main__":
    main()
