# 零基础必看入门

系列讲座课前中文入门，面向没有编程经验、日常使用 Office 的教师。先解释模型调用、Harness、Agent、数据 API 与文档格式，再按需准备工具和服务。

- `handout.md` 是唯一正文维护源。
- `build.py` 生成可单独打开的 `index.html`，内嵌页面样式与操作脚本。
- 页面沿用第二讲的框架、颜色、字体与步骤卡片，增大正文和表格字号。
- `assets/onboarding.css`、`assets/onboarding.js` 处理排版、复制、打印及已有工具选择。选择任意已有 Agent 后，隐藏整段 OpenCode/DeepSeek 安装说明；无已有工具时提供折叠路线。选择仅保存于本机浏览器，没有服务请求或密钥输入。
- 无课前完成进度、自查单或完成报告。每个按需操作都说明目的和具体输出，各讲在自己的项目中验收。
- `verification.md` 记录作者检查及尚未验证的事项。

生成方式，使用已有 Python Markdown 与 BeautifulSoup：

```sh
python3 start-here/build.py
```

从本库根目录刷新分讲导出：

```sh
python3 start-here/build.py --export-to ../../00-getting-started
```

`00-getting-started/01-handouts` 是逐字节导出副本，不独立编辑。来源指纹保存在该目录的 `06-preparation/export-manifest.json`。本页作为独立课前入口，不修改第一、二讲的教学源或第三讲候选分支。

讲义中的本人操作、注册和实际 API 调用尚未由所有学员完成。作者检查不代替课堂学员的连接证明。Windows 安装路线按官方文档编写，未做 Windows 实机验收。
