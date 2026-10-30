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

event至少含`id,stock_code,company,report_period,meeting_date,start_time,end_time,question_deadline_date,question_deadline_time,participation_url,status,source_ids,source_numbers,pending_fields`。取消或未定日延期停止旧未来时间，历史保留。嘉和概括声明与提问日期冲突时保留旧值，将候选放pending_fields。全量已知公告按发布日期重建可用事件，保留失败公司的旧记录。比较事件业务字段生成changes，重复执行无变化。issues含`{stock_code,source_id,reason,...}`。不得将日期已过等同已召开。

## runner.py

拥有配置、单写者文件锁、一次业务运行、模型缓存、结果HTML和summary/state原子发布。一个公司的查询、处理或关联失败，不推进其last_success，其他成功公司正常更新。原始运行目录不可变。公开的`run(config_path,workspace,trigger="manual",fixture=None)`供CLI调用。模型变化是extraction_revision，不能伪称市场新改期。

## schedule.py

`install(config_path:Path,workspace:Path,project_root:Path)->dict`安装本平台的持续任务。macOS采用launchd每分钟唤起`python run_agent.py tick --config ... --workspace ...`，tick按Asia/Shanghai计算周一至周五08:30是否到期，避免launchd使用机器时区带来的偏差。Windows生成同一tick入口的计划任务，但未实测不标通过。

`test_after(workspace:Path,seconds:int=90)->dict`保存一次未来测试时刻，真实OS任务到点调用同一run入口；不能用手动kickstart冒充定时触发。`status(workspace:Path)->dict`读取计划和真实OS任务，`pause/resume(workspace)->dict`控制enabled。`tick(config_path,workspace,project_root)->dict`到期后用绝对路径启动同一run命令，记录scheduled_for、实际开始/结束、退出码、run_id/产出。提前claim避免重复触发，失败保留结果并允许下一次计划。不得记录凭据。只操作本项目label/任务，不改其他自动化。
