# 从 Chat 到 Agent：提示词附录

这份文件是可选的动手材料。先阅读 `金融教师AI-Agent实操讲义.html`，理解每一步要解决的问题，再决定是否把下面的提示词交给自己的工具。

## 主线 8 步

### 1. 准备工作：先把课堂环境和边界固定下来

沿用原讲义的准备步骤：解压 byd_earnings，先用 OpenCode 打开正确文件夹，再确认模板、目录和凭据边界。准备工作的目的不是让模型先写一大段话，而是让后面的每个阶段都有固定的落点。

```text
我已解压 byd_earnings.zip，并在 OpenCode 中打开名为 byd_earnings 的文件夹。请先确认当前文件夹名称，并确认 output/byd_earnings_template.pptx 存在且可编辑。保留模板，不要删除或替换。

请只做准备工作：建立 data/case/raw/hithink/、data/case/raw/cninfo/、data/case/prepared/evidence/pages/、data/case/prepared/、output/、skills/a-share-earnings-reviewer/、workflow/agents/、automation/ 和 setup/。建立 README.md，说明本练习分析收入与利润，主线先使用本地报告窗口，真实 Key 不进项目。建立并删除一个测试文件，确认当前文件夹可写。完成后停止，不取数、不联网、不生成结论。
```

自我检查：在 OpenCode 中打开 byd_earnings；确认 output/byd_earnings_template.pptx 存在；建立 data/case/raw、data/case/prepared、output、skills、workflow 和 setup；确认 Key 仍保存在项目外。

### 2. 定义 Product：先把财务任务写成数据契约

最新 demo 的 Product 卡先写清使用者、五项指标、两个报告期、单位、输出和停止条件。对金融教师来说，这一步相当于先把一页简报的审阅口径写成可执行的课程要求。

```text
请在当前 byd_earnings 中建立 data/case/case_request.json 和 data/evals/product_spec.md。Product 是“业绩简报更新器”：使用者是金融专业教师；任务是把比亚迪 002594.SZ 的 2026H1 与 2025H1 整理成一页可核验的收入与利润简报。

固定五项指标：revenue、operating_cost、operating_profit、parent_net_profit、basic_eps。金额展示为亿元，EPS 保留元/股；同比公式是 (current - prior) / prior * 100。记录来源文件、页码、单位和未知项。H1 是六个月累计数；身份、期间、单位、来源或数字冲突时停止并保留证据。没有分析师共识或公告原文时，不写 beat/miss、earnings surprise、确定性原因、估值或投资建议。完成后只写文件，不取数。
```

自我检查：建立 data/case/case_request.json 或等价的 Product 文件；它包含 002594.SZ、2026H1、2025H1、五项指标、金额和 EPS 单位、同比公式、停止条件和能力边界。

### 3. 做基线：把完整报告窗口交给模型，先保留失败

demo 的第一行不是成功案例，而是一个有意保留的失败。把第 60–75 页完整窗口原样附在请求后，只要求模型找合并利润表，不预先切片，也不先给页码。

```text
请运行一次定位基线。读取 source/extraction_eval/input/report-pages-60-75.txt，把全文窗口原样附在请求末尾。使用 Qwen/Qwen3.5-4B 或同等模型，temperature=0，thinking=false，response_format=json_object。只要求模型返回 section_name、table_name、table_pages，不抽取数字，不解释。

把请求摘要、原始回答、解析后的 JSON、返回页码、运行时间和固定门禁写入 workflow/runs/locator-baseline.json。不要为模型补 p.68，也不要切片或重写输入。
```

自我检查：生成 locator-baseline 收据；保存实际请求、模型、thinking=false、完整窗口路径、原始 JSON、返回页码和 0/1 的章节或表格门禁。

### 4. 修复定位：用 thinking 同时拿到表格和十个原值

第二行只改一个关键边界：同一份完整窗口，打开 thinking，把定位要求和五项指标的原值放进同一个 JSON。模型不等程序切片，也不能猜页码。

```text
请在完整的 report-pages-60-75.txt 上运行定位与原值提取。只把 thinking 从 false 改为 true，并设置 thinking_budget=4096。返回严格 JSON，包含 section_name=第八节 财务报告、section_start_page=65、table_name=2、合并利润表、table_pages=[67,68]、current_period_header、prior_period_header、unit=千元，以及 values。values 只能有 revenue、operating_cost、operating_profit、parent_net_profit、basic_eps，每项包含 current 和 prior。区分合并利润表和母公司利润表，附注编号不是金额，basic_eps 单位是元/股。

程序检查章节、表格、单位和十个原值。通过后把原值写入 workflow/runs/locator-thinking.json 的 workflow_state.raw_values。失败时保留收据并停止，不切片、不补值。
```

