# 星火日历 · 交互式党史学习网页

一个**纯前端、零依赖、单文件**的党史学习工具：把中共党史上的重要事件按"日历"组织起来，
支持事件详情弹窗、因果脉络关系图、时间轴、关键词检索与分类筛选，并对移动端做了适配。

> 数据来源为公开出版的党史史料（如《中国共产党简史》等），仅作学习、教育用途。
> 项目本身（代码、交互设计、可视化方案）以 **MIT 协议**开源，详见 [LICENSE](LICENSE)。

---

## ✨ 功能特性

- **日历视图**：按真实公历日期排布事件，标注月份、年份，一眼看到"历史上的今天"。
- **事件详情**：点击任意日期，弹窗展示事件标题、描述、三级分类（中共 / 国家大事 / 其他力量），以及史料详情 6 子块（背景 / 历史意义 / 重要论述 / 相关人物 / 文献出处 / 延伸阅读）。
- **因果脉络图（Causal Graph）**：基于力导向布局的 SVG 关系网络，区分
  - **已证实边**（实线，来自史料明确记载的因果）
  - **推断边**（虚线，由本地文本算法推断的强关联）
  - 支持"聚焦某条脉络"查看前因 / 后续，以及侧栏列表联动。
- **时间轴**：横向时间线，快速定位不同历史阶段。
- **检索与筛选**：按关键词搜索事件；按分类（中共 / 国家大事 / 其他力量）筛选。
- **关于页**：内置更新日志与操作指南（弹窗 Tab 切换）。
- **PWA**：可安装到桌面、离线兜底（manifest + Service Worker；`/api` 不缓存保证工具实时；仅 HTTPS / localhost 生效，双击 `file://` 自动跳过）。
- **三合一工具台**（`tools/workshop.html`）：OCR 清洗、合并应用、详情丰富三个维护工具合并为一个页面，含「⚙️ 构建 index」一键重建与实时进度条。
## 🚀 快速开始

**在线体验（推荐）** —— GitHub Pages 已部署最新版，点开即用：

```
https://kidnappe.github.io/ccp-spark-calendar/
```

支持 **PWA 安装**：手机 / 桌面浏览器打开后，通过浏览器菜单「添加到主屏幕 / 安装应用」即可安装为独立应用，**离线可用**。

**本地运行**（任选其一）：

| 方式 | 操作 | 备注 |
|---|---|---|
| ① 最简单 | 直接双击 `index.html` | `file://` 打开，PWA 自动跳过，功能不受影响 |
| ② 静态服务 | `python -m http.server 8080` → 访问 `http://localhost:8080` | PWA 离线可用 |
| ③ 维护工具 | 双击 `tools/start_workshop.bat` | 启动三合一工具台（OCR 清洗 / 合并应用 / 详情丰富） |

> 数据已烘焙进 `index.html`，运行时不依赖 `events.json` / `causality.json`，
> 这两个文件只在**重新生成数据**时才需要。
> 维护工具（OCR 清洗）另需本机运行 Ollama 服务。

---

## 🧱 技术栈

| 层 | 说明 |
|---|---|
| 前端 | 原生 HTML + CSS + JavaScript（**单文件 `index.html`，无需打包、无框架**） |
| 数据 | `events.json`（事件库）+ `causality.json`（因果链），由 Python 脚本生成并注入 `index.html` |
| 构建 | Python 3 标准库脚本（无第三方依赖），用于数据再生与布局预计算 |
| 可视化 | 自研 SVG 力导向布局（构建期预计算坐标，运行期零布局开销） |

整个项目**不需要 npm install、不需要构建步骤**——拿到 `index.html` 直接双击即可在浏览器打开。

---

## 📁 目录结构

```
ccp-spark-calendar/
├── index.html                      # 主程序（单文件应用，含全部样式与脚本）
├── events.json                     # 事件库（外部化事实源，419 条，含详情 6 子块与 causes）
├── causality.json                  # 因果链（外部化事实源，451 条边）
├── manifest.webmanifest            # PWA 应用清单（可安装）
├── sw.js                           # PWA Service Worker（网络优先 + 离线兜底）
├── backups/                        # 统一备份目录（各工具写入 events.json 前自动快照）
├── README.md                       # 本文件
├── LICENSE                         # MIT 协议
├── .gitignore                      # 忽略私有/大文件（PDF、.ocr、备份、.workbuddy 等）
├── scripts/                        # 数据生成与校验脚本（Python 标准库）
│   ├── build_data.py               # 读取 events/causality → 重写 index.html 数据块 + 预计算布局
│   ├── build_causality.py          # 合并多源种子边 → causality.json
│   ├── build_events.py             # 合并基线事件库 + 新书片段 → events.json
│   ├── classify_rel.py             # 事件三级分类（强党史 / 国家大事 / 其他力量）产出候选清单
│   ├── causal_algorithm.py         # 因果图算法与校验（validate）
│   ├── causal_infer_local.py       # 本地文本因果推断（生成推断边）
│   ├── apply_ocr_results.py        # OCR 清洗/补缺结果合并回 events.json（写入前自动备份）
│   └── ...                         # 其余质检、清洗、图标脚本
├── tools/                          # 维护工具（三合一工作台 + 统一本地服务）
│   ├── workshop.html               # 三合一工具台（OCR 清洗 / 合并应用 / 详情丰富）
│   ├── build_workshop.py           # 由三个工具 HTML 真实 DOM 合并生成 workshop.html
│   ├── detail_server.py            # 统一本地服务（8001）：静态托管 + 全部 API + /api/build
│   ├── start_workshop.bat          # 双击启动统一服务并打开工具台（唯一入口）
│   └── ...                         # 三个工具源 HTML、OCR 服务等
└── docs/                           # 设计文档与资料
    ├── 星火日历_项目概览.md
    ├── 星火日历_续做指南.md
    ├── 因果关系跳转方案.md
    ├── 因果图外部增强方案.md
    └── assets/                     # 预览图（SVG）
```

