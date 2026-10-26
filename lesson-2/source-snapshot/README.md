# Earnings Review 第二讲

打开 `index.html` 阅读网页讲义。`讲义.md` 是同内容的 Markdown 版本，`PROMPTS.md` 收集全部开发与修复 Prompt。实操材料包为 `earnings-review-materials.zip`，没有成品应用、真实公司答案、预选答案页或凭据。

`source/lesson.json` 维护九条本步任务；`source/project-agents.md` 维护共同规则，构建时复制为材料包根目录的 `AGENTS.md`。学习者解压即有规则文件，第0步读取，后续各步引用，不再另发一条消息创建。`source/prepare_materials.py` 生成数据约定、任务书和材料清单，并复制四份通用运行时提示词与 `source/acceptance/` 公共合成验收。验收代码调用学习者编写的生产模块；第8步必须走实际任务创建和冻结工作进程，不能另写测试专用流程。

生成与内容检查：

```sh
python3 source/build.py
python3 qa/check_handout.py
node --check assets/handout.js
```

学习者使用自己项目的 Python 运行 `python -m acceptance.checks --through 5`，后续改为6、7、8。默认检查禁止出站访问，继承到Python子进程；仅回环合成服务可用。这是进程级保护，不是操作系统沙箱。联网身份预检、模型列表预检与真实财报运行分别启用。合成用量和测试复盘不得进入真实公司结果。

实际浏览器检查与 HTTP 检查分开记录。没有已授权浏览器工具的编程 Agent 应启动服务、给出人工检查步骤，不能把 API 测试通过当成页面可用。九条主线实验的独立浏览器记录保留在审计目录，不作为额外提示词或私有观察写入新项目；需要额外修复消息的版本如实判未通过。

课前顺丰27B示例的原始用量与阶段时间见 `source/verified-example.json`，它不是学习者的当前运行回执。当前内容检查见 `qa/content-checks.json`。Windows、9B或其他公司的通过状态只能由各自的实际运行证明。

发布到既有静态站时使用 `python3 source/publish.py --site 目标站目录 --handout-only`。它导出讲义、材料和带哈希的 `source-snapshot/`，并核对历史成品示例保持原字节。源快照用于审阅教学修改，不是成品应用，也不是每次任务实际执行的 `program/` 快照。生成仍由本工作坊的规范源码目录负责。

如需重新投影一份已经封存的历史产品，另传 `--product 本地产品目录 --job 已通过封存检查的ID`。脚本检查来源和证据，只复制公开投影，不复制凭据、后台状态或原始提供商日志。第一讲、主页与既有反馈表单保持各自的维护边界。

前版2026-10-18从头重建与真实运行见 `source/verified-rebuild.json`。实测使用macOS和OpenCode CLI1.18.26，从不含应用代码的23份材料顺序完成0–8。成功前继续使用同版第8步修复Prompt10次，成功后再1次仅修改网页显示。另有一次只读观察意外修改了工作区，已与正式修复分开记录；最终观察改为明确填写任务ID、只返回报告，工具仅可读取，禁止包括project_status.md在内的任何写入，并检查受保护文件前后哈希。材料包与其余30条提示词在重建中保持哈希一致；观察Prompt单独修订和复测，不改已封存财务任务。

三轮真实任务依次为定位停止2次调用/52,396 tokens、来源标题误拒停止5次/147,158 tokens、完整通过3次/65,561 tokens。第三轮当前两层均10/10，无失败或补证，原始请求、213张整页图、所有候选、完整季度参考和实际程序已经封存。此前失败保留，不能改成成功或用课前示例覆盖。运行模型总用量265,115 tokens，缓存29,440已含在prompt，不另加；编程对话用量不在产品账本内。

最终检查为独立操作系统断网条件下串行18项公共、99项本地检查，以及24项封存和45项财务/上下文/图像绑定核对。375/320实际结果页无根页面横向溢出；只读刷新保留同一任务和用量。成功后网页显示修复没有改变28个业务源文件或成功任务275个文件。Windows、9B、其他公司和OpenCode桌面操作回放没有由本次实测证明。

本轮主线标准：把前版十次修复及显示问题移入九条主提示词、contracts/development-checks.json和可执行公共验收。每条原始消息内允许Agent根据公开失败自行修正并重测；不发送第十条修复、恢复或观察消息，不复制旧应用，不由审查Agent补写业务代码。版本冻结后从零应用文件和全新OpenCode会话依次发送0–8。额外指令使本版验证失败，必须保留失败再修改教学源、另空目录重跑。当前新版验证状态以新的真实回执为准，不能引用前版成功替代。

- After the version-03 main8 length termination, production work is incremental: durable task/journal1, normal read-only server2, real freeze/worker and permanent negative gates3, same-task ledger4, source loop5, first sealed happy path6, all30 original production assertions7, UI/full regression/launch8. No additional Subject API or finished business code is provided. Earlier failed versions remain failed; code-model settings stay unchanged for the new replay.
