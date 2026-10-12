# 开始前

第一步是取得课堂提供的 `byd_earnings.zip` 并解压，再用 **OpenCode** 打开解压后的 `byd_earnings` 文件夹。压缩包只含 `output/byd_earnings_template.pptx` 这一份可编辑模板；除个人 API Key 的安全凭据文件保存在项目外，后续目录、文件和程序都在这个文件夹中建立。学习者主线默认使用 OpenCode + 一个能力足够的通用大模型；其他 Agent 工具可以复用同一批文件，但不是本讲义的必需前提。

## 1. 用 OpenCode 打开工作文件夹

开始前做一个一分钟测试：解压 `byd_earnings.zip`，从 [OpenCode 官方下载页](https://opencode.ai/download) 安装并打开 OpenCode，在“打开文件夹”中选中解压后的 `byd_earnings`，确认 `output/byd_earnings_template.pptx` 存在，然后在 OpenCode 对话界面输入：

> 我已解压 `byd_earnings.zip` 并打开名为 `byd_earnings` 的文件夹。请确认当前文件夹名称，并确认 `output/byd_earnings_template.pptx` 已存在且可编辑；这是压缩包提供的唯一模板，请保留它。建立 `data/case/raw/hithink/`、`data/case/raw/cninfo/`、`data/case/prepared/evidence/pages/`、`data/case/prepared/`、`output/`、`skills/a-share-earnings-reviewer/`、`workflow/agents/`、`automation/` 和 `setup/`，并建立一个 README.md 说明练习用途。完成后建立并删除一个测试文件，确认你能在这里保存内容。这一步只检查模板、建目录和检查写入，完成后停止。

如果 OpenCode 还没有连接大模型：

1. 在 [DeepSeek 开放平台](https://platform.deepseek.com/) 注册、创建自己的 API Key，并在[充值页](https://platform.deepseek.com/top_up)充值；课堂建议 5 元作为小额试用预算，实际规则以页面当时说明为准。
2. 在 OpenCode 输入 `/connect`，选择 DeepSeek，在不回显的输入框中填写 Key；再输入 `/models`，选择一个能力足够完成文件读写和长文本整理的模型。
3. 先让模型完成讲义第 01 步的 Product 定义，再继续后面的基线、Approaches 和 Evals。不要把 DeepSeek Key 写进练习文件夹或聊天正文。

[Kimi 官方会员说明](https://www.kimi.com/help/membership/membership-overview)列出的专业数据库包含同花顺；[Kimi Code Datasource 说明](https://www.kimi.com/code/docs/kimi-code-cli/customization/plugins)指出查询会消耗 Kimi Code 套餐额度。这项查询能力在 Kimi 产品内使用。本练习的独立程序需要自己的同花顺金融数据 API Key。

## 2. 注册同花顺金融数据 API

打开 <https://fuyao.aicubes.cn/> 注册，在个人管理页取得自己的 API Key。不要与同学共享，也不要发到聊天、邮件、截图或群文件。

如果尚未安装命令行工具，可让 AI 完成下面这件事：

> 请先检查这台电脑能否运行 hithink-finance。如果不能，请只从官方 npm 包 `@hithink-tech/hithink-finance-cli` 安装，并确认版本可以显示。不要索取或显示我的 API Key。

该工具需要 Node.js 22.12 或更高版本。安装命令是：

```bash
npm install -g @hithink-tech/hithink-finance-cli
hithink-finance --version
```

## 3. 让 AI 建立安全保存工具，再由本人存入 Key

Key 不得放在 `byd_earnings` 或任何将被打包、同步、截图的项目目录中。先让 AI 判断当前系统，并在解压后的项目 `setup/` 中建立隐藏输入的安全保存工具。Key 由本人运行该工具时输入，标准保存位置是：

| 系统 | 个人凭据文件 |
|---|---|
| Windows | `%APPDATA%\hithink-finance\credentials.env` |
| macOS | `~/Library/Application Support/hithink-finance/credentials.env` |
| Linux | `~/.config/hithink-finance/credentials.env` |

文件只包含一行 `HITHINK_FINANCE_API_KEY=自己的Key`，等号右侧不加引号。

- macOS：运行 AI 刚在 `setup/` 中建立的 `save_hithink_key.command`；工具必须隐藏输入。
- Windows：运行 AI 刚在 `setup/` 中建立的 `save_hithink_key.ps1`；脚本必须隐藏输入，并只允许当前用户读取凭据文件。
- Linux：在终端运行 `hithink-finance auth login`，按提示隐藏输入；不要把 Key 写进命令参数。

脚本只报告成功或失败，Key 始终隐藏。完成后可运行：

```bash
hithink-finance auth status --format json
```

## 4. 检查 AI 现场建立的目录

下面是 AI 应在解压后的 `byd_earnings` 中建立的目录。所有路径都相对于这个文件夹；`output/byd_earnings_template.pptx` 已随起始包提供：

```text
data/case/raw/hithink/       自己取得的同花顺 JSON
data/case/raw/cninfo/        由 Agent 从巨潮官方披露取得的 PDF
data/case/prepared/          自己填写的原文核对表与程序生成的汇总
output/                      5 页候选 PPT、人工确认后的 PPT 和待复核简报
skills/                      供各 Agent 共同遵守的金融口径和证据规则
workflow/                    四个 Agent 的编排、角色任务、固定检查程序与每次运行的证据副本
automation/                  每日完整自动程序、事件状态与本地结果页
```

目录检查通过后，继续把讲义中的普通中文请求逐条交给 AI。AI 会使用本人的同花顺权限取数，并根据公司、报告期和本地目标位置，从巨潮资讯官方公开披露中下载两份 PDF。

## 5. 开始前的安全约定

- 任何 AI 都不得要求你把完整 Key 发到聊天。
- Key 不进项目、不进提示词、不进代码、不进日志、不进压缩包。
- 同花顺数值用于整理，巨潮资讯公司公告用于原文复核；两边不一致时先停，不猜原因。
- 本练习分析收入与利润，不判断“超预期”，不估值，不荐股。
- 最终简报是“课堂草稿——需要人工复核”，不得自动发布。

## 6. 本次讲座的最终结果

在完成收入与利润复核后，运行由四个 Agent、课程 Skill 和固定检查程序组成的 workflow。角色与顺序保存在 `workflow/agents/` 和 `workflow/workflow.json`。Codex 路线使用：

```bash
python3 workflow/run_agents.py --project . --provider codex
```

兼容的第三方模型使用 `--provider openai_compatible`。每次 workflow 保存两份 JSON、两份 PDF、摘要第 1、2 页与全文第 65、67 页的整页截图、五项核对表和阶段状态。

最后生成独立自动化程序，使其每天北京时间 02:00 检查观察名单中的新业绩数据。课堂试跑时，把前面刚刚取得的半年报作为一次新发现处理，将 `automation/config.json` 中 `monitor.first_run` 临时设为 `emit_existing`；试跑结束（成功或停留）后恢复 `baseline`。发现新数据后，程序自动完成巨潮取证、计算、PDF 提取、整页截图、五项核对、候选 PPT 更新、简报和结果页。每一步都有状态；出错时停在当前步骤，保留已取得材料，修复后从该事件继续。`automation/runtime/result.html` 显示逐步进度、准确停留位置、人工复核材料、候选/已批准 PPT 状态和上一次成功结果。文字模型可以更换，取数、计算、复核、PPT 数据绑定和停止规则保持一致；已批准 PPT 只由本人确认后更新。
