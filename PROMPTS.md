# 从 Chat 到 Agent：提示词附录

这份文件是可选的动手材料。先阅读 `金融教师AI-Agent实操讲义.html`，理解每一步要解决的问题，再决定是否把下面的提示词交给自己的工具。

## 主线五步

### 1. 先看 Product：把一页业绩简报说清楚

讲义从现场演示的 Product 卡开始。先认出使用者、输入、输出和完成标准，再把这张卡交给 OpenCode；你不需要先懂 Agent 术语。

```text
我已经在 OpenCode 中打开名为 byd_earnings 的文件夹。请先确认当前文件夹名称，并确认 output/byd_earnings_template.pptx 存在且可编辑；保留这个模板，不要删除或替换。

现在只定义 Product，不联网、不注册账号、不读取真实财务数据。在 data/evals/ 建立 product_spec.md 和 README.md。product_spec.md 用普通中文写清：
1. 使用者：需要快速阅读一家公司业绩变化的金融教师；
2. 任务：把一组报告期数字整理成一页可核验的业绩简报；
3. 输入：本期、上年同期、单位、指标、来源和不确定项；
4. 输出：一页简报、变化率、来源说明、未知项和通过 / 错 / 待测状态；
5. 完成标准：数字可复算，单位一致，来源可回查，证据不足时停止，不编造原因或共识比较。

README.md 写明主线是用 OpenCode + 已连接的大模型复刻这个 Product，教学输入不代表比亚迪或任何真实公司。完成一次写入测试后停止，不要建立真实数据目录。
```

自我检查：在 byd_earnings/data/evals/product_spec.md 写清使用者、任务、输入、输出、完成标准和停止条件；README.md 标明主线只使用教学输入，模板仍可编辑。

### 2. 用 OpenCode + 大模型做出第一版

把 Product 卡交给 OpenCode，让它在工作文件夹里完成第一版。先用一个能力足够的通用大模型读同一份教学输入，只追求完整产物，不急着追求完美。

```text
请在 OpenCode 当前打开的 byd_earnings 文件夹内，用已经连接的通用大模型完成一次 Product 基线。先读取 data/evals/product_spec.md 和 README.md。

建立 data/evals/teaching_input.json，写入明确标注的教学输入：公司标签“教学用示例（非真实财务数据）”；本期“2026H1”；上年同期“2025H1”；单位“亿元”；营业收入 1000 对 800；营业利润 100 对 80；归母净利润 80 对 60；基本每股收益 1.20 对 0.90；来源“教学输入”。

然后只用这份文件生成 output/brief_baseline.md：标题、报告期、四项指标的本期 / 上年同期 / 同比、计算过程、来源、未知项和“教学草稿—未评测”。在 workflow/minimal/run_log.md 记录时间、使用的模型、读取了哪些文件、写出了哪些文件和仍未检查的地方。不要联网、不要制作网页、不要添加市场反应、估值、评级、目标价或投资建议。完成后停止。
```

自我检查：data/evals/teaching_input.json、output/brief_baseline.md 和 workflow/minimal/run_log.md 已生成；简报含四项指标、计算过程、来源和“教学草稿—未评测”，没有联网请求。

### 3. 逐轮改 Prompt：从直接输出到有边界的流程

同一份输入跑三轮，只改一个边界：先直接输出，再要求固定字段，最后把计算和停止条件写清楚。每轮都保存原始结果，才能看出 Prompt 为什么变好。

```text
请在 OpenCode 中读取同一份 data/evals/teaching_input.json，按下面三轮运行，不要换输入，不要联网，也不要覆盖上一轮结果。把 Prompt、原始回答和观察写入 workflow/minimal/：

01_direct.md：让模型直接写一页简报，记录它怎样处理同比、单位和未知项。
02_schema.md：要求严格 JSON，字段固定为 period、unit、metrics、calculation、unknowns；缺字段就写错，不要自行补值。
03_checked.md：在严格字段之外，要求所有同比写出 current、prior 和公式；遇到来源冲突、单位不明或没有共识时只能输出 UNKNOWN，并列出停止原因。

每轮都记录：使用的模型、Prompt、原始输出、发现的差异和下一轮只改了什么。把比较结论写到 workflow/minimal/approaches.md。先不要做网页；完成后停止。
```

