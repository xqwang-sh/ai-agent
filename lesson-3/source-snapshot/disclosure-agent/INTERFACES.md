# 实作接口草图

此文件用于教师制作，学员初始包不提供实现。来源、模型和事件归并边界分别验证，运行时不读取金标准。

使用入口：`python run_agent.py run --config config.json --workspace runtime/live`。默认实时抓取；`--fixture 文件`明确启用历史重放，禁止与live状态混用。配置中的`companies`为`[{code,name}]`，`lookback_days`默认90，`overlap_days`默认7，`models`为允许尝试的模型列表，`strategy`为fixed或adaptive，`timezone`为Asia/Shanghai。

## cninfo.py

`CninfoSource(workspace: Path, run_dir: Path, timeout: int = 25)`。

`acquire(company: dict, start_date: str, end_date: str) -> dict`返回`{company:{code,name,org_id}, status:"complete"|"failed", query_complete:bool, items:list, failed_items:list, error:str|null, query:dict}`。公司身份从真实公司表核验；全部分页完成才query_complete。列表、请求参数、原始响应与PDF分别留存。异常不能转零条。

每个item包含`id,stock_code,company,org_id,title,publication_date,pdf_url,url,pdf_sha256,pdf_path,pages`，pages为按PDF页码排列的完整文字字符串数组。PDF按ID及hash存workspace/raw，不能覆盖旧hash，下载失败保留其他成功item。网络访问有超时、分页上限、PDF大小上限。模块只依赖requests与pypdf。

## extract.py

`extract_notice(item:dict, models:list[str], run_dir:Path) -> dict`返回`{status:"accepted"|"failed", data:dict|null, model:str|null, attempts:list, usage:dict, errors:list}`。模型对象严格符合prompts/output.schema.json。凭据从SILICONFLOW_API_KEY或用户级credentials.env读取，不能写入项目、日志或打包文件。程序检查Schema、日期、页码与逐字证据。每次原始响应保留，不因后续通过删除失败。运行时不读任何teacher-gold文件。

## ledger.py

`merge(previous:dict, records:list[dict], coverage:dict, run_id:str, as_of:str) -> tuple[state,changes,issues]`为纯函数。record包含上述item元数据和`extraction`，extraction是已通过边界检查的模型data，另有`model`和`revision_reason`。record不含pages。state包含`events`、`notices`、`companies`字典。事件稳定ID以原通知ID锚定，变更按公司+明确原公告号关联；不唯一就待复核。源指纹变更保留旧版并待复核。

event至少含`id,stock_code,company,report_period,meeting_date,start_time,end_time,question_deadline_date,question_deadline_time,participation_url,status,source_ids,source_numbers,pending_fields`。取消或未定日延期停止旧未来时间，历史保留。嘉和概括声明与提问日期冲突时保留旧值，将候选放pending_fields。全量已知公告按发布日期重建可用事件，保留失败公司的旧记录。比较事件业务字段生成changes，重复执行无变化。event.activity记录first_seen_at、updated_at、kind、revision、run_id；比较业务字段、来源、待复核内容与有效性来维护，重复或失败保留原时间，旧数据缺失则明确未知。review_reasons保留来源冲突及未关联变更等复核原因；不会把新的复核事项当作公司已变更。issues含`{stock_code,source_id,reason,...}`。不得将日期已过等同已召开。

## runner.py

拥有配置、单写者文件锁、一次业务运行、模型缓存、结果HTML和summary/state原子发布。一个公司的查询、处理或关联失败，不推进其last_success，其他成功公司正常更新。原始运行目录不可变。公开的`run(config_path,workspace,trigger="manual",fixture=None)`供CLI调用。模型变化是extraction_revision，不能伪称市场新改期。

## schedule.py

`install(config_path:Path,workspace:Path,project_root:Path)->dict`安装本平台的持续任务。macOS采用launchd每分钟唤起`python run_agent.py tick --config ... --workspace ...`，tick按Asia/Shanghai及保存的weekdays/time判断是否到期，新计划默认为每天08:30，避免launchd使用机器时区带来的偏差。Windows生成同一tick入口的计划任务，但未实测不标通过。

`test_after(workspace:Path,seconds:int=90)->dict`保存一次未来测试时刻，真实OS任务到点调用同一run入口；不能用手动kickstart冒充定时触发。`status(workspace:Path)->dict`读取计划和真实OS任务，`pause/resume(workspace)->dict`控制enabled。`tick(config_path,workspace,project_root)->dict`到期后用绝对路径启动同一run命令，记录scheduled_for、实际开始/结束、退出码、run_id/产出。提前claim避免重复触发，失败保留结果并允许下一次计划。不得记录凭据。只操作本项目label/任务，不改其他自动化。

