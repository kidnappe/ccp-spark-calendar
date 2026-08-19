# 星火日历 · OCR 清洗与补漏工作指导

> 用途：指导后续会话/子代理继续完成 `events.json` 的 OCR 文本清洗与补缺工作。
> 最后更新：2026-08-18（**批量清洗已暂停，以下为冻结后的真实状态**）

---

## 一、项目背景与数据现状

**数据**：`events.json`（结构 `{"meta":{...},"events":[...]}`），共 **423 条**事件。
**字段**：每条含 `year/month/day/title/desc`，部分含 `ocrDesc`（来自《中国共产党简史》的 OCR 长文本）。

| 现状 | 数量 |
|------|------|
| 事件总数 | 423 |
| 带 `ocrDesc`（需清洗） | 277 |
| 缺 `ocrDesc`（需补写） | 146 |

**清洗重点**：修改 ocrDesc 中的**事实错误**（OCR 字形认错、乱码、数字/字母混入、人名地名史实错误）。

---

## 二、当前进度（2026-08-18，清洗工作已暂停）

### ✅ 已入库（git 已提交推送，数据安全）
- **前三轮清洗**：44 处事实错误修正（`scripts/clean_ocr.py` 的 `ERROR_MAP` 36 条规则）
- 已修正：黄百韬、杜聿明、邱清泉、林彪、辎重、鄂豫边境、莫斯科、乌兹别克斯坦、习近平、撒切尔、嫦娥一号 等
- GitHub 提交：`e3ace1c`（清洗）、`c7aab9a`（.nojekyll 修复 Pages）
- **`events.json` 与推送时一致，未被后续操作修改**

### ⏸️ 批量清洗（workflow + 子代理并行）——**该子代理并行方案在本地RTX3060‑6G硬件下存在严重token超限缺陷，已全部停止，不建议继续使用原自动子代理工作流**
- **所有子代理已中断**（0 个运行中），不再发起新批次
- **中间结果未合并**：以下文件原样保留在 `.ocr_work/`（已被 .gitignore 忽略，不入库），**未应用到 events.json**

| 类别 | 已产出文件（未应用） | 条数 |
|------|---------------------|------|
| 清洗 | clean_00/01/04/05/07/08/09/10/11/12.json | 200 |
| 补缺 | fill_f00/f01/f03/f06/f08.json | 74 |

**未完成的批次**：清洗 c02/c03/c06/c13（77 条）、补缺 f02/f04/f05/f07（72 条）——子代理在运行中被中断，无输出。
> ⚠️硬件限制说明：本地7B模型、6G显存环境，一次性传入整批JSON、完整工作文档、工具schema会触发`exceed context size`上下文溢出，原并行子代理方案不适合该硬件环境。

---

## 三、要做什么（剩余工作，按需决策执行）

### 第 0 步：人工决策（二选一）
> 注意：原 workflow+子代理并行批量方案，在 RTX3060‑6G + qwen2.5‑7B 本地环境因token超限无法稳定运行，不推荐直接复用原自动子代理工作流。

方案A【推荐，低风险】：放弃AI批量子代理处理
1. 删除 `.ocr_work/` 目录，清理全部子代理中间产物；
2. 保留已经入库的44处`ERROR_MAP`机械规则修正成果；
3. 仅依靠脚本机械清洗 + 人工修正：处理已知错配、史实日期异常条目；
4. 后续不再跑AI批量清洗/补缺。

方案B【继续剩余批次，硬件约束严格】：继续完成剩余77条清洗 +72条补缺
> ❗禁止直接使用原自动子代理并行工作流，会触发上下文token超限报错。
> ✅必须改为**小批次模式：每次仅提交1‑3条事件给大模型，禁止一次性传入完整批次JSON、完整全文工作指导文档；使用精简提示词调用本地Ollama qwen2.5:local7b；模型底层num_ctx固定3072，上层框架上下文窗口同样设置3072，不可调至4096/8192，避免显存OOM。**

若选择方案B → 执行第1‑6步；若选择方案A → 保留现状，直接跳到第3步人工处理已知异常，执行验证、重建、提交。

### 第 1 步：完成缺失批次（仅方案B执行）
- 清洗 77 条 + 补缺 72 条，**禁止使用原自动子代理并行工作流，采用小批次手工分组调用本地模型**
- 输入文件已在 `.ocr_work/`（如 `c02.json`、`f02.json`）
- **路径必须用正斜杠**（`E:/code/...`，反斜杠会被 JSON 转义破坏导致找不到文件）
- 每次仅取出1‑3条事件提交模型，不要把整个批次全部塞入prompt；不要粘贴完整本指导文档作为prompt；输出 `clean_XX.json` / `fill_XX.json`（格式见第四节）

### 第 2 步：合并应用
```bash
python scripts/apply_ocr_results.py
```
- 读取 `.ocr_work/clean_*.json` 与 `fill_*.json` 全部结果
- **flagged=true 不应用**（保持原文，记入 `.ocr_work/apply_report.txt` 待人工）
- 应用前自动备份 `events.json.bak-apply-<时间戳>`
- 补缺应用时写入 `ocrSource`（来源）字段