自我检查：生成 locator-thinking 收据和 workflow_state.raw_values；章节、表格、两期表头和十个数字都能逐项验算；后续步骤只读取这份 state。

### 5. 加单位门禁：先看无工具失败，再调用 `convert_units`

demo 的第三、四行说明单位换算不能只写在自然语言里。先让模型直接换算，保留 1/5 的失败；再提供一个只做换算的工具，把五项逐一交给工具并固定检查返回值。

```text
请先读取 workflow_state.raw_values，运行一次没有工具的单位换算，保存 unit-baseline 收据。然后增加 convert_units 工具，工具参数为 metric、current、prior、source_unit；金额从千元换成亿元时除以 100000 并保留两位小数，basic_eps 从元/股原样返回。模型不得自己换算，五个指标各调用一次工具。

工具返回后，模型只整理相同键名的 JSON。固定检查器逐项核对五项结果，保存 workflow_state.unit_values。工具调用失败或字段不全时停下，保留已经收到的 tool call 和收据。
```

自我检查：保留 unit-baseline 收据；它应显示真实 API 只过 1/5。建立 `convert_units` 工具定义和工具收据；四项金额得到 3448.15、2798.27、147.44、123.25，EPS 保持 1.35，单位门 5/5。

### 6. 加同比门禁：先保留四舍五入错误，再调用 `calculate_yoy`

第五、六行只使用已经通过单位门禁的 `workflow_state.unit_values`。先看无工具的 4/5，再让 `calculate_yoy` 固定分母、精度和百分号格式。

```text
请读取 unit-tool 产生的 workflow_state.unit_values。先运行没有工具的同比整理，保存 yoy-baseline 收据。然后增加 calculate_yoy 工具，参数为 metric、current、prior，固定计算 (current-prior)/prior*100，四舍五入到两位小数并返回带 % 的字符串。五项分别调用一次工具，模型只负责把结果放回 JSON。

固定检查器逐项比较五项同比，保存 workflow_state.yoy_values。无工具结果和工具结果都保留，不能覆盖失败收据。
```

自我检查：保留 yoy-baseline 收据；demo 的真实 API 为 4/5，营业收入为 -7.12%。增加 `calculate_yoy` 后，五项应为 -7.13%、-8.08%、-21.24%、-20.54%、-21.05%，保存 `workflow_state.yoy_values`。

### 7. 把模型输出交给固定检查，再生成候选简报

前面的模型输出还不是交付物。固定程序要重新检查身份、报告期、章节、表格、十个原值、单位、五个同比、来源和证据状态，只有通过才写候选简报。

```text
请建立一个不调用模型的固定核验程序。它读取 locator-thinking、unit-tool、yoy-tool 的收据，检查公司代码、报告期、章节、表格页、两期表头、十个原值、金额单位、EPS 单位和五个同比。

每个检查保存 expected、got、state 和 evidence。任何缺文件、状态不匹配、单位不一致、数值不一致或来源冲突都返回 BLOCK，当前阶段写 blocked，后续阶段写 pending。全部通过后才生成候选简报。简报分开写披露值、计算值、来源、未知项和人工复核事项，不写没有证据的原因、共识比较或投资建议。
```

自我检查：建立固定 grade 和停止函数；它能输出 5/5、BLOCK 或待测，并保留失败证据。通过后生成 output/比亚迪2026年半年报收入与利润简报.md 和 output/finance_brief_candidate.md，状态写成“草稿——需要人工复核”。

### 8. 最后拼起来：让四个 Agent 共享状态，固定程序决定放行

现在把前面的正确步骤放进可重复运行的工作流。四个 Agent 负责取得证据、计算、原文复核和撰写简报；共同 Skill 规定金融口径；固定控制器记录阶段、调用验证器，并决定候选 PPT 能不能更新。

```text
请把刚才的步骤拼成可重复运行的 workflow。建立四个 Agent：
1. acquire：取得同花顺原始 JSON 和巨潮全文、摘要；
2. calculate：从已冻结输入计算收入、成本、营业利润、归母净利润、EPS、毛利、毛利率和归母净利率；
3. verify_sources：回到 PDF 逐项核对五项指标，保存原文页整页截图和 source_checks.csv，并运行 workflow/verify_run.py；
4. brief：只有 receipt.status=verified 时才整理待人工复核简报。

四个 Agent 都读取 skills/a-share-earnings-reviewer。每个事件单独保存 run.json、证据副本、计算表、核对表、截图和 verification_receipt.json。文字模型可以使用 codex、DeepSeek 或其他 OpenAI-compatible provider；取数、公式、截图、验证器、阶段状态和停止条件由固定程序完成。只有 verified 收据才允许固定 PPT 更新阶段读取数据；不创建或覆盖 output/byd_earnings_approved.pptx。
```