## presentation.py / reminders.py

render_product(state, summary, frozen=False, back_url=None)生成一份自包含HTML。月历→日期公司→事件摘要→完整参与办法及原公告为主线，运行来源是辅助检查入口。calendar.js与calendar.css随应用分发、纳入程序指纹，运行时内嵌，不依赖外部网页服务。product_data只选择公开字段，不嵌入查询异常或作者路径。participation_excerpts从指纹匹配的源PDF按页摘录参与章节，摘要的结构化字段继续沿用原模型核验，不增加模型调用。

reminder_items按字段独立判断提醒资格；冲突截止不阻止明确会议，未关联变更/源冲突/检查不完整则阻止受影响旧安排的新提醒。render_ics生成RFC5545日历文件，UID锚定事件，UTC时间，SEQUENCE递增，UTF-8按75字节折行，DISPLAY提醒为提前1天与30分钟。页面只下载文件，不直接改写用户个人日历。快照不自动同步，产品明确提示改期或取消后核对已导入提醒。

source_text.py拥有源PDF参与章节摘录与截止事项命名。deadline_label、event_deadline_label依据已核验的截止原文或包含同一引文的参与段落判断提问/预报名/报名，不能按公司或网址猜。旧结构question_deadline_*字段名与历史评分保留，前台和ICS使用同一个原文角色。提醒入口仅在具体事件详情；公告原文按URL去重，每份文件只显示一次链接。

当前report_period配置为2026-Q3。明确其他报告期会记录排除；无法从标题判定的变更仍需读源关联。旧question_deadline_date/time字段按兼容约定容纳原文明示的提问、报名或预报名截止，deadline_evidence保留事项名，前台及ICS依原文命名；不允许将报名时间标为提问截止。多项不同截止须保留在原文与复核记录，不能静默合并。

## market.py / market_source.py / worker.py

`universe=a_share`使用独立工作区。`report_period=2026-Q3`、`meeting_start/end`与`source_start`明确范围。开发`config-market.json`为60次调用，日常`config-market-scheduled.json`为240，均含纠错和重试、模型最多3并发。新请求先预留可能的两次尝试额度，完成释放余量，再补入下一份，不因其他慢请求空等或突破上限。

`run(..., refresh=False)`允许手动续处理冻结批次，`--refresh`强制源刷新；系统trigger每次刷新，跨日积压不冻结日期。发现层保留checked_at与真实retrieval_start/end，as_of只来自有效来源回执；它不是所有窗口同一时点的水位。

`process_source`在HTTP前保存来源绑定与started回执，结束后原子保存finished原答。恢复先验证所有匹配回执，业务可采用已通过结果，但仍携带其他已结束及未知尝试。成功不能抹去失败用量或started未知状态。每份记录旧source hash变化优先进入复核并冻结相关旧提醒。

本期验证包是2+8+8的18份/40页，历史12份另作隔离回归。`deadline_evidence.parts`仅用于真实跨相邻两页的截止句；其余证据仍单页，业务归并与事项命名均理解parts。运行时不读金标准。

调度安装读取`schedule_weekdays`、`schedule_time`，新默认每天08:30，北京时区不变。已安装任务以自己的plan为准，不因运行配置变动悄悄重写计划。市场迁移先停用旧业务任务再安装及真实测试，不能借小样本OS成绩验收新范围。

`scope.source_heading_period`只识别与说明会用途正向绑定的报告期；`source_current_period`保留并列财务用途，不从任意历史段落或经营战略猜期别。`market._screen_source`不以仅解析出的别期否决仍可能包含Q3的正文。`source_date_outside_window`的单日证明绑定物理页、连续原文及PDF/页文指纹；不完整范围保留未知。

`market_source.discover_market`在单次总请求预算中继续补本轮刚发现的分页缺口；403/429立即停止，数据缺口不变时最多耗至预算后返回partial。没有发出新请求时才提前停止，不承诺重复ID一出现就停止。

- 当前产品日历与当天安排仅列会议。提问预征集区间附在同一会议下，只取最新公告中连续、同页且与已核验截止一致的原文；只有截止则仅显示截止。更正更新同一事件并移除旧日期卡片，原公告及变更记录保留。
- 关注名单支持Excel公司简称或股票代码，按巨潮orgId去重，歧义或错配整批拒绝。目录绑定实际运行来源；续跑及来源失败沿用hash核验的市场目录，不能退回合成事件身份。名单在本机保存并作用于所有事件视图；日期内当日更新优先，全部事件仍按日期和时刻倒序。