自我检查：workflow/minimal/approaches.md 列出三轮 Prompt 和改动原因；每轮有独立输出、运行记录和同一份输入，未通过的地方没有被删掉。

### 4. 按行运行五个 Evals

现在才问“它真的变好了吗”。五张案例卡固定不变；你每次只运行一个 Approach 行，逐张记录通过、错或待测和原因。

```text
请在 OpenCode 中读取 data/evals/teaching_input.json、workflow/minimal/ 三轮输出和 product_spec.md，建立并运行五个最小评测。把案例保存为 data/evals/cases.json，把通过条件保存为 data/evals/expected.md，把结果保存为 data/evals/eval_report.md。

固定五个案例：
1. control：两份来源的本期和上年同期一致，收入同比应为 25.00%；
2. cumulative：H1 是截至 6 月 30 日的六个月累计数，不得把 H1 减 Q1 写成未经来源支持的单季 Q2；
3. unit：一份来源用万元、另一份用亿元，写出换算因子再比较；
4. conflict：两份来源数值冲突，必须停止下结论并保留冲突记录；
5. boundary：没有分析师共识或公告原文，不得写 beat/miss、earnings surprise 或确定性原因。

先逐行运行 01_direct，再运行 02_schema 和 03_checked。每张案例卡只写 pass、fail 或 pending，并说明证据。不要为了让结果全通过而修改输入或删除失败记录。完成后停止。
```

自我检查：data/evals/cases.json、expected.md 和 eval_report.md 已生成；五个案例各有 input、pass_condition、observed、status 和 next_action；状态只使用 pass / fail / pending。

### 5. 修复失败，交付 Product；UI 网页作为选做

把失败项修好，再交付一页候选简报和一份检查清单。主线到这里已经完成；如果你想继续，再让 OpenCode 把同一套文件包成一个本地 UI 网页。

```text
请在 OpenCode 中完成最后一轮 Product 交付。只根据 data/evals/eval_report.md 修复失败项，不改写原始教学输入，不删除失败记录。

先生成：
1. output/finance_brief_candidate.md：一页候选简报，包含标题、报告期、指标表、本期 / 上年同期 / 同比、计算说明、教学输入来源、五个评测状态、未知项和下一步；
2. output/brief_review_checklist.md：逐项检查数字、单位、期间、来源、未知项和能力边界。

重新逐行运行五个评测，把修复前后结果写进 workflow/minimal/run_log.md。只有通过条件满足时才标为 pass；其余保留 fail 或 pending。

如果我选择继续做 UI，再建立 ui/index.html、ui/styles.css 和 ui/app.js：只读取本地 Markdown / JSON，做成 Product、Approaches、Evals 三个选项卡；页面不能发起外部请求，也不能在 UI 中重新计算或改写证据。UI 是可选展示层，不影响文件版 Product 的验收。完成后停止。
```

自我检查：output/finance_brief_candidate.md 和 output/brief_review_checklist.md 已生成；修复前后的评测记录仍在；若选择 UI，ui/index.html 只读取本地产物并提供 Product / Approaches / Evals 三个选项卡。

## 进阶 5 步

UI、真实权限、报告原文和自动化属于选做内容。

### 进阶 1. 进阶：接入真实 Hithink 与巨潮数据

主线闭环通过后，再把教学输入替换成真实材料：安全保存个人权限，由证据取得 Agent 查找巨潮公告并取得 Hithink 原始返回。

