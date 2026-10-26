<div align="center">
  <img src="icons/icon-calendar-256.png" width="96" alt="星火日历" />

  # 星火日历 · 交互式党史学习网页

  **把党史事件放进一张可以查、可以连、可以讲来龙去脉的日历。**

  纯前端单文件 · 无框架 · 无构建 · PWA 离线可用

  <img src="https://img.shields.io/badge/Web-HTML5-e34f26?style=flat-square&logo=html5&logoColor=white" alt="Web" />
  <img src="https://img.shields.io/badge/build-none-555?style=flat-square" alt="无构建" />
  <img src="https://img.shields.io/badge/PWA-installable-5a0fc8?style=flat-square" alt="PWA" />
  <img src="https://img.shields.io/badge/license-MIT-2ea44f?style=flat-square" alt="MIT" />

  <a href="https://kidnappe.github.io/ccp-spark-calendar/">在线体验</a> · <a href="CHANGELOG.md">更新日志</a> · <a href="LICENSE">许可证</a>
</div>

<img src="docs/screenshots/calendar.png" width="100%" alt="星火日历界面：1911 年 10 月日历，10 月 10 日标注辛亥革命爆发" />

---

## 它是什么

星火日历是一个纯前端的党史学习工具。它把中共党史上的重要事件按真实公历日期排布，点开某一天就能看到事件详情；再把事件之间的因果关系画成一张可以聚焦、可以追溯的网络。

整个项目就是一个 `index.html`：不需要 npm install，不需要打包，也不需要后端。数据已经烘焙进页面，双击文件就能打开。

当前数据规模：**419 个事件、451 条因果边**。

---

## 它和普通日历、时间轴的区别

| | 普通日历 | 单一时间轴 | 星火日历 |
|---|---|---|---|
| 时间 | 按日期看事件 | 按年份线性排列 | 日历 + 时间轴双视图 |
| 关系 | 事件之间彼此独立 | 只能看先后 | 因果网络，区分已证实边与推断边 |
| 检索 | 关键词搜索 | 通常没有 | 关键词 + 分类筛选 |
| 讲解 | 只有标题和日期 | 只有简述 | 背景 / 意义 / 论述 / 人物 / 出处 / 延伸阅读 |
| 使用 | 需要联网 | 需要联网 | 单文件离线可用，可装成 PWA |

---

## 功能

### 日历

- 按真实公历日期排布事件，标注月份和年份。
- 左右切换年份；左侧月份导航显示每月事件数量。
- “每日一史”入口，适合课堂导入或自学。
- 事件按三类着色：中共党史、国家大事、其他力量。

### 事件详情

点击任意日期，弹窗展示：

- 事件标题、日期、简述与来源；
- 三级分类；
- 史料详情 6 个子块：背景、历史意义、重要论述、相关人物、文献出处、延伸阅读；
- 来源标记（官方 / 非官方）与核验状态。

### 因果脉络图

- 力导向 SVG 关系网络；
- 实线表示史料明确记载的因果关系，虚线表示本地文本算法推断的强关联；
- 支持聚焦某条脉络，查看前因与后续；
- 侧栏列表与图上节点联动。

### 时间轴与检索

- 横向时间线，快速定位不同历史阶段；
- 按关键词搜索事件；
- 按分类筛选；
- 关于页内置更新日志与操作指南。

### PWA

- 可安装到桌面或手机主屏幕；
- Service Worker 提供离线兜底；
- `/api` 不缓存，保证维护工具的数据实时；
- 仅 HTTPS / localhost 生效，`file://` 打开时自动跳过。

### 维护工具台

`tools/workshop.html` 把 OCR 清洗、合并应用、详情丰富三个维护工具合并成一个页面，并提供“构建 index”按钮和实时进度条。

---

## 快速开始

### 在线体验

打开 **<https://kidnappe.github.io/ccp-spark-calendar/>** 即可。支持 PWA 安装：手机或桌面浏览器打开后，通过菜单“添加到主屏幕 / 安装应用”安装，离线可用。

### 本地运行

| 方式 | 操作 | 说明 |
|---|---|---|
| 直接打开 | 双击 `index.html` | `file://` 打开，PWA 自动跳过，功能不受影响 |
| 静态服务 | `python -m http.server 8080` → 访问 `http://localhost:8080` | PWA 离线可用 |
| 维护工具 | 双击 `tools/start_workshop.bat` | 启动三合一工具台 |

