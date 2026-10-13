# Earnings Reviewer：提示词附录

这份文件是可选的动手材料。先阅读 `金融教师AI-Agent实操讲义.html`，理解每一步要解决的问题，再决定是否把下面的提示词交给自己的工具。

## 9 步操作

### 1. 先分清 Chat 和 Agent：一次回答，还是一项任务？

先用一个熟悉的例子区分两种用法：Chat 是你提出问题，模型返回一段回答；Agent 是你给出目标，系统在多个步骤中读取文件、调用工具、保存状态、检查结果，直到完成或停下。两者可以使用同一个模型，区别在于是否有任务流程、工具、共享状态、检查和停止条件。

```text
请用金融教师熟悉的例子解释 Chat 和 Agent 的区别。用同一个财报问题分别演示：一次性回答的 Chat；包含目标、步骤、工具、共享状态、检查和停止条件的 Agent。最后列出这两种方式在输入、过程、产物和责任边界上的差异。不要先搭建项目。
```

自我检查：写下一个你平时使用的 Chat 和一个 Agent，分别记录输入、步骤、工具、保存的结果、检查方式和停止条件。若只有一段回答，没有可复查的中间结果，就先把它归为 Chat。

### 2. 盘点你已经在用的智能体

先请大家列出自己已经用过的智能体，再说明它们解决什么任务。可以把 Codex、Claude Code、Cursor、Kimi Code、ZCode、WorkBuddy、Qoder、Trae，以及 OpenCode 配合 DeepSeek 都写进清单；不要求比较品牌，先看它们能否打开文件、调用工具、保存结果和重复运行。

```text
请在当前讨论中帮助学员盘点已有智能体。提示他们从自己的工具经验出发，填写 name、task、input、tools、output、check、stop。可使用 Codex、Claude Code、Cursor、Kimi Code、ZCode、WorkBuddy、Qoder、Trae 或 OpenCode + DeepSeek 作为例子，不要把品牌名称当成 Agent 能力证明。
```

自我检查：每人记录 3 个已有智能体或 Agent 用法，并为每个填写任务、输入、工具、输出和检查方式；小组再选一个，说明它和本课 Earnings Reviewer 的差别。

### 3. 先准备文件夹，保留原讲义的环境设置

解压 `byd_earnings.zip`，在 OpenCode 打开 `byd_earnings`。确认模板存在，再建立后续步骤会写入的目录。不要把 API Key 放进项目。

```text
请只做准备工作。确认当前文件夹是 byd_earnings，确认 output/byd_earnings_template.pptx 存在，建立 data/case/raw、data/case/prepared、output、skills、workflow 和 setup。测试一次写入权限后删除测试文件。不要取数、联网或生成结论。
```

自我检查：确认 `output/byd_earnings_template.pptx` 存在；建立 `data/case/raw`、`data/case/prepared`、`output`、`skills`、`workflow` 和 `setup`；测试项目可写；Key 仍在项目外。

### 4. 写一份任务契约，先固定财务口径

建立 `data/case/case_request.json`。把公司、报告期、指标、单位、公式和停止条件写进去。

```text
请在当前 byd_earnings 中建立 data/case/case_request.json。任务是整理比亚迪 002594.SZ 的 2026H1 与 2025H1 收入与利润。营业收入是核心指标，营业成本、营业利润、归母净利润和基本每股收益用于交叉核对。金额展示为亿元，EPS 保留元/股，同比公式为 (current - prior) / prior * 100。身份、期间、单位、来源或数字冲突时停止。没有共识或公告原文时，不写原因、beat/miss、earnings surprise、估值或投资建议。
```

自我检查：文件包含 `002594.SZ`、`2026H1`、`2025H1`、五项指标、金额和 EPS 单位、同比公式，以及身份、期间、单位、来源或数字冲突时的停止条件。

### 5. 从完整报告窗口提取原值

读取 `source/extraction_eval/input/report-pages-60-75.txt` 的完整窗口。现场 demo 先展示无 thinking 的定位失败，再只打开 thinking 重跑。课堂练习直接保留失败收据，并把通过的结果保存为 `workflow_state.raw_values`。