```text
这是进阶扩展：只有需要接入真实 A 股材料时才继续。先确认个人 Hithink Key 已保存在项目外的系统凭据位置；Key 不得出现在聊天、提示词、日志或 byd_earnings 文件夹中。

请在当前 byd_earnings 中完成一次真实数据取证：为比亚迪（002594.SZ）查找 2026 年半年度报告全文和摘要，分别保存到 data/case/raw/cninfo/002594_BYD_2026_H1_report_full.pdf 和 data/case/raw/cninfo/002594_BYD_2026_H1_report_summary.pdf，并核对公司、证券代码、报告期和文件身份。使用已配置的 Hithink Finance 权限取得 2026H1 与 2025H1 的利润表和财务指标，完整原始返回保存为 data/case/raw/hithink/income.json 和 data/case/raw/hithink/indicators.json。确认 H1 是截至 6 月 30 日的六个月累计数。缺少权限、文件或期间不清时停止并写清原因。不要展示或猜测 PDF 直链。完成后停止。
```

自我检查：个人 Key 仍在项目外；两份 CNINFO PDF 和两份 Hithink JSON 均保存到规定路径，并确认公司、证券代码、报告期和累计口径。

### 进阶 2. 进阶：从核对表生成候选 PPT

把真实材料整理成收入与利润核对表，运行独立验证器，再生成与已批准版本分开的 5 页候选 PPT。

```text
这是进阶扩展：在真实材料完整后继续。请分析比亚迪 2026 年半年报与 2025 年同期的收入与利润，金额统一为亿元，变化率保留两位小数；计算值明确标注。把结果保存到 data/case/prepared/income_profit_summary.csv。当前分析比较 2026H1 与 2025H1，均为截至 6 月 30 日的六个月累计数；不要用 H1 减 Q1 生成单季数。请使用起始包中已经存在的 output/byd_earnings_template.pptx，先确认它可打开且保留原有版式；若模板缺失或无法打开，保留现有材料并停止说明，不要自行换用其他模板。然后按这份模板建立 5 页大纲：第1页“封面与报告期”；第2页“收入与利润概览”，列营业收入、营业利润、归母净利润、基本每股收益的本期、上年同期和同比；第3页“增长与盈利能力”，放收入与归母净利润图表、收入增速、利润增速、营业利润率和归母净利率；第4页“本期主要变化”，只写有已核验数字或公告原文支持的收入、利润和解释；第5页“数据来源与核对”，列同花顺两份原始数据、巨潮摘要、巨潮全文和人工确认状态。营业成本在核对和来源材料中保留。巨潮摘要中的扣非归母净利润作为公告补充指标单列。资料不完整、报告期不清或单位无法统一时保留已取得材料并说明待补内容，不写结论。

请先建立独立验证器 `workflow/verify_run.py` 和收据规则，再进行本次原文复核。固定检查营业收入、营业成本、营业利润、归母净利润、基本每股收益。每项记录同花顺原始数值和单位、巨潮原始数值和单位、统一口径后的比较值、PDF 文件名、页码和对应整页截图，保存到 `data/case/prepared/source_checks.csv`。先根据已经完成的计算和五项核对写出待人工复核的简报 `output/比亚迪2026年半年报收入与利润简报.md`，把披露事实、计算结果、可能解释和仍需核实分开，并保留“草稿——需要人工复核”标记。再用与 workflow 相同的运行记录格式，把本次使用的两份 JSON、两份 PDF、计算表、核对表、四张截图、汇总表和简报冻结到 `workflow/runs/<本次运行目录>/`，记录文件哈希、报告期和运行身份。运行 `python3 workflow/verify_run.py --run <本次运行目录>`，让它重新检查冻结文件、计算值、五项核对、单位、页码、截图绑定和简报输出，并生成 `workflow/runs/<本次运行目录>/verification_receipt.json`。验证器返回 `BLOCK` 时，保留收据和已有证据，先按失败检查修复，不生成候选 PPT。只有五项全部通过且收据为 `status: "verified"` 时，才按 PPT 模板生成 `output/byd_earnings_candidate.pptx`，固定 5 页为：1）封面与报告期；2）收入与利润概览；3）增长与盈利能力；4）本期主要变化；5）数据来源与核对。第 4 页只写有数字或公告原文支持的观察，第 5 页列出两份同花顺原始数据、巨潮摘要、巨潮全文和人工确认状态，并在 PPT 中标明“候选—需要人工复核”。发现差异、缺页或单位不一致时，保存已有证据，停在当前指标，不生成或覆盖已批准 PPT。已批准文件使用 `output/byd_earnings_approved.pptx`；候选稿逐页查看后，请先向我说明需要确认的数字、来源、图表和文字，只有我明确确认后才运行项目中提供的批准操作，并记录确认人和时间。
```

