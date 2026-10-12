# 从Chat到Agent：金融智能体搭建入门

## 公开数据与原文复核指南

这是一份真实数据进阶指南。主线先在 `byd_earnings` 中用本地教学输入完成“产品 → 做法 → 评测 → 生成—评测—修复”的最小闭环；完成后再按本文件接入比亚迪（002594.SZ）公开证据。真实扩展沿用 2026Q1 对 2025Q1 的基线、2026H1 对 2025H1 的六个月累计比较，Q3 和 FY 继续按同一报告期比较。

主线第一步仍确认并打开 `byd_earnings` 和可编辑 PPT 模板；压缩包只含模板。主线提示词不需要网络或个人凭据。真实数据、PDF、原始 JSON、候选 PPT、workflow 和结果页属于进阶扩展，按本文件逐项建立并检查。

本文件只讲真实数据和安全边界。主讲义中的五个评测先规定什么时候应停下；进入这里以后，证据取得 Agent 先找巨潮全文和摘要并检查身份，再取得同花顺原始数据。每一步完成后查看产物，再继续。

本课使用两类证据：

- Hithink Finance（同花顺金融数据 API）用于快速取得、保存和比较结构化财务数据。
- 巨潮资讯的本期报告全文和摘要是公司的正式披露，由 Agent 从官方公开披露中取得，用于复核金额、单位、期间和页码；本次固定取得 H1 两份文件。

两类证据分别承担数据整理和原文复核的责任。出现差异时，记录差异并停止生成新简报。

## 一、解压并打开起始文件夹

先解压 `byd_earnings.zip`，再在 AI 工具中选择“打开文件夹”，选中解压后的 `byd_earnings`。其中的 `output/byd_earnings_template.pptx` 是课堂起始模板；除个人 Key 按安全要求保存在项目外，课堂取得的证据、生成的计算与复核记录、搭建的 Agent、Skill、workflow 和自动化程序都放在这里。

起始包不含数据、PDF、代码或运行记录。讲座进行到原文复核时，老师们会逐步建立出下面的目录：

```text
byd_earnings/
├── data/case/
│   ├── case_request.json
│   ├── raw/
│   │   ├── hithink/
│   │   │   ├── income.json
│   │   │   └── indicators.json
│   │   └── cninfo/
│   │       ├── 002594_BYD_2026_H1_report_full.pdf
│   │       └── 002594_BYD_2026_H1_report_summary.pdf
│   └── prepared/
│       ├── source_checks.csv
│       └── income_profit_summary.csv
├── output/
│   ├── byd_earnings_candidate.pptx
│   ├── byd_earnings_approved.pptx        （本人确认后才出现或更新）
│   └── 比亚迪2026年半年报收入与利润简报.md
└── automation/
    └── runtime/
        └── result.html
```

`income_profit_summary.csv` 和 `output/` 中的简报由分析与复核步骤生成；后面的 workflow 会把同样的过程编排起来并再次运行。`automation/runtime/result.html` 在自动化步骤中生成。

## 二、注册自己的同花顺金融数据 API

