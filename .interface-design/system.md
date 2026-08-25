# 星火日历 · 设计系统档案（system.md）

> 本文件是界面设计的**唯一权威决策记录**。任何 AI 或人修改 UI 前，先读此文件并对齐；
> 新的设计决定产生时，更新此文件再动代码。配套技能：interface-design / impeccable。

---

## 一、设计上下文（Intent）

| 维度 | 决策 |
|---|---|
| **这个人是谁** | 党史学习者与授课教师。课堂大屏投影讲历史、通勤手机上刷“历史上的今天”、备课查证某条因果脉络 |
| **要完成的动词** | 按日期浏览事件 → 打开详情读史料六子块 → 顺因果实线延伸探索 → （工具侧）清洗/丰富史料 |
| **应该给人的感觉** | 一份装帧考究的**党报特刊摊在宣纸桌上**：庄重、温暖、有年代温度，但排版现代、交互利落。拒绝 SaaS 后台感，拒绝泛 AI 冷灰 |
| **受众禁忌** | 不做娱乐化动效堆砌；不消解历史的严肃性；红色仅作印章式点睛而非满屏渲染 |

## 二、产品域探索（Signature 的来源）

- **Domain 概念**：报刊双线报头 · 铅字小钮 · 宣纸毛边 · 朱砂印泥 · 竖排年份柱 · 序章/续章书挡 · 中轴时间卷轴 · 史料书证
- **Color world**：宣纸米黄、墨锭黑、铅灰界线、朱砂印泥红、石青（国民党系）、暖金（国家大事）
- **Signature 元素**（≥5 处复现）：① 双线报头字标 ② 朱砂实线因果脉络 vs 灰虚线背景 ③ 年份竖排柱 + 横置虚影大字 ④ 序章/续章书挡面板（tep-wm 大字水印）⑤ 搜索框/按钮的“铅字小钮”描边风格
- **要规避的默认**：Inter/system 字体、冷灰 SaaS 卡片栅格、蓝紫渐变、万物皆圆角卡片、居中一切

## 三、色彩（Token 架构）

一切颜色溯源到以下原语，禁止凭空 hex：

| Token | 值 | 角色 |
|---|---|---|
| `--paper` | `#f0e9d8` | 页面底色（宣纸外沿） |
| `--paper-2` | `#fdfaf2` | 卡片/内容面 |
| `--ink` | `#2b2b28` | 主文字 |
| `--edge` | `#c8bd9f` | 结构边框（铅灰） |
| `--vermilion` / `--vermilion-deep` / `--vermilion-soft` | `#b22222` / `#8b1a1a` / `#e57373` | 品牌/强调/因果实线 |
| `--brand2` | `#185fa5 系` | 外链/超链接（石青） |

- 暗色主题 = **夜间档案馆**：深褐纸面同族降亮度，因果虚线换暖红，语义色微降饱和
- 配比 ≈ 60% 宣纸中性面 / 30% 结构与文字 / 10% 朱砂点睛——红色是印章，不是墙漆

## 四、深度策略（选一并贯彻）

**细边框为主 + 极轻暖调阴影**：
- 结构线 `#d6c9a8` 系细边（分隔、归属）；浮起用 `0 2px 10px rgba(90,70,40,0.12)` 级轻影
- 禁粗黑重框、禁大投影、禁玻璃拟态滥用
- 输入框略深于周围（inset 语义：“在此键入”）

## 五、排版与层级

- 字族：正文 `"Microsoft YaHei"` 系；报头/轴杆标题 `"Songti SC","SimSun","STSong"` 衬线
- 层级三杠杆并用：**字重 > 颜色 > 字号**；动态数字加 `font-variant-numeric: tabular-nums`
- 标题 `text-wrap: balance`，正文 `text-wrap: pretty`
- 密度：时间轴中轴为高密度叙事流；日历格留白呼吸——两种密度并存是有意的节奏

## 六、动效规则（全项目硬性）

1. 缓动变量：`--ease-out-quint: cubic-bezier(.22,1,.36,1)`、`--ease-expo: (.16,1,.3,1)`；**永不用 ease-in**
2. 时长 <300ms；按压 `scale(0.96~0.97)`；入场不从 scale(0)，从 ≥0.95+opacity
3. 只动 transform/opacity；**禁 `transition:all`**
4. 高频路径（搜索回车、翻页、滚轮导航）**零动画**
5. hover 全部门控 `(hover:hover) and (pointer:fine)`
6. `prefers-reduced-motion`: 保留透明度/颜色，去位移

## 七、组件规格（实测值，改版须同步此处）

### 顶部三钮（移动端右上竖排，顺序固定）
```
☰ menu   top: calc(10px + safe-area)      ← 恒为第一
日夜theme  top: calc(56px + safe-area)
rail 本年  top: calc(102px + safe-area)
```
横屏矮视口：8/50/92；≤480：menu 40×40/font18。断点：768 / 700 / 560(横) / 480。

### 搜索清除钮 `.sx`
无底无边无动效；无衬线 16px/700 墨色 `#4a3f28`；`:active` 转 `--vermilion`；
`transition:none; -webkit-tap-highlight-color:transparent;`；20×20 flex 居中 z-index:2。
暗色：`#b9ad91`。

### 弹窗（vvh 体系）
遮罩 `height: var(--vvh)`（`--vvh` 由 visualViewport 实时驱动，回退 svh→vh）；
盒 `max-height: min(92vh, calc(var(--vvh,100vh) - 16px))`；
内容底部 `padding-bottom: calc(8px + env(safe-area-inset-bottom))`。

### 时间轴桌面滚轮导航
门控：`(min-width:769px) and (hover:hover) and (pointer:fine)` —— 手机横屏不误判；
进入时间轴锁定页面竖滚，滚轮下=向未来；弹窗/因果图打开时不接管。

### 年份虚影 `.tyw`
每年段一条：以相邻两条分割线中心为界切分，绝对定位于段内中轴空白带，
横置大字（min(72px,11vw)/800，rgba(139,26,26,0.08)，dark 12%），
`overflow:hidden` 严格不越线；由 `layoutYearGhosts()` 在 renderTimeline 末尾与 resize 时计算。

### 链接 `.ev-link`
12px / `#185fa5`（dark `#7fb3e0`）/ 无下划线，hover 下划线；
文献出处与延伸阅读统一此样式，`title` 悬停显示完整 URL。

## 八、自检四问（每次 UI 改动后过一遍）

1. **Swap**：把宋体报头换成 Inter、宣纸换成冷灰——若页面毫无变化，说明这次改动没有携带设计信息
2. **Squint**：眯眼看时间轴——实线因果链与年份柱应仍构成可辨骨架
3. **Signature**：能指出签名元素在本次改动中的至少一处延续或强化
4. **Token**：新增颜色/间距是否都溯源到第三节的原语表？

## 九、已知约束与工程事实

- **单文件零依赖**：不引入外部字体/图标库；图标=内联 SVG 或字符
- `build_data.py` 只重写 index.html 的 historyData/CAUSAL/CAUSAL_INFERRED/布局四块数据——**UI/交互改动直接编辑 index.html 是安全的**，不会被构建覆盖
- 服务端响应已带 `Cache-Control:no-store`；SW 对 `/tools/` 全豁免且缓存版本 v2
- 断点体系：768 / 700 / 560(横屏矮视口) / 480；桌面判定一律 `(hover:hover) and (pointer:fine)` 叠加宽度