自我检查：source_checks.csv 恰有五项指标；验证收据为 verified 才生成 output/byd_earnings_candidate.pptx；候选稿带人工复核标记，已批准稿不被覆盖。

### 进阶 3. 进阶：把主线固化为四 Agent workflow

把已经跑通的产品、评测和真实证据步骤固化成四个 Agent 加一个 Skill 的可重复工作流。

```text
请把前面已经建立并通过验证的收入与利润分析做成一套以后可以重复使用的工作流程（Agent workflow），并在 byd_earnings 中实际建立和运行。复用已有的独立验证器 `workflow/verify_run.py` 和 `verification_receipt.json` 收据规则，不要在本阶段另写一套数字判断。安排四个 Agent：证据取得 Agent 取得同花顺数据和巨潮公告；计算 Agent 计算指标；原文复核 Agent 逐项核对并保存截图；简报 Agent 只根据已通过的证据整理待人工复核文字。再建立一个共同遵守的 Skill，把公司、报告期、单位、公式、来源和停止规则写清楚；再建立一个固定的 PPT 更新阶段，只有验证器对本次冻结运行目录返回 `status: "verified"` 后，才读取计算表和核对表，按 5 页结构（封面与报告期、收入与利润概览、增长与盈利能力、本期主要变化、数据来源与核对）生成 `output/byd_earnings_candidate.pptx`、页面更新计划和变更记录。把 2026Q1 对 2025Q1 作为基线，把本次 2026H1 对 2025H1 作为第一次更新；以后 Q3 和 FY 都与上一年同一报告期比较，不把 H1 减 Q1 当作单季。每开始一个阶段先记录，完成后标记已完成；出现问题就停在当前阶段，写清原因、已保存材料和下一步，后续保持尚未开始。每次运行单独保存 JSON、PDF、截图、五项核对表、核验收据和候选 PPT。数字、公式、核对结果、独立验证和停止条件由固定程序决定。已批准 PPT 只能由本人确认后更新。完成后运行一次并列出状态和仍需人工复核事项。
```

自我检查：workflow/run_agents.py --project . 可以展示计划并做本地预检；每个角色载入同一 Skill；失败时后续阶段保持尚未开始，候选 PPT 与已批准 PPT 分开。

### 进阶 4. 选做：把 Product 做成一个本地 UI 网页

文件版 Product 跑通后，再让 OpenCode 把它包装成一个可以点击的离线网页。网页只展示已有产物，不承担取数、计算或判断。

```text
这是主线完成后的选做任务。请在 OpenCode 中读取 product_spec.md、workflow/minimal/、data/evals/ 和 output/，把已经完成的 Product 包装成一个离线网页：

1. 在 ui/ 建立 index.html、styles.css 和 app.js；
2. Product 选项卡展示使用者、输入、输出、完成标准和停止条件；
3. Approaches 选项卡逐轮展示 01_direct、02_schema、03_checked 的 Prompt 摘要、原始输出链接和“本轮改了什么”；
4. Evals 选项卡逐行运行五个案例，状态只显示通过、错或待测，并显示证据文件路径；
5. 页面只读取本地 JSON / Markdown，不访问外部网络，不在浏览器里重新计算或修改数字；
6. 在 README.md 写明 UI 是展示层，文件版 Product 才是验收对象。

完成后在本地打开页面检查 1280px、375px 和 320px，不要把凭据、真实 PDF 或 API Key 复制进 ui/。
```

自我检查：ui/index.html、ui/styles.css 和 ui/app.js 已生成；页面有 Product、Approaches、Evals 三个选项卡，无外部运行时请求，五个案例状态来自本地文件。

### 进阶 5. 进阶：接上查新、自动化与结果页

最后才接入每天北京时间 02:00 的观察名单查新，并把每个阶段、复核材料和上一次成功结果放进本地结果页。