自我检查：建立 workflow/workflow.json、skills/a-share-earnings-reviewer/SKILL.md、四个 Agent 文件和 workflow/run_agents.py。用 none provider 做一次本地预检，再按顺序运行 acquire、calculate、verify_sources、brief；确认候选 PPT 与已批准 PPT 分开。

## 进阶 2 步

UI、真实权限、报告原文和自动化属于选做内容。

### 进阶 1. 进阶：接真实证据并生成候选 PPT

主线已经验证了结构。进阶时再把本地窗口换成真实数据，并先确认公司、代码、报告期、PDF 身份和累计口径。 候选 PPT 只消费已经冻结并通过核验的计算表和核对表。它是供教师逐页检查的草稿，不是自动发布的结果。

```text
请使用项目外的 Hithink Finance 权限取得 002594.SZ 的 2026H1 与 2025H1 原始 JSON，并从巨潮官方来源取得半年报全文和摘要。把两份 JSON、两份 PDF、文件身份、报告期和 SHA-256 保存到本次独立 run 目录。先检查公司、证券代码、报告期、六个月累计口径和文件可读性。任何一项不符时停在 acquire，不计算，不写简报。

完成取证后继续：
请让固定 PPT 更新阶段读取本次 verified run 的 calculation.json 和 evidence/source_checks.csv，使用 output/byd_earnings_template.pptx 生成 5 页候选稿：封面与报告期、收入与利润概览、增长与盈利能力、本期主要变化、数据来源与核对。每页保留来源或计算说明，并标明“候选—需要人工复核”。不要创建或覆盖已批准 PPT。
```

自我检查：两份 Hithink JSON、两份 CNINFO PDF、报告期身份和原始文件 SHA-256 都保存到本次 run 目录；H1 仍按六个月累计处理。 只有 `verification_receipt.json` 为 verified 时才生成 5 页候选稿；`output/byd_earnings_approved.pptx` 不被创建或覆盖。

### 进阶 2. 进阶：替换模型、做展示层并接自动化

demo 的真实运行层是本地 Python runner 调用 SiliconFlow 的 Qwen/Qwen3.5-4B。学习者可以用 OpenCode + DeepSeek 编排文字，但模型更换不应改变证据、公式、工具和停止条件。 UI 只展示 Product、Approaches、Evals 和收据。先有可读文件，再做页面。页面不能取数、计算或改变状态。 最后才接查新和结果页。自动化使用明确观察名单，按 Q1 基线、H1、Q3、FY 顺序处理；没有新数据时结束，有问题时停在当前阶段。

```text
请检查 workflow/workflow.json 的 provider 配置。允许 none、codex 和 openai_compatible 三种文字整理方式。模型只生成阶段说明和简报草稿；它不能取得未经固定程序冻结的数据，不能修改 calculation.json、source_checks.csv、verification_receipt.json 或停止状态。Key 只从项目外的环境变量或凭据文件读取。

接着检查展示层：
请建立一个只读的本地页面，显示 Product、六个 Approaches、五个 Evals 和当前 run 的验证收据。浏览器只读取本地 JSON 或发送一个无凭据的 approach id；取数、工具调用、固定 grade 和停止条件留在本地 runner。页面不能把数字改成通过，也不能显示 API Key。

最后接入自动化：
请把已经验证的 workflow 接到 automation/。每天 Asia/Shanghai 02:00 检查明确观察名单，按 2026Q1、2026H1、2026Q3、2026FY 处理同一累计口径。每个事件单独保存原始 JSON、PDF、截图、五项核对、候选 PPT、简报、verification_receipt.json 和结果页更新记录。失败时停止当前阶段，后续 pending；候选稿等待人工批准，已批准稿不自动覆盖。课堂试跑可以临时用 emit_existing，结束后恢复 baseline。
```

自我检查：用 none、codex 或 openai_compatible 各做一次 dry-run；项目中没有模型 Key；同一输入得到同一套固定检查字段。 页面离线可打开；没有外部运行时请求；每个状态都来自本地收据；移动端 320px、375px 和桌面 1280px 都无横向溢出。 automation/config.json 使用 Asia/Shanghai 02:00；每个事件有独立目录和阶段状态；失败不覆盖上一次成功结果；`monitor.first_run` 试跑后恢复 baseline。

## 卡住时可以问

```text
请只检查当前阶段的输入、输出和固定门禁。告诉我：当前阶段是什么、已保存了哪些文件、哪一项检查失败、下一步应该从哪里继续。不要删除失败收据，不要重跑已经通过的阶段，不要联网，不要读取或显示任何 Key。
```

## 资料边界

主线不需要联网；真实数据扩展使用本人注册的 Hithink Finance API Key。密钥不写入提示词、日志、截图或项目目录。没有公告原文或分析师共识时，不写确定性原因、beat/miss 或 earnings surprise。