> 数据已烘焙进 `index.html`，运行时不依赖 `events.json` / `causality.json`；这两个文件只在重新生成数据时才需要。
> OCR 清洗工具另需本机运行 Ollama 服务。

---

## 数据与构建

### 事实源

- `events.json`：事件库，包含事件字段、详情 6 子块与 `causes`。
- `causality.json`：因果边，`from` → `to` 表示因 → 果，`tier` 分为 `verified`（实线）与 `background`（虚线）。

### 重新生成页面

1. 编辑 `events.json` / `causality.json`；
2. 运行生成器：

```bash
python scripts/build_data.py
```

脚本会重写 `index.html` 的数据块，并预计算 SVG 布局。完整构建约 5–10 分钟。

3. 校验因果图数据：

```bash
python scripts/causal_algorithm.py
```

输出事件数、边数和校验错误数；错误数应为 0。

> 不要在 `index.html` 里手工维护数据块——每次运行 `build_data.py` 都会被覆盖。改数据请改事实源后重跑脚本。

### 事件字段

```json
{
  "key": "1921-7-23",
  "year": 1921,
  "month": 7,
  "day": 23,
  "title": "中国共产党第一次全国代表大会召开",
  "desc": "1921年7月23日中共一大在上海召开，后转嘉兴南湖……",
  "cat": "party",
  "source": "《中国共产党简史》",
  "bg": "背景……",
  "significance": "历史意义……",
  "quotes": ["重要论述……"],
  "figures": ["陈独秀", "李大钊"],
  "srcCite": ["共产党员网 https://news.12371.cn/…"],
  "furtherReading": [{ "title": "中共党史研究", "url": "http://…" }],
  "causes": ["1922-7-16", "1923-6-12"]
}
```

- 主键格式为 `年-月-日`，月日不补零，例如 `1921-7-23`。
- `cat`：`party`（中共，红）/ `nation`（国家大事，金）/ `kmt`（其他力量，蓝）。
- `causes` 只维护“因 → 果”方向；前因由页面程序反向推导。

---

## 项目结构

```text
index.html                     主程序（单文件应用，含全部样式与脚本）
events.json                    事件库（外部化事实源）
causality.json                 因果链（外部化事实源）
manifest.webmanifest           PWA 应用清单
sw.js                          PWA Service Worker（网络优先 + 离线兜底）
backups/                       工具写入事实源前的自动快照
scripts/                       数据生成、校验、清洗脚本（Python 标准库）
tools/                         维护工具台与统一本地服务
docs/                          设计文档、数据说明与预览素材
icons/                         应用图标
CHANGELOG.md                   版本更新日志
```

---

## 数据来源与边界

- 事件内容整理自公开出版的党史史料（如《中国共产党简史》等），仅用于学习、教育和非商业用途。
- 仓库**不包含**受版权保护的原始文献（如扫描 PDF）；相关文件已在 `.gitignore` 中排除。
- 因果图中的虚线边由本地文本算法推断，不等于史学界定论；重要结论请以史料原文为准。
- 事件整理力求准确，但难免有疏漏；欢迎以 Issue / PR 勘误。

---

## 已知限制

- `index.html` 是单文件应用，体积约 1 MB；数据量大时首次打开会稍慢。
- PWA 的 Service Worker 只在 HTTPS 或 localhost 生效；`file://` 打开时没有离线缓存。
- 数据更新需要手动编辑事实源并重跑构建脚本，没有在线后台。
- 因果图的推断边是算法结果，不能替代史学考证。
- 维护工具台的 OCR 清洗依赖本机 Ollama，不是开箱即用的在线服务。

---

## 参与贡献

欢迎提 Issue 指正史实、补充事件，或提交 PR 改进交互、可视化和移动端体验。

1. Fork 本仓库；
2. 创建分支（`git checkout -b feature/xxx`）；
3. 如果涉及数据，同步更新 `events.json` / `causality.json`，并重跑 `scripts/build_data.py`；
4. 发起 Pull Request。

---

## 许可证

[MIT License](LICENSE) © 2026 星火日历项目作者。

事件内容整理自公开史料，相关权利归原作者与出版方；本项目仅用于学习、教育与非商业用途。
