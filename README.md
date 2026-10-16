# 产教融合背景下AI金融智能体赋能教师教学能力提升计划

系列讲座主页、第一讲公开材料与第二讲 Earnings Review。

主讲：汪小圈｜上海对外经贸大学 金融管理学院

- 线上主页：[suibe-ai-agent.netlify.app](https://suibe-ai-agent.netlify.app)
- 主页源码：`index.html`
- 第一讲现场演示：`demo.html`
- 第一讲学习讲义：`handout.html`
- 第二讲成品示例：`lesson-2/earnings-review/`
- 第二讲分步 Prompt 讲义：`lesson-2/`
- 第二讲实操材料：`lesson-2/earnings-review-materials.zip`
- 第二讲完整离线讲义：`lesson-2/EarningsReview-第二讲讲义包.zip`
- 第一讲实操材料：`lesson-one-materials.zip`
- 原 PPT 模板附件：`byd_earnings.zip`
- 数据与安全指南：`PUBLIC_DATA_GUIDE.md`

公开目录不包含 API Key、私人授权信息或本地后台状态。第二讲仅发布经核验的顺丰示例及其公开调用汇总、财务比对和 PDF 证据，首次打开不调用模型。其余公司只有报告材料，不套用顺丰结果。

第二讲完整产品在学习者本机读取 PDF、运行模型和访问同花顺。按讲义第 0–8 步，让自己的编码 Agent 搭建程序。实操材料包不含成品应用或预填财务答案。`lesson-2/publication.json` 记录发布文件、原产品界面、PDF 与封存结果的哈希。

第一讲使用报告第 60–75 物理页文字窗口，以 02 → 04 → 06 为主线，比较三个阶段的不同做法。它是程序规定依赖与检查的 workflow。历史只读，在线 03/04 必须读取本轮通过的 02，05/06 必须读取本轮通过的 04。材料包含只读历史与评分参考，后两者不得作为本轮模型输入。

第一讲讲义源为 `handout/lesson.json`，运行 `python3 handout/build.py` 同步生成网页、提示词附录、Markdown 讲义和材料包。模型、工具定义与运行提示词直接从产品的共享模块导出。验证使用 `python3 handout/check.py`、`npm test`，并在浏览器检查桌面和窄屏页面。

## 发布

- GitHub：[xqwang-sh/ai-agent](https://github.com/xqwang-sh/ai-agent)
- Netlify：[suibe-ai-agent.netlify.app](https://suibe-ai-agent.netlify.app)