```text
读取完整的 report-pages-60-75.txt，不要先切片。请返回严格 JSON：section_name、table_name、table_pages、current_period_header、prior_period_header、unit，以及五项指标各自的 current 和 prior。区分合并利润表和母公司利润表。程序检查章节、表名、页码、单位和十个原值；通过后保存 workflow_state.raw_values，失败时停止并保留收据。
```

自我检查：通过结果找到第八节和跨 `p.67–68` 的合并利润表，保存两期表头、单位和五项指标的 current、prior，共十个原值。

### 6. 用 `convert_units` 统一展示单位

读取 `workflow_state.raw_values`。金额从千元换成亿元，除以 100000；EPS 不换算。每项都调用同一个 `convert_units` 函数，并保存 `unit_values`。

```text
读取 workflow_state.raw_values。为五项指标调用 convert_units。金额千元除以 100000 并保留两位小数，basic_eps 原样返回并标记为元/股。程序逐项检查单位和结果，保存 workflow_state.unit_values。
```

自我检查：五项单位检查通过。金额结果为 revenue 3448.15、operating_cost 2798.27、operating_profit 147.44、parent_net_profit 123.25 亿元；EPS 仍为 1.35 元/股。

### 7. 用 `calculate_yoy` 固定同比公式

读取 `workflow_state.unit_values`。每项调用 `calculate_yoy`，固定公式、两位小数和百分号格式。

```text
读取 workflow_state.unit_values。为每项调用 calculate_yoy，固定计算 (current - prior) / prior * 100，四舍五入到两位小数并返回带百分号的字符串。程序逐项比较结果，保存 workflow_state.yoy_values。
```

自我检查：五项同比检查通过：`-7.13%`、`-8.08%`、`-21.24%`、`-20.54%`、`-21.05%`。

### 8. 让固定核验决定是否生成简报

运行固定核验程序。它重新检查公司、报告期、章节、页码、十个原值、单位、五个同比和来源。通过后才生成候选简报。

```text
建立不调用模型的固定核验程序。读取 extract、units、yoy 的收据，逐项写入 expected、got、state 和 evidence。任何缺文件、身份不符、期间不符、单位不一致、数值不一致或来源冲突都返回 blocked。全部通过后才写候选简报，并标记为草稿，需要人工复核。
```

自我检查：`verification_receipt.json` 的 `status` 为 `verified`；候选简报标记为“草稿，需要人工复核”；没有证据的原因、共识比较和投资建议不出现在简报中。

### 9. 把前面的步骤接成四个 Agent

用四个 Agent 把前面的步骤连起来：`acquire` 取得证据，`calculate` 计算指标，`verify_sources` 回到 PDF 核对，`brief` 整理候选简报。它们共享同一个运行目录和同一份金融口径。

```text
请使用 workflow/workflow.json 和 workflow/run_agents.py 建立四个阶段：acquire、calculate、verify_sources、brief。每个阶段读取上一个阶段保存的文件。verify_sources 调用 workflow/verify_run.py。只有 verification_receipt.json 的 status 为 verified，brief 才能写候选简报；失败时当前阶段 blocked，后续阶段不启动。
```

自我检查：先运行 `--plan` 和 `--dry-run`，再运行正式命令。确认 `run.json` 中四个阶段都是 `passed`，`verification_receipt.json` 是 `verified`，HTML 简报标记为需要人工复核。

## 卡住时可以问

```text
请只检查当前阶段。告诉我当前阶段、已经保存的文件、失败的检查和下一步。不要删除失败收据，不要重跑已经通过的阶段，不要联网，不要读取或显示 Key。
```

## 资料边界

讲义可以用已有 Coding Agent 工具，也可以用 OpenCode + DeepSeek。密钥不写入提示词、日志、截图或项目目录。没有公告原文或分析师共识时，不写确定性原因、beat/miss 或 earnings surprise。
