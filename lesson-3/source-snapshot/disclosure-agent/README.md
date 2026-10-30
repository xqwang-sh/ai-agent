# 公告事件智能体

教师参考实现，默认从巨潮真实查询开始。学员从短业务需求和空目录搭建，课堂主线见同级`../lesson3-workshop/lesson.md`。这一成品不进入起步包。

Python 3.11及以上。安装`requirements.txt`后，在本目录运行：

```sh
python3 run_agent.py run
python3 run_agent.py schedule install
python3 run_agent.py schedule test --after-seconds 90
python3 run_agent.py schedule status
python3 run_agent.py schedule pause
python3 run_agent.py schedule resume
```

先手动查对来源、模型结果与事件状态，再安装持续任务。`schedule test`只安排真实系统任务在约90秒后到期；不要用手动`run`冒充定时触发。macOS系统每分钟唤起检查器，业务时间为周一至周五北京时间08:30。暂停阻止下次业务运行，系统唤起保留，当前运行继续。电脑醒来仅补当天到时的工作日任务，不补过去日期。

macOS版使用本机用户任务，需要电脑开机且用户登录；关机或退出登录期间不能保证执行。迁到常开位置时须重新验收后台凭据、来源与系统触发。

`config.json`覆盖伊利股份600887、嘉和美康688246，首次回看90天，后续完整成功后回看7天重叠窗口；旧公告按归档原文和模型回执重新核验。默认模型`Qwen/Qwen3.8-27B`来自本次4B、9B、27B比较，使用前核对自己账号模型目录。`config-adaptive.json`是有界规划实验，不是主线。

密钥读取环境变量`SILICONFLOW_API_KEY`，或用户级`~/.config/siliconflow/credentials.env`中的同名变量。Windows用户级配置位于`%APPDATA%/siliconflow/credentials.env`。项目、ZIP和网页都不保存密钥；后台任务必须用本机真实凭据完成一次验证。

默认工作区`runtime/live`，实时与历史重放必须分开。`current.json`提交指针绑定同一轮`runs/<run_id>/state.json`、`summary.json`和`calendar.html`的指纹，使用它恢复状态。根目录同名文件是便捷副本；丢失提交指针时须核对不可变运行后恢复，不能默认为旧副本正确。源PDF、每次模型回执与失败都保留。

结果`complete`表示本轮覆盖与处理完整且无未决事项；`needs_review`表示处理完成但有待判断信息；`incomplete`表示查询或处理未完整完成。CLI后两者返回退出码2，软件异常返回1。定时任务单独记录execution_status和business_status，避免把待复核误报成启动失败。失败不能解释为无新增。

```sh
python3 -m pytest -q
```

测试使用明确标记的模拟数据，不调用付费模型、不安装系统任务。2026年10月30日已实测macOS真实触发、后台巨潮取数及模型调用、暂停恢复。Windows适配只有生成与模拟测试，长期无人值守仍需观察。

运行时不读取候选金标准。12份验证资料由单独验证包提供，评分原始输出；人工修订另存。关键词查询的完整性只适用于指定公司、关键词和日期窗口，不等于所有披露的完整召回。候选金标准待任课教师确认。

产品入口仍为每轮输出的calendar.html，页面包含会议安排、变更与待复核、运行与来源三个视图。展示与来源字段使用同一状态，前台不另造业务数据。
