# 第一讲准备工作

先打开 [教师实操讲义](../handout.html)。本页只负责把工具与文件准备好，搭建时逐步使用讲义第 0–7 步。

## 1. 准备编程 Agent

本讲用 OpenCode 写程序。已有可用的 OpenCode 就继续使用，不必更换版本。

1. 尚未安装时，打开 [OpenCode 官方文档](https://opencode.ai/docs/)，按自己的系统安装。
2. 打开 OpenCode，在连接入口配置自己使用的编码模型。终端版常用 `/connect` 和 `/models`，不同版本按实际界面操作。连接方法见 [官方模型提供方说明](https://opencode.ai/docs/providers/)。
3. 确认它能回复一句话。然后打开下面准备的项目文件夹，确认能读文件。

OpenCode 中的模型帮助你写代码。应用运行时使用的 Qwen/Qwen3.5-4B 是另一项配置，不能因为 OpenCode 能聊天，就认为应用已经有财报模型授权。

## 2. 准备工作文件夹

1. 下载 [第一讲实操材料](../lesson-one-materials.zip)。
2. 解压，把包内 `earnings-workflow` 文件夹放在桌面等自己方便找到的位置。不要直接在压缩包内操作。
3. 在 OpenCode 中选择“打开文件夹”，选中这个 `earnings-workflow`。若文件列表只有另一个同名文件夹，向内再打开一层。
4. 确认以下文件直接出现在项目中。不要先建 PPT、四 Agent 或定时任务目录。

```text
earnings-workflow/
  TASKBOOK.md
  AGENTS.md
  data/report-pages-60-75.txt
  contracts/workflow.json
  prompts/runtime/
  history/lesson-one-history.json
  checks/
```

材料包有真实报告文字窗口、只读历史收据、任务模板和固定案例检查参考，没有成品应用。`checks/case-reference.json` 含评分答案，只供程序检查器使用，不能发给运行中的财报模型。历史收据不能补成本次 Run 的前序输入。

## 3. 检查本机环境

把讲义第 0 步完整 Prompt 发给 OpenCode。它会检查系统、Node.js 22 或更高版本、材料指纹和写入权限。

缺少 Node.js 时，按 Agent 给出的当前系统步骤完成；官方入口是 [Node.js 下载页](https://nodejs.org/en/download)。已经满足条件的环境不用重装。第 0 步检查通过，再发第 1 步。

以后由 Agent 建立并启动本地服务。打开它返回的完整本机网址，不用双击 HTML 文件。关闭与重新启动方法要写在它生成的 `RUN.md` 中。

## 4. 准备个人运行 Key

看现有产品的历史结果，以及搭建和运行离线检查，都不需要财报模型 Key。真实 Run 才使用自己的硅基流动授权。

1. 打开 [硅基流动控制台](https://cloud.siliconflow.cn/)，在本人账户中管理 API Key。账户权限与费用以服务当时显示为准。
2. 第 3 步接通调用后，由本人在做出的网页隐藏输入框填 Key。若先试现场产品，也在 [Evals](../demo.html#evals) 的个人 Key 输入框填写。
3. 在同一页面会话依次运行 02、04、06。每次检查通过后再继续。后续只能读取本轮通过的精确前序。
4. 完成后清空 Key。刷新会清空页面中的 Key 和本轮可用前序，需从 02 重新开始。

Key 只在页面与本次请求内存中使用，不发给 OpenCode，不写入项目、浏览器存储、运行收据、日志或截图。程序由本地后台调用模型服务；已上线产品则由同站后台调用。

## 5. 每一步怎样跟做

复制本步主 Prompt → 发给 OpenCode → 等它写文件并运行检查 → 自己按“你应看到”核对 → 确认后发下一步。

若只返回方案，先切到允许编辑的 Build 模式，再发送“按刚才方案完成本步并运行检查”。卡住时发送该步修复 Prompt，不必自己先解释错误。

没有个人 Key 时可以继续搭建离线模块，验收如实写“真实运行待完成”。历史结果和测试响应都不能算作本人真实 Run。

操作入口核对日期：2026-10-17。返回 [教师实操讲义](../handout.html)。