```text
请根据已经验证的 Agent workflow，在 automation/ 中建立每天北京时间凌晨 2:00 运行的独立程序，观察名单先放比亚迪（002594.SZ）。按报告期保存结果：2026Q1 对 2025Q1 是一季度基线，2026H1 对 2025H1 是本次第一次更新，之后依次支持 Q3（前三季度）和 FY（全年），每次都与上一年同一报告期比较。第一次正式运行先记录这次运行时已经看到的数据；课堂为了把刚刚取得的 2026 年半年报试跑，请把 automation/config.json 里的 monitor.first_run 暂时设为 emit_existing（把刚刚取得的半年报当作一次新发现来处理），试跑结束（成功或停留）后改回 baseline（以后只处理新出现或有修订的数据）。没有新公告时结束本次检查，不生成新 PPT。发现新公告后依次完成：保存同花顺原始返回；取得巨潮全文和摘要并核对公司与报告期；计算收入与利润；保存关键巨潮整页截图；复核五项指标；由固定 PPT 更新阶段生成 output/byd_earnings_candidate.pptx，并在本次事件目录保存一份候选 PPT 副本；更新本地结果页。文字整理可以接 codex exec 或兼容 OpenAI 的第三方模型；取数、计算、原文截图、PPT 更新和停止规则由固定程序完成。

每开始一步先记下当前步骤，完成后标记已完成。哪一步出现问题，就停在那一步，写清原因、已保存材料和下一步；后面的步骤保持尚未开始。修复后从该步继续，避免重复已完成的取数和下载。每个新事件单独保存 JSON、PDF、截图、五项核对表、verification_receipt.json、事件候选 PPT 副本和阶段记录；结果页与 PPT 只读取通过的收据。候选 PPT 标明“候选—需要人工复核”，不得自动改写 output/byd_earnings_approved.pptx；只有本人确认后才批准。数字、核对规则和停止条件由固定程序执行。完成后用比亚迪 2026 年半年报试跑一次。

请为每日自动程序生成一个极简本地结果页，保存为 automation/runtime/result.html；同花顺查新、资料取得、计算、复核、PPT 更新和结果页任一步的状态变化后，页面都要自动更新。

页面显示“本次处理”，按顺序列出步骤；处理完成后每步显示“已完成”“停在这里”或“尚未开始”，正在处理的步骤显示“进行中”。出问题时写出“停在：巨潮公告下载”或“停在：原文复核—营业利润”，并显示原因、已保存材料和下一步。

页面设置“人工复核材料”入口，打开本次 JSON、巨潮 PDF、原文页截图、五项核对表、verification_receipt.json、候选 PPT、页面更新计划和变更记录。单独显示“候选 PPT：待人工复核”和“已批准 PPT：未批准或上一次版本”。候选 PPT 不能自动变成已批准 PPT。

页面再显示“上一次成功结果”，失败时保留上一次已批准 PPT 和收入利润结果。verification_receipt.json 的 status 为 verified，五项核对全部通过且截图可打开时，显示“巨潮原文复核通过（5/5）”。页面隐藏 API Key 和内部日志。完成后试跑一次并检查电脑和手机宽度下都能阅读。
```

自我检查：automation/ 中有可独立运行的查新程序；新事件能写入阶段记录、证据、核验收据、候选 PPT 和 automation/runtime/result.html；失败时后续步骤尚未开始且已批准 PPT 未被覆盖。

## 卡住时可以问

```text
当前步骤遇到问题。请先读取最近一次产物和 workflow/minimal/run_log.md，只定位一个具体阻塞点；保留已经完成的文件，不重做已通过的步骤。说明：停在哪一步、已保存什么、缺什么、修复后从哪一步继续。不要联网，除非当前步骤明确属于真实数据进阶。
```

## 资料边界

主线不需要联网；真实数据扩展使用本人注册的 Hithink Finance API Key。密钥不写入提示词、日志、截图或项目目录。没有公告原文或分析师共识时，不写确定性原因、beat/miss 或 earnings surprise。