### 第 3 步：人工处理 flagged 项
- 读 `apply_report.txt`，逐条人工核对两类：乱码无法还原、内容与事件不符（数据错配）
- 已知数据错配：index 6、311、315（ocrDesc 与事件标题不符）
- 已知史实日期出入（子代理 note 中标注）：中山舰事件（题面 1927，实 1926）、三线建设（题面 1963，实 1964 决策）、批林批孔（题面 1974-01-01，实 1/18）、护国战争（题面 1915-12-12 为称帝日，实 12-25 云南起义）、首艘国产航母（题面 2017-6-25，实 4-26 下水）

### 第 4 步：验证
```bash
python scripts/scan_ocr_errors.py      # 错字/异常清零或减少
python -c "import json; d=json.load(open('events.json',encoding='utf-8')); print(len(d['events']))"  # =423
```

### 第 5 步：重建页面
```bash
python -u scripts/build_data.py
```
⚠️ **必须长超时（≥600000ms）**——末尾 O(n²) 力导向布局约 40s+，默认 120s 会被静默 kill。

### 第 6 步：提交推送
```
git add -A && git commit -m "..." && git push origin main
```
Pages 自动重建（1-2 分钟）：https://kidnappe.github.io/ccp-spark-calendar/

---

## 四、怎么做（工具与方法）

### 权威来源
| 来源 | 地址 |
|------|------|
| 人民网·党史资料库 | dangshi.people.com.cn |
| 中国共产党新闻网 | cpc.people.com.cn |
| 中央党史和文献研究院成果总库 | ebook.dswxyjy.org.cn |
| 中国共产党历史网 | zgdsw.org.cn |
| 共产党员网 | 12371.cn |
| 中国军网（战史） | 81.cn |

### 脚本
| 脚本 | 用途 |
|------|------|
| `scripts/clean_ocr.py` | 幂等清洗：补日期头 + ERROR_MAP 替换 + 归属修正 + 可疑标记（自动备份） |
| `scripts/scan_ocr_errors.py` | 全量异常扫描，输出报告 |
| `scripts/check_suspect.py` | 检查待入表子串出现次数与上下文（防误伤） |
| `scripts/apply_ocr_results.py` | 合并子代理结果应用到 events.json（flagged 不应用） |
| `scripts/build_data.py` | 重建 index.html（⚠️ 长超时） |

### 子代理补跑要点
- 输入：`.ocr_work/<批次>.json`；输出：`clean_<批次>.json` / `fill_<批次>.json`
- **路径用正斜杠**；每个子代理完成后必须返回：处理条数、flagged 数、主要修正概述
- 清洗输出：`{"items":[{"index":N,"corrected":"...","note":"...","flagged":bool}]}`
- 补缺输出：`{"items":[{"index":N,"filled":"...","source":"...","note":"...","flagged":bool}]}`

> ⚠️本地6G显存7B模型额外约束：
> 1. 禁止将完整批次JSON、完整本工作指导文档全部输入prompt；
> 2. 模型底层 Modelfile 设置 `PARAMETER num_ctx 3072`，上层Agent框架上下文窗口同步设置3072；
> 3. 单次处理事件数量限制：1‑3条，控制总token，规避`exceed context size`报错；
> 4. 不要开启大量工具，工具Schema会额外消耗大量token；
> 5. 出现flagged=true，不允许AI编造史实内容，交由人工查阅权威来源核对。

---

## 五、标准（质量红线）

### 清洗标准
1. **只改错误**：仅修 OCR 字形认错、乱码、数字/字母混入、人名地名史实错误。不润色、不删减、不文学加工。
2. **打标不编造**：乱码无法还原 → corrected 置空 + flagged=true；绝不臆造历史文本。
3. **机械优先**：能用确证规则修的不用 AI 猜。
4. **权威核验**：不确定的人名/数字/史实查权威源。
5. **先备份**：写回前保留 `events.json.bak-*`。
6. **保留结构**：仅错误处替换，不动叙述结构与有效内容。

### 补缺标准
1. 每条 150-400 字，客观书面语。
2. 内容：时间、背景、经过、结果、意义，只写有据内容。
3. 正文不含「据…/来源…」标注（来源放 source 字段）。
4. 检索不到 → filled 置空 + flagged=true。

### 验证清单
- [ ] scan_ocr_errors.py 对照表错字 0 残留
- [ ] events.json json.load 正常，事件数 = 423
- [ ] 无「年年/月月」artifact
- [ ] build_data.py 重建成功（长超时）
- [ ] 推送后 Pages 构建 `built`

### 防误伤
新错字入 ERROR_MAP 前先跑 `check_suspect.py` 确认无歧义。

---

## 六、遗留问题备忘

- **ocrDesc 不进页面**：build_data.py 不烘焙完整 ocrDesc 进 index.html，清洗成果沉淀在 events.json 数据层。
- **数据错配**：个别事件 ocrDesc 与标题不符（index 6、311、315），需人工校正对应关系。
- **备份/中间产物不入库**：`events.json.bak-*`、`.ocr_work/` 已 gitignore。
- **本地硬件限制备忘**：原自动并行子代理工作流不适合6G显存7B本地模型，会出现上下文token超限；如需继续AI批量处理，必须采用小分组单/少量条目调用模式。