1. 打开 [同花顺金融数据 API 平台](https://fuyao.aicubes.cn/)并注册自己的账号。
2. 在[个人管理页](https://fuyao.aicubes.cn/admin)生成 API Key。
3. Key 只保存在个人凭据文件中，不进入 AI 对话、邮件、截图或群文件。
4. 使用下一节的标准位置保存，然后只检查认证状态。

API 文档入口为 [Hithink Finance API 概览](https://fuyao.aicubes.cn/docs/api-reference/overview/)。账号权限和可用额度以登录后的平台页面为准。

## 三、把 Key 保存到项目外

标准用户凭据文件如下：

| 系统 | 路径 |
|---|---|
| Windows | `%APPDATA%\hithink-finance\credentials.env` |
| macOS | `~/Library/Application Support/hithink-finance/credentials.env` |
| Linux | `${XDG_CONFIG_HOME:-~/.config}/hithink-finance/credentials.env` |

文件必须只有一行，等号右侧不加引号：

```text
HITHINK_FINANCE_API_KEY=自己的Key
```

先在 AI 对话界面输入下面的请求，让 AI 在当前文件夹中创建适合自己系统的安全保存脚本。脚本本身不得包含 Key，也不得读取后再显示 Key：

> 请在当前 `byd_earnings` 文件夹的 `setup/` 下，为我的电脑创建一个安全保存同花顺 API Key 的小工具。运行时要隐藏输入，把 Key 保存到上表对应的项目外位置；macOS 和 Linux 权限设为 `600`，Windows 只允许当前用户读取。不要向我索取 Key，不要把 Key 写入脚本、对话、命令参数或日志。请先说明将创建哪个文件，再创建并检查它。

### macOS

AI 创建并检查脚本后，双击：

```text
setup/save_hithink_key.command
```

如果系统不允许双击，在 `byd_earnings/` 目录运行：

```bash
sh setup/save_hithink_key.command
```

脚本使用隐藏输入并把文件权限设为 `600`。

### Windows

AI 创建并检查脚本后，右键下列文件并选择“使用 PowerShell 运行”：

```text
setup/save_hithink_key.ps1
```

脚本使用隐藏输入，并把文件读取权限限制为当前用户。

### Linux

先让 AI 只创建目录和空文件，并把权限设为 `600`；不要把 Key 发给 AI：

```bash
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/hithink-finance"
touch "${XDG_CONFIG_HOME:-$HOME/.config}/hithink-finance/credentials.env"
chmod 600 "${XDG_CONFIG_HOME:-$HOME/.config}/hithink-finance/credentials.env"
```

随后在本地文本编辑器中打开该文件，写入规定的一行并保存。不要用带 Key 的 `echo` 命令，因为命令可能进入终端历史记录。

### 安全检查

- Key 不在 `byd_earnings/` 或任何同步、打包、截图的目录中。
- Key 不写在命令参数、提示词、代码、Markdown、日志、压缩包或 Git 中。
- 检查只运行 `hithink-finance auth status --format json`；不要打开或打印凭据文件。
- 如果 Key 曾出现在公开位置，立刻在平台撤销，生成新 Key 并重新保存。

## 四、安装并检查 hithink-finance

可以先让自己的 AI 工具完成：

> 请检查这台电脑能否运行 hithink-finance。如果不能，请只从官方包安装，并确认版本和认证状态。不要索取、读取或显示我的 API Key。

需要手工执行时：

```bash
npm install -g @hithink-tech/hithink-finance-cli
hithink-finance version --format json
hithink-finance auth status --format json
```

若认证缺失，回到上一节，不要把 Key 写进命令。

## 参考 A：进阶取得同花顺原始数据

在 `byd_earnings/` 目录运行：

```bash
hithink-finance financials income --thscode 002594.SZ --period quarterly --limit 8 --output data/case/raw/hithink/income.json
hithink-finance financials indicators --thscode 002594.SZ --report 2026-2 --output data/case/raw/hithink/indicators.json
```

完成后检查：

- 两个文件都能打开，内容为有效数据返回；
- 公司代码为 `002594.SZ`；
- 利润表包含截至 2026 年 6 月 30 日和 2025 年 6 月 30 日的累计记录；
- 原始返回完整保留，尚未删字段、改数值或写结论。

报告期更新按 Q1→H1→Q3→FY 进行：Q1 是一季度，H1 是截至 6 月 30 日的六个月累计，Q3 是截至 9 月 30 日的前三季度累计，FY 是全年。每次与上一年同一报告期比较。`2026Q2` 在本案例的半年报利润表中表示截至 6 月 30 日的六个月累计数；不把 H1 减 Q1 当作 4—6 月单季数。

## 参考 B：进阶让 Agent 取得巨潮全文和摘要

在打开 `byd_earnings` 的 AI 对话界面中，把公司、报告期和两个本地目标位置交给 Agent：

> 请从巨潮资讯官方公开披露中找到比亚迪股份有限公司 2026 年半年度报告全文和摘要。确认证券代码为 002594、报告期截至 2026 年 6 月 30 日。把全文保存到 `data/case/raw/cninfo/002594_BYD_2026_H1_report_full.pdf`，把摘要保存到 `data/case/raw/cninfo/002594_BYD_2026_H1_report_summary.pdf`。必须使用巨潮资讯官方文件，不要使用第三方转载、网页摘要或截图；找不到、打不开或身份不符时停止并告诉我。

提示词只给 Agent 本地目标位置，不直接提供 PDF 下载链接。完成后应出现：

```text
data/case/raw/cninfo/002594_BYD_2026_H1_report_full.pdf
data/case/raw/cninfo/002594_BYD_2026_H1_report_summary.pdf
```

Agent 下载后要逐一打开并确认：公司为比亚迪股份有限公司，A 股代码为 002594，报告期截至 2026 年 6 月 30 日，两个文件分别是全文和摘要。来源或身份不确定时，程序停在“巨潮公告身份检查”，保留已下载文件和失败原因。

## 七、收入与利润的复核范围

本次讲座的固定双来源核对有五项：

1. 营业收入；
2. 营业成本；
3. 营业利润；
4. 归属于母公司股东的净利润；
5. 基本每股收益。

从营业收入和营业成本计算毛利与毛利率；从归母净利润和营业收入计算归母净利率。计算值必须写出公式并标注“计算值”。

扣非归母净利润从巨潮摘要补充，并标为“巨潮摘要披露值”。当前同花顺利润表返回没有直接提供该绝对值，因此核对表中的接口值应保留为缺失。

`data/case/prepared/source_checks.csv` 的五行应记录：同花顺原始数值与单位、巨潮原始数值与单位、统一后的两端数值、换算倍数、PDF 文件名、PDF 阅读器页码、对应的原文页截图和状态。金额统一换算为元后比较；EPS 单位为元/股。只有指标、期间、口径、单位和数值都一致时，状态才写 `passed`。

系统从本次保存的 PDF 副本中生成四张 150 DPI 整页截图：

```text
cninfo_summary_p0001.png
cninfo_summary_p0002.png
cninfo_full_p0065.png
cninfo_full_p0067.png
```

截图保留表名、期间栏、单位和指标行。运行清单记录每张图的源 PDF、页码、文件指纹、图片尺寸和生成工具。发现不一致时，系统仍写完五行核对表并保留已生成的截图，再停在出现差异的指标。

## 八、数据与写作边界

- 本讲座分析收入与利润，不把现金流、资产结构和股价表现带入主结论。
- 本案例没有分析师一致预期，不判断“超预期”或“不及预期”。
- 半年度财务报表未经审计。
- 同花顺数值与巨潮披露冲突时停止，不猜是哪个来源“应该正确”。
- 最终产出是“草稿——需要人工复核”，不自动发布，不作估值、评级或投资建议。

## 九、Kimi 套餐与本课 API 的区别

截至 2026 年 10 月 11 日，[Kimi 官方会员说明](https://www.kimi.com/help/membership/membership-overview)把同花顺等专业数据库列为各档会员的探索性功能；[Kimi Code 官方插件说明](https://www.kimi.com/code/docs/kimi-code-cli/customization/plugins)说明 Datasource 查询会消耗 Kimi Code 套餐额度。

Kimi 会员额度用于 Kimi 产品内的数据源查询。本练习中的 `hithink-finance` 命令和 `automation/` 使用本人在同花顺金融数据平台注册的 Hithink Finance API Key；Kimi 可以负责操作文件或整理文字。

## 十、把前面过程搭成 workflow

完成取数、计算、原文复核和简报后，把这四段工作搭成可运行程序。让 AI 在当前 `byd_earnings/` 中创建四个 Agent，分别负责取得证据、计算指标、复核原文和撰写简报；再创建一个供四个 Agent 共同遵守的 Skill，并用固定检查程序守住公司、期间、单位、公式和停止条件。编排顺序记录在 `workflow/workflow.json`，四个角色记录在 `workflow/agents/`，共同规则记录在 `skills/a-share-earnings-reviewer/`。

搭建完成后，可用下面的命令查看四个职责；这项查看不会联网、写文件或调用模型：

```bash
python3 workflow/run_agents.py --project . --plan
```

正式运行时，Codex 路线使用 `python3 workflow/run_agents.py --project . --provider codex`；兼容的第三方模型使用 `--provider openai_compatible`。老师们刚刚创建的编排顺序记录在 `workflow/workflow.json`，角色任务位于 `workflow/agents/`，共同规则位于 `skills/a-share-earnings-reviewer/`；固定控制器决定数字和能否继续，文字模型不能改写检查结果。

确认整套 workflow 能实际运行后，再让 AI 在当前文件夹的 `automation/` 中生成独立程序。程序按 Q1 基线→H1→Q3→FY 的报告期顺序保留每次证据：

- 每天北京时间 02:00 检查明确的观察名单；
- 首次运行建立基线；
- 发现新记录后，自动完成事件交接、同花顺证据保存、巨潮公告取得与身份检查、计算、PDF 原文提取、整页截图、五项核对、候选 PPT 更新、简报和结果页；
- 每开始一步就更新状态。出错时当前步骤标记为“停在这里”，后续步骤保持“尚未开始”；
- 修复后从该事件继续，保留已经通过检查的材料和上一次成功结果；
- 查新、去重、计算、核对和停止条件由固定程序执行；
- 文字起草可用 `codex exec` 或第三方模型，Key 不交给文字模型；
- 任何候选 PPT 或简报都不自动发布；逐页确认候选 PPT 后，才运行 `automation/approve_ppt.py --confirm` 生成或更新已批准版本；
- 每个步骤的状态变化都更新 `automation/runtime/result.html`。

这项自动化针对明确的观察名单逐家监测。公开接口尚未提供全部 A 股公告的实时公告流。

## 十一、查看自动化结果页

自动化程序在每次手动运行或 02:00 定时运行时，随步骤状态生成或更新：

```text
automation/runtime/result.html
```

用浏览器打开这个文件，依次看三个区域：

- “本次处理”按顺序列出全部步骤。出错时，页面准确写出“停在：具体步骤”、原因、已保存材料和下一个动作。
- “人工复核材料”可直接打开本次的两份同花顺 JSON、两份巨潮 PDF、四张原文页截图和五项核对表。
- “上一次成功结果”展示最近一次完成取证、计算、复核和简报的结果。本次停在中途时，该区域继续保留上一次成功结果。

`5/5` 只在当前事件与 workflow 的公司、期间和原始记录标识完全一致，核验表恰好包含营业收入、营业成本、营业利润、归母净利润和基本每股收益五项，五项全部通过且对应截图均可打开时显示。任何一项停留、不一致或缺少证据时，页面标准停留位置，不显示新的 `5/5`。

## 官方入口汇总

- [Codex](https://openai.com/codex/)
- [Claude Code](https://www.anthropic.com/claude-code)
- [Cursor](https://cursor.com/)
- [Kimi Code](https://www.kimi.com/code)
- [ZCode](https://zcode.z.ai/cn)
- [WorkBuddy](https://www.workbuddy.ai/)
- [Qoder（阿里）](https://qoder.cn/download)
- [Trae](https://www.trae.cn/)
- [OpenCode Desktop](https://opencode.ai/download)与[连接模型说明](https://opencode.ai/docs/providers/)
- [DeepSeek 开放平台](https://platform.deepseek.com/)与[充值页](https://platform.deepseek.com/top_up)
- [同花顺金融数据 API 平台](https://fuyao.aicubes.cn/)
- [同花顺金融数据 API 个人管理页](https://fuyao.aicubes.cn/admin)
- [Hithink Finance API 概览](https://fuyao.aicubes.cn/docs/api-reference/overview/)
- [巨潮资讯](https://www.cninfo.com.cn/)
- [Kimi 会员说明](https://www.kimi.com/help/membership/membership-overview)
- [Kimi Code Datasource 说明](https://www.kimi.com/code/docs/kimi-code-cli/customization/plugins)