---

## 🔄 数据再生（可选）

如果你想修改事件数据或重新生成因果图，按以下流程：

1. 编辑事实源：`events.json`（事件）与 `causality.json`（因果边）。
2. 运行生成器（脚本会自动定位项目根目录，无论从哪个目录执行都行）：

```bash
python scripts/build_data.py      # 重写 index.html 的数据块 + 预计算 SVG 布局（约 5-10 分钟）
```

   或在**工具台**页面点「⚙️ 构建 index」按钮一键执行，带实时进度条
   （构建前会自动把 `events.json` / `causality.json` 快照到 `backups/`）。

3. 校验因果图数据完整性：

```bash
python scripts/causal_algorithm.py # 输出：事件数 / 边数 / 校验错误数（应为 0）
```

> ⚠️ **不要在 `index.html` 里手工维护数据块**——每次运行 `build_data.py` 都会被覆盖。
> 改数据请改 `events.json` / `causality.json` 后重跑脚本。

### 数据格式约定

**`events.json`**

```json
{
  "meta": { "...": "..." },
  "events": [
    {
      "key": "1921-7-23",
      "year": 1921, "month": 7, "day": 23,
      "title": "中国共产党第一次全国代表大会召开",
      "desc": "1921年7月23日中共一大在上海召开，后转嘉兴南湖，宣告中国共产党正式成立……",
      "cat": "party",
      "source": "《中国共产党简史》",
      "ocrDesc": "史料原文（OCR 清洗/补写结果）……",
      "bg": "背景（80-150 字）……",
      "significance": "历史意义（80-150 字）……",
      "quotes": ["重要论述（1-3 条）……"],
      "figures": ["陈独秀", "李大钊"],
      "srcCite": ["共产党员网 https://news.12371.cn/…"],
      "furtherReading": [{ "title": "中共党史研究", "url": "http://…" }],
      "detailSource": { "site": "共产党员网", "url": "https://…" },
      "detailVerified": true,
      "causes": ["1922-7-16", "1923-6-12"]
    }
  ]
}
```

- 主键规则：事件含显式 `key` 字段（`年-月-日`，**月日不补零**，如 `1921-7-23`），与 `index.html` 内部 `keyOf()` 完全一致；`causes` / `causedBy` 亦以该格式引用其他事件。
- `cat`：`"party"`（中共，红）/ `"nation"`（国家大事，金）/ `"kmt"`（其他力量，蓝）三档。
- 详情字段（可选）：`bg` / `significance` / `quotes` / `figures` / `srcCite` / `furtherReading`（史料详情 6 子块）、`detailSource` / `detailVerified`（来源与官方/非官方标记）、`ocrDesc`（史料原文）。
- `causes`：该事件直接导致的后续事件主键数组（因 → 果，单向维护）；`causedBy`（前因）由页面程序反向推导，无需手工维护。

**`causality.json`**

```json
{
  "edges": [
    { "from": "1921-7-23", "to": "1922-7-16", "tier": "verified" },
    { "from": "1927-8-1", "to": "1928-4-28", "tier": "background" }
  ]
}
```

- `from` → `to` 表示**因 → 果**。
- `tier`：`"verified"` 进入已证实层（实线）；`"background"` 进入弱因果背景层（虚线）。

---

## 📝 版权与免责声明

- 本仓库**不包含**任何受版权保护的原始文献（如扫描 PDF），相关文件已在 `.gitignore` 中排除。
- 事件内容整理自公开出版的党史史料，力求准确；如有疏漏，欢迎以 PR 形式勘误。
- 本项目仅用于学习、教育与非商业用途。

---

## 🤝 贡献

欢迎提 Issue 指正史实、补充事件，或提交 PR 改进交互 / 可视化 / 移动端体验。

1. Fork 本仓库
2. 创建分支 (`git checkout -b feature/xxx`)
3. 提交改动（若涉及数据，请同步更新 `events.json` / `causality.json` 并重跑 `scripts/build_data.py`）
4. 发起 Pull Request

---

## 📄 开源协议

[MIT](LICENSE) © 2026 星火日历项目作者
