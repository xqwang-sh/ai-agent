# 公共合成验收

这里没有成品应用。fixtures.py 中的公司、页、数值及服务响应都是编造的。checks.py 调用学习者自己实现的生产模块，不能把测试数据放进真实公司的 review。

先读当前步骤对应的约定和用例，完整检查失败后再读相关测试体；不要在第一次业务写入前通读全部脚本。实现 app/acceptance.py 中唯一工厂 create_subject(project_root)。工厂返回对象，下列方法只适配生产代码的输入输出，不重新实现校验或阶段循环。

- validate(observation, pages, selected_pages, expected_company=None) 返回 passed、rules、五项 bound_rows。rules 非空即不能通过。pages 是 physical_page/text 对象数组。
- dispatch(actions, pages, phase) 驱动生产 ExtractSession 的同一动作分派。返回 trace 动作名称数组、candidate_count、source_actions、failures。裸selection和裸完整observation先归一化。
- compare(text, vision, reference, pages, expected_thscode, expected_company=None) 调用生产两层核验与反馈脱敏。返回 internal/external，各有 passed、matched、total，以及只含规则和指标的 feedback。合成 reference.records 是规范化传输夹具，进入生产唯一H1筛选和比较函数，不另写测试比较。
- progress(events) 驱动生产 WorkflowController，返回 snapshots、stopped、reason、counters。snapshot 含 no_progress、ever_passed；counters 含 failed_gate_evaluations、feedback_emitted。gate事件 rules=[] 表示通过，candidate_changed仅使当前证明失效。未知终态usage阻止后续准入。
- run(scenario, output_root, after_create=None, wait_timeout_seconds=None) 调用网页相同的 TaskManager 创建、原子冻结和真实 TaskRunner。after_create(task_dir) 在冻结完成、启动子进程前执行。工作进程实际从 task_dir/program 执行。仅替换模型和外部传输，不替换编排、检索、页图渲染、计算、核验或交付。测试传输脚本是显式测试依赖，不写进生产预设，真实运行不启用。

run 返回真实路径 task_dir、state_file、trace_file、ledger_file、freeze_manifest_file、execution_file、sealed_archive、prepared_file、proof_file。允许适配命名，禁止伪造成功摘要。

state_file 包含 status、review、counters、latest_failure、current。current 有 candidate_id 和 internal/external，每层有 passed/matched/total/candidate_id。counters 至少有 failed_gate_evaluations、feedback_emitted、feedback_requests。两次无进展失败应显示两次失败评估、一次已发反馈、一次实际补证请求。

trace_file 包含 actions 和 requests。actions 每项有 action；requests 按实际调用顺序含 request_id、stage、session_id、request_path、response_path。request_path 是真正送到传输边界的无认证头请求，messages 与 model_receipts 中同 request_id 的 messages 一致。response_path 保存原始usage。ledger_file 含 requests 与 total_tokens。

freeze_manifest_file 的 files 每项含相对 program 根目录的 path、sha256。execution_file 含实际 pid、entrypoint、loaded_modules 名称到实际模块文件路径映射。sealed_archive 含同样的 program/ 文件和哈希。工作区后改的模块、提示词、配置不能影响已创建任务。

各步执行 `python -m acceptance.checks --through N`，N为当前0–8。累计测试数为1、1、3、6、6、11、16、35、35。第3步已有真实冻结worker及源码/PDF/目录漂移负例；第5步走真实来源循环；第6步frozen_execution走完整成功链与封存；第7步完成全部35项生产组合，第8步不再新建后端系统。缺接口、阶段或证据就失败，不能skip、删断言或新增测试专用成功路径。函数检查用于定位问题，第7步完整生产组合才证明离线接线，第8步再做完整回归和网页检查。

默认检查在导入应用前阻止本进程及继承环境的Python子进程出站连接、DNS和常见外部网络命令，只允许回环测试服务。这是进程级保护，不是操作系统沙箱。不导入live测试、不查询真实证券身份、不读服务凭据。应用默认单元测试也在相同守卫下运行，联网检查必须显式启用。

合成组合包含来源失败后检索、视觉分歧退回、外部分歧退回，以及终身无进展。完整循环使用同一合成PDF中两张相互竞争、各自原文引用有效的不同数字表，测试图/文字或外部不一致时退回修订。第二次候选选择另一张实际印刷的表，不是把同花顺数值填进原表。外部一致只证明该合成候选的比较结果；两张原页和先前差异必须保留，不能据此声称已解决文档权威性。源检查负例会另测交换或错误取值；文字检查不声称通用理解PDF的二维排版。视觉请求只含完整原页图和身份/期间任务，不含抄录文本、参考答案、文字历史或外部差值。

另需浏览器核对运行中/终态文字、刷新、重复点击、公司切换、晚到响应。真实任务的身份、模型回执、原始页图、私有同花顺响应、当前两层10/10和封存交付，在第8步手动运行后单独核对。合成验收不能替代真实运行。

run场景不提供预抽取页文字或模型/参考答案。公共services.py拥有回环HTTP传输脚本和独立回执，传给run的scenario只有pdf_path、合成身份、preset、model_endpoint与reference_endpoint，或显式reference_cli可执行路径。后者不设置reference_endpoint，执行同一生产CLI分支。生产ModelClient在注入的测试端点按正常Chat Completions形状发请求；ReferenceClient测试传输GET/POST reference_endpoint取得与已安装CLI相同的完整success envelope（data.item）后，仍用同一个生产解析/H1筛选/比较。只在显式合成模式使用这些端点，不读真实服务密钥。生产代码不能导入public fixtures脚本取得答案。
prepared_file含pdf_path、pages_path和images，每个images项有path/sha256/physical_page。pages_path的逐页text须与传入PDF实际pypdf提取一致，图片必须从同一PDF渲染。公共测试独立记录服务边界请求、响应ID和完整usage，与任务证据逐项对齐。app/contracts.py、prompts/runtime/extract.md、contracts/workflow.json是本讲已明确约定的路径，冻结检查会先导入app.contracts再改工作区这三项。

视觉自己的证据失败必须留在同一视觉会话，后续请求保留它自己的历史；新文字候选才创建新盲读会话。公共检查只在每个视觉会话首请求排除文字/外部答案，续跑允许自身原回复。来源工具预算检查会连续检索6次后停止，不能把检索动作计成财务失败。每个实际模型请求的system指令必须包含冻结目录对应runtime提示词原文。

外部参考可在本轮私有冻结后缓存。combined/external_revision允许1–2次实际HTTP取数，但trace_file.external_evaluations必须保存两次实际比较，不能复用通过标记。每项含递增sequence、candidate_id、candidate_path（原始observation对象）、candidate_sha256、reference_path（保留的完整原始CLI形状JSON响应）、reference_sha256、after_request_id（本次盲读视觉请求ID）、passed/matched/total及comparisons（metric/period/current或prior/matched）。两候选内容哈希不同、同一参考哈希，第一轮8/10失败，第二轮10/10通过；适配器从真实生产比较记录映射这些字段。数据仅留私有核验记录，不进入模型反馈。冻结允许prompts/runtime下的运行时提示词，禁止根目录runtime输出及密钥。

外部核验的expected_thscode来自已确认的报告身份，不能从参考响应反推。日期必须解析且年份与record.year和目标年一致。列头证据不得为空，也不得用较短引文证明虚构的完整path。模型回执中的prompt/completion/total须齐全且为非负整数，total=prompt+completion；缓存量含在prompt内，不可超过prompt。缺失、负数、非整数或矛盾回执标unknown并停止后续准入，不补零或猜测用量。每张实际发送的视觉图前紧邻text标注physical_page=原PDF物理页编号，自身续跑保留相同图片和标注；不以图片序号替代。

封存不能只有文件路径索引。ZIP必须实际包含与本轮哈希一致的原PDF、逐页文字、所有已发模型请求及原始响应、原始页图、各候选、冻结参考、执行记录、prepared和冻结manifest，以及完整模型请求账本和动作/比较轨迹。公开检查逐个核对实际文件内容哈希，不能以prepared.json里列出图片路径代替嵌入图片，也不能只打包最终成功候选而丢弃本轮失败和补证。状态投影可在封存后加入ZIP哈希等元数据，原始回执及比较记录不得改变。

原始参考响应固定使用官方CLI的{ok,command,data:{timestamp,item:[]},meta}形状。记录字段为thscode/ticker/period/period_end_ms/report_date_ms/fiscal_year/fiscal_period/currency和财务字段，不能要求未文档化的cumulative字段。季度Q2是报表窗口，不等于单季度利润。以financials income命令语义、quarterly窗口、唯一fiscal_year/Q2及CNY核对H1；期末毫秒按明确的Asia/Shanghai报表日期规则转换，要求6月30日且年与fiscal_year一致，保存原始时间戳与规则，不按操作者本地时区转换。直接compare的规范records夹具仍用于独立诊断；两种输入必须进入同一生产参考归一化和比较边界，不能只在synthetic分支转换。

expected_company来自资料库已确认身份，传入所有生产来源/视觉检查。直接诊断可省略，仅表示未证明任务身份；生产交付不可省略。PDF可能同时含其他公司名称，出现过不等于可作为本任务公司。

每次search/read/select的实际结果必须作为user来源工具回执进入保留文字会话，包含检索片段、完整读页文字及物理页号；下一次真实provider-bound请求应能看到结果，不得只发通用继续语。未知/无效动作同样进入唯一分派器并留trace，重复失败停止，不先私下normalize跳过。

达到视觉阶段的run结果提供proof_file，持久化真实VerificationSession的candidate_id、visual_session_id、selected_pages、image_source='page_image_hashes'、image_hashes（物理页字符串到实际SHA256）。哈希必须与prepared及真正发送图片一致，并实际参与候选/证明身份。纯函数的text-only合成fallback不能用作生产通过证据。最终页包变化，即使observation字节相同，也清除当前证明、更新绑定并开启新盲读；终身预算/进度不重置。

wait_timeout_seconds只控制适配器调用实际TaskManager.wait的等待超时，用延迟的回环传输测试中断；不修改TaskRunner预算或另写测试调度。已有queued/running状态必须原子转interrupted并保留真实账本、失败和计数；不能因为state.json存在就保持运行中。封存必须含最终candidate_ready证明投影和完成的执行记录，网页只在封存成功后发布ready；不要求把尚未发生的操作系统进程退出伪装成已发生。

“保留文字会话”指保留assistant/user事实与工具历史；locate/extract阶段切换时可以更新system运行时指令，不能要求system全文保持不变，因为每阶段必须使用自己的runtime提示词。公共检查只对非system历史作前缀连续性核对。

实际已发请求在工作进程被终止后，如未收到完整usage，保留原始在途证据但终态用量标unknown，不能作为0收费或永久pending继续准入。

超时可能发生在持久化准入记录之后、测试服务收到请求之前。允许实际服务回执为0或1，账本保留0或1项且不得少于已收到的请求，状态计数与账本一致。已有准入记录但未取得完整响应时，发送结果不确定，用量同样标unknown；不能用服务尚未收到请求来删除准入记录。

选页工具回执可只返回选中状态和页包标识；下一次文字请求须保留所选页完整原文，若该原文已在同一会话的读页回执中，可复用历史而不重复发送。读页本身仍返回完整原文，检索返回真实片段。

封存执行记录须有真实pid/entrypoint、全部实际app模块路径及evidence_completed_at或run_completed_at，表示核验取证已完成。允许live execution_file在工作进程结束后补充finished_at/process_exited_at，因此不要求该live文件最终字节哈希与ZIP完全相同；ZIP中的执行投影与live的PID、入口及实际app模块映射必须一致。不能为了字节相等而伪造提前退出，也不能只封存导入运行器之前的空模块表。

完整CLI包必须满足ok严格为true、command严格为financials.income，目标H1记录period严格为quarterly。错误命令、失败包或annual记录不能靠Q2和日期冒充季度利润表。

视觉来源只允许本次实际发送的所选原图页，PDF文字库里有该页不代表视觉看过。选页变更或变为uncertain时立即使控制器当前证明、live state.current和持久化proof一致失效，清旧vision_hash；没有最终页包时proof.selected_pages=[]、image_hashes={}，不能沿用旧内部通过。终身计数和最佳进度不重置。

工具回执使用本次dispatch的事件/失败增量；当前search/read/select失败不能重复上一条同名工具成功。公共服务从实际任务目录只读抓取下次provider-bound请求发生时的state/proof，检查失效已完成；这些快照由独立回环服务观察，不给生产应用新增测试分支。


## 主线内的自修与服务验收

主线是0–8九条消息，每条任务内根据这些公开检查自行修正并重测。不能依赖另发repair/resume/observe或讲义外观察文件。运行`--through 2`先核对静态页面，0–8数字均可用；第5步以后还包含生产适配与组合检查。公共冻结/canary与所有其它冻结/本地检查串行执行。

唯一新增适配方法是`serve(scenario, output_root)`上下文，yield字典`{'base_url': 'http://127.0.0.1:实际空闲端口'}`。它调用正常启动也用的真实生产server工厂，真实TaskManager及新冻结worker，不能另写验收HTTP处理器、投影、财务计算或替换_spawn。project_root/runtime_root显式传入；本上下文runtime_root=output_root，任务在`output_root/tasks/{task_id}`。退出只停止本次测试拥有的服务/worker。已有validate/dispatch/compare/progress/run保持原签名。

scenario与run一致，只给pdf_path、已确认合成company、preset、model_endpoint/reference_endpoint、synthetic=true；没有模型答案、预选页或预计算reference。合成目录/身份与回环传输是依赖注入，不能替换扫描哈希、编排、页图、校验、计算或封存。真实普通服务不接受浏览器提交synthetic模式或模型端点。所有测试传输只用127.0.0.1。

真实HTTP接口：

- GET `/api/catalog`返回`entries`，每项至少id/company/thscode/filename/pages/pdf_sha256，id用于请求。
- POST `/api/tasks`使用JSON对象report_id/preset_id/idempotency_key/expected_source_sha256。Content-Type必须application/json且Origin与服务同源。成功202返回task_id；同键重试返回同一task_id。已有活动任务的不同键409、error=active_task_exists；扫描后PDF变化409、error=source_changed，不能启动worker。
- GET `/api/tasks/{id}`是当前持久投影，GET `/api/history`返回`tasks`数组，各项含task_id。重启服务可读同一任务历史，所有GET均不创建任务/请求。已有历史读取不要求当前真实服务凭据可用。
- 投影至少含task_id/status/current_stage/stages/usage/current/review/evidence。`stages`是六步有序数组，各项name/status/model/requests/model_tokens/pending/unknown/elapsed_seconds。status使用pending/running/done/stopped/interrupted；`usage`有requests/total_tokens/pending/unknown。全部数值来自实际ledger/journal。`current`沿用实际同候选两层证明，不能另造通过标志。
- `evidence`是允许的同源路由URL字典，GET实际可读对应文件；不把本地绝对路径当浏览器URL，不开放任意目录。路径穿越、绝对路径、软链接和不在允许清单的文件返回4xx。

`stage-journal.json`位于任务目录，`events`每项含递增sequence、stage、kind=start/end、Unix秒at，end含outcome。每次进入阶段先持久start再工作，所有出口关闭已进入区间，同阶段重入保留多个配对。run返回`journal_file`真实路径，封存嵌入该日志。程序阶段在回环服务收到请求时已能看到持久start，终态所有区间关闭；后来读取不让耗时继续增长。TaskManager必须先确认worker停止再追加中断收尾，避免两个进程抢写。

已知tokens、pending和unknown并列投影。保留reserved→complete/unknown的原始证据，终态ledger.requests每项`usage_status`只能known或unknown，不能残留reserved/pending。已知小计不因另一在途请求消失，不把未知补零。每个未完成请求在确认中断后转unknown。

`review.metrics`由生产formatter生成，至少含metric/current/prior/unit/display_unit/source_unit/current_raw/prior_raw。金额current/prior是两位小数字符串、单位亿元，unit与display_unit都与数字对应，source_unit与raw保留；EPS元/股。HTTP和前端都使用这些同一结果，不在adapter里转换或重算。

`trace.candidates`保存每次可解析文字submit，记录sequence/candidate_id/path/sha256。先保存再做来源及后续检查。来源拒绝、视觉退回、未到外部比较的候选不能丢；相同内容另次提交仍有独立序号和文件，不能覆盖。封存逐个核对所有候选及journal，ZIP成员名必须唯一。

公开服务`raw_content`直接作为provider-bound回复内容，可以是合法bare JSON、一个json/无标记围栏或无效文本；不替应用先清洗。生产文字与视觉共用严格单对象解析器。无效内容也走唯一分派器，保留原始usage与错误，连续两次无效回复停止，不假装财务候选失败。联合标题与混合8季度正例/负例由生产入口核对，完整raw参考保留，候选变化后重新比较而不覆盖早期引用。

静态DOM引用/Node语法和HTTP检查只证明相应边界。真正布局、点击、刷新、公司切换和晚到响应仍须用已有获授权浏览器工具在1280/375/320实测；不安装CDP或另建浏览器自动化栈。九消息实验的独立浏览器检查不能转成给新Agent的补充修复指令；若需额外指令，该版本实跑即未通过。

并发反例启动两个正常server实例并共享同一output_root，各自TaskManager同时POST，不能靠单实例串行请求或内存锁冒充跨实例创建锁。只产生一个真实冻结worker。另有冻结后、启动前破坏复制PDF的反例，必须在任何provider或reference请求前停止。联合表正例包括合并及公司、合并及母公司、合并和公司、合并和母公司四种标题，两期列均需明确合并；金额验收同时核对原值、两位亿元数字与单位。

所有默认本地单测通过 `python -m acceptance.local_checks --output runtime/step-N/local-checks` 启动，先创建tests/__init__.py。该公开入口在发现/导入前安装守卫，以项目根为top_level_dir，并把默认临时目录设到项目内。不能仅在tests/__init__.py安装守卫却用裸unittest discover -s tests，因为这种发现方式可能根本不导入tests包。公共acceptance.checks与local_checks严格串行。每条主Prompt均要求日志/诊断/临时文件留在本项目，不请求系统临时目录权限。

## 生产主干逐步完成

第1步实现原子持久状态和阶段日志，第2步建立正常server工厂/只读投影，第3步扩展同一个TaskManager及冻结worker，第4步接同一任务模型账本，第5步接来源循环，第6步接两层与首条封存成功链，第7步补齐有界反馈并通过全部35项，第8步完成网页验收和实际启动。适配器从第3步加载，未来模块延迟导入，不以导入副作用触发服务。没有新增Subject接口或第二套开发运行器。原30项测试体和断言保持一致，新增5项补齐原文结构与前端恢复，只把对应永久安全反例及成功链提前；阶段未实现的临时行为不能变成长期测试要求。

OpenCode以length结束或没有最终完成回复时，本条消息未完成，即使CLI退出码为0。九消息验证不得追加继续，须保留失败版本、修订教材并在新空目录重建。编码模型与推理配置记录在实验回执中，改变配置需公开记录，不能暗改后重发同一步。


## 原文行与列的结构绑定

新增source_binding_checks.py只用虚构公司与数值。第5步先通过结构化来源检查，第6步用同一来源绑定器比较文字/视觉，并从合成PDF经冻结worker完成封存。接受有完整年份证据的半年累计原文表达，明确拒绝单季、仅年份、错年和其他期末。original_label逐字保留受限的序号、加/减前缀；附注只能从明确结构位置排除，括号负数仍是完整财务数词。表头先证明各列年份/合并口径，再按列索引选行值，保留不适用/横杠占位，不取前两个数字。每行绑定自己的来源页与表头，续页列序可不同；无法唯一恢复就失败。

## 正常网页使用的恢复模块

第2步创建web/task-view.mjs，原生ES模块，不需要前端框架。正常app.js启动与选择/轮询实际调用它，不能只为测试另写模块。公开Node检查导入的就是这份生产文件。Node在第0步列为环境前提。

导出createTaskView({getJSON,storage,present})，返回三个异步操作restore()、select(reportId)、refresh()。select('')明确取消选择。getJSON(url,options)返回已解析JSON，所有恢复请求只能GET，接口是/api/catalog、/api/history、/api/tasks/{task_id}。storage使用浏览器getItem/setItem/removeItem接口。固定键earnings-review.task-view.v1，值为JSON对象，只存report_id、source_sha256和可选task_id，不复制状态、结果或模型。

present(view)发布mode、generation、selected、task、message。mode为loading/active/last/history/empty/error之一；generation是非负整数选择代数；selected为catalog中的报告对象或null；task为完整服务任务投影或null；message为可见说明字符串。请求前发布loading并禁用创建；只有成功读取且确无匹配记录才能发布empty。异常发布error，不能清成无记录。终态已有任务使用last，仍显示真实成功/停止结果，不能冒充新运行。

任务和历史投影都包含task_id、report_id、source_sha256、preset_id、status、created_at、updated_at。时间为Unix秒数值。身份与preset来自冻结任务，不以当前catalog覆盖。先用id+PDF哈希确认报告，再匹配任务；名称/文件名不能用于兜底。完整任务GET与history的task_id/报告/哈希/preset必须一致，否则拒绝关联。存在匹配活动任务时优先活动任务，其次有效记忆任务，最后按created_at及task_id选择最近终态。无选择提示时仅自动恢复唯一合法活动任务。过期或错哈希的提示不得绑定旧任务。

restore从持久提示及服务端记录恢复；select读取所选报告的已有记录；refresh读取同一选择当前事实，过期响应不得渲染。正常POST显式创建T2后调用同一select重新hydrate，后续refresh不能覆盖为旧T1。创建响应也检查发起时generation。控制器导入不自动启动请求/定时器，不包含创建或业务编排；app.js负责现有POST和DOM绑定。

recovery_checks.py第2步在Node执行生产模块的刷新、重选、唯一活动任务、同名隔离、哈希/身份/preset、终态、新任务替换旧终态、失败和晚到响应。第7步把同一模块接真实生产server GET，活动任务读取已知tokens及pending；重新实例化、取消再选、终态和服务重启都不能增加任务或回环服务回执。Node证明状态逻辑，真实浏览器仍需在第8步证明DOM接线与交互。

## 重复执行验收

每次acceptance.checks调用在所给输出目录内创建新的run-*子目录，保留前次现场。本次开始即把根summary.json指向本次running记录；成功/失败/未完成都更新同一指针。结果含output_directory和invocation_id。不要读旧ok、删除持久任务或改幂等键规则来消除测试污染。同一用例内两server/服务重启仍共享该用例自己的runtime_root；不同完整调用互相隔离。公共与本地冻结检查仍必须串行。

column_evidence逐字覆盖每个column_path组成项，允许同一组成项在多页有重复引用，因此不强制数组等长或按zip截断。每个value_page的局部表头仍须明确证明该页的年份、半年、合并口径和列序；全局某页通过不能代替续页证明。

## 局部来源与CLI命令边界

半年必须正面证明一月起累计至六月三十日，或截至六月三十日止六个月，并分别证明2026/2025；不能用“含六个月且未命中几个坏日期”的排除法。无截止日、五月三十一日或任意其他期末、六月三十日止三个月都不能推出H1。每行绑定本页中真正包含该行的局部表格及最近完整连续表头，按该表头证明期间、年份、合并口径和列索引。不能取整页第一组表头，也不能让前页H1引文替续页单季背书；同页另一张表的列序不能用于当前行。证据不足或多个局部表格无法唯一关联就失败，不猜索引。公开test_05_structured_source_binding包含这些反例；文字与视觉仍共用这个绑定结果。

financials.income是schema与响应command的能力ID，不是单个CLI命令。读取schema可用 hithink-finance schema financials.income；实际查询必须拆成命令组和子命令：hithink-finance financials income --thscode 已确认代码 --period quarterly --limit 8 --format json，可加--output保存完整响应。以已安装官方schema.command数组或内置帮助核对参数，不把点号ID当argv。新增test_06_reference_cli_transport通过正常Subject.run、冻结worker和同一个生产ReferenceClient执行离线假CLI。显式synthetic场景只注入reference_cli绝对可执行路径，冻结入非密配置；未提供reference_endpoint时走正常CLI分支，普通任务仍默认hithink-finance，不接受网页提交测试路径。测试只替换可执行传输，不能另造取数器、解析、比较、运行器或封存。该检查核对真实argv、一次income调用、零参考HTTP调用、完整原始envelope及最终两层10/10封存；错误命令必须在本步被拦住。

## 完整含义与结构位置

来源绑定按证据含义逐项证明，不能用关键词共现作默认值。期间须完整匹配至六月三十日，或明确完整一月至六月累计；2026年1月1日至6月30日是合法H1，至6月15日、6月29日、其他期末及五月三十一日都不是，不能匹配到“6月”前缀就通过。每行选自己的最近完整连续表头；本表明确合并标题可为不另列分组的两期列证明合并，联合表则需明确分组。公司/母公司表不能因页边或别表出现合并就默认全列合并，缺本表口径证明应失败。unit_quote必须实际证明该行声明的单位；“除基本每股收益外，金额单位为人民币万元”只能说明金额，不能证明EPS元/股。EPS的每股与未缩放元须有明确关系，不能用每股+元子串放行千元/万元/亿元或排除句；可用本行基本每股收益(人民币元)原句。附注按明确列位置排除：附注列内三(19)或裸(19)均可为附注，不能因缺中文序号就当财务数；财务单元格的括号成本/损失仍须完整保留为负数。无法唯一关联表头、口径、单位或单元格时失败并补证。文字与视觉使用同一个生产绑定结果。

## 完整单位和目标记录身份

EPS先识别与该行直接关联的完整单位表达及币种、倍率，再归一化；元/股必须是完整单位，不能在万元/股、千元/股、亿元/股、美元/股或港元/股中匹配元/股子串。允许元/股、人民币元/股，或明确基本每股收益行中的未缩放人民币元。未知、缩放或非CNY的EPS单位均不猜成元/股。quote可包含周围金额万元说明，只要本行EPS自身另有明确未缩放元证据就可接受；不能全句出现万元就一律拒绝，也不能全句出现元/股就一律通过。

官方CLI envelope的每条目标H1记录必须独立提供非空字符串thscode并与expected_thscode逐字相同；缺字段、null、空串或错误代码都失败，不能写成“存在才核对”。顶层匹配代码不能为缺代码的item背书。规范reference.records夹具可以由其规范顶层代码证明身份，这项适配不得反向放松官方data.item的逐条要求；两者仍进入同一个生产归一化边界。

## 编码工具路径核对

路径约束：每步先从工具输出确认当前项目根目录。支持相对路径的命令和文件工具使用项目相对路径；要求绝对路径的写入工具，必须从刚确认的根目录原文生成，禁止重打、猜写目录名或日期。写入前确认父目录实际存在且属于本项目；无法确保时改用当前目录下的相对路径写入命令，不试探项目外写入。
外部目录权限被拒绝后没有完整stop回复，仍是未完成。该规则属于九条主消息的开发验收，不以应用运行时测试冒充工具路径正确。

## 编码实跑配置与首写检查点

本版默认编码配置为macOS、OpenCode＋DeepSeek、Build、deepseek/deepseek-flash、High推理档，输出上限沿用本机32000，不启用实验性输出覆盖。连接编码模型后直接从第0步开始，不额外发送测试对话。CLI的run方式使用 --model deepseek/deepseek-flash --variant high；交互界面按本机模型选项切到High。若High出现无进展、输出上限耗尽、以length结束或效果不足，保留该次结果，在全新空项目中用Max重跑（CLI使用 --variant max），不把两档结果合并为同一次。编码模型和财报运行模型不是同一个配置，财报默认仍是Qwen27B。其他配置需另记实跑。
本步先落盘再扩展：首次业务写入前，只读observation.schema.json、locate/extract运行时提示词和现有接口必要片段，不通读全部验收脚本。先写app/contracts.py与app/extract.py的最小通用实现、明确未实现的失败结果并编译；初版落盘后立即运行through5公开检查，再只读失败所指的测试方法片段，逐段补行列绑定、期间/单位及来源动作循环。每段写入和编译后再分析下一段，不在单次生成里推演整步最终方案。中间缺功能必须真实失败，最终仍须全部11项公开检查与本地检查通过，不能以初版或占位交付。

## EPS正向完整单位语法

EPS单位使用闭合的正向语法：先从原文中提取与基本每股收益本行直接关联的完整单位表达，保留币种和倍率边界，再对整个表达完整匹配。只允许元/股、人民币元/股，或明确基本每股收益本行/专属单位说明中的人民币元。可归一化空白和全半角括号，不能删掉未知币种、币种前缀或倍率。禁止先排除少数已知外币/倍率，再搜索元/股后缀；增加黑名单不是完整单位解析。日元/股、欧元/股、未知币种前缀及人民币百元/股、人民币兆元/股等未允许表达都应失败或补证，不能默认人民币。同一引文可以同时有金额万元说明和基本每股收益专属单位，须分别绑定；裸行名基本每股收益加明确专属说明“基本每股收益单位为人民币元”是合法证据。不能因整句含万元就拒绝，也不能因整句含元/股或人民币就通过。既有万元/股、千元/股、亿元/股、美元/股、港元/股负例和本行人民币元正例继续保留。

文字与视觉必须复用第5步闭合的正向完整单位语法。先绑定EPS自己的完整表达，再完整匹配允许集合；不能在verify中以“排除几个币种后含元/股”或含人民币作为替代。EPS专属说明中的人民币元应通过，日元/股、欧元/股、未知前缀和未允许倍率均失败。

test_05在同一既有四列表中配对修改裸EPS行名和专属单位说明；数值、表头和其他四项金额证据保持一致。允许单位与外币、确定生成的未知前缀、未允许倍率都有配对，不能只增加拒绝项而破坏合法证据。仍为35项，原30项函数体不变。

## 完整表达两端与实际模型角色

完整匹配必须同时证明左边界和右边界。先按EPS本行的成对括号或专属“基本每股收益单位为”说明的完整分句提取单位，不能把元或元/股的位置当作提取终点。提取后只归一化空白和外层括号，对整个剩余表达full-match允许集合；任何未消费的币种、倍率、汉字、字母、数字或斜杠后缀都应失败。此规则适用于三个别名的所有分支，人民币元也不能用未锚定search作为回退。例如人民币元/股合成尾缀01、人民币元合成尾缀01不能从中截出合法部分；周围金额说明仍应与EPS自己的单位分句分开。不要只补几个后缀黑名单或只检验左前缀。

模型角色由实际阶段在唯一客户端/分派边界强制决定：locate、extract及其文字续跑使用冻结text_model，vision及其全部视觉续跑使用冻结vision_model。不要依赖默认role=text，也不能只把vision写在日志而发送text_model。若客户端显式接收role，worker必须实际传递并检查它；否则客户端按stage唯一解析，不能保留两套互相矛盾的默认值。qwen9的真实请求payload应是9B文字、27B视觉；qwen27两者同为27B。本地合成检查核对实际已发送并持久化的request.model与冻结配置，不只检查预设字典或界面标签。

公开test05保留原有三种合法单位对照，并对它们生成两端未知前后缀反例；另验证本行人民币元别名不能绕过完整匹配。test06的结构化完整链使用混合预设，核对正常冻结worker实际发出的文字与视觉模型ID。测试仍35项，原30项函数体不变；合成混合预设不等于9B真实财报已验证。

## 长表与同页表格归属

局部表头按同页表格归属判断，不按固定回看行数判断。在现有来源绑定模块内部为每个物理页建立表格区段，记录本表标题、完整期间、年份列、口径列、附注位置及生效区间。目标行必须位于本表完整表头之后；表体有多少普通项目或换行说明，都不改变归属，不能用固定13行或另一个更大常数限制。表题与表头也按结构连续关系关联，不另设一个固定距离掩盖问题。遇到新的财务表题或新的列头结构，立即结束旧区段；新结构为单季、公司/母公司、缺失或冲突时必须拒绝，不能跳过它回借较早合法表头。普通明细、净利润分类和每股收益分项不是新表题。同页后一个合法完整表可以独立通过，不能因前表不合法就拒绝整页；每页重复表头使用自己的列序。页边界清空区段，续页仅有“续”字而没有本页完整表头时失败，不继承前页。保持已有逐字行名、完整数词、单位、附注、占位单元格、年份与合并索引检查，文字与视觉复用同一个binder。observation schema和六个Subject接口不增加字段或入口，也不新增测试专用解析路径。

公开test05用两种不同表体长度、表内分项、较近新表、续页缺头和本地列序的正反对照验收。test06在同一个正常冻结worker链上使用长表；原有两层比较、CLI与模型角色断言不减。仍为35个方法，原30个方法不变。

## 新列头的本块期间与唯一财务投影

每次新列头都重新证明本块期间。把表名/报表口径与本块的期间证据分开，不能把旧标题日期当作可继承的H1默认值。新列头之前结构连续的独立期间说明属于新块，不能先丢进旧表body再忽略。本块收集所有明确期间声明后统一判断：单季、非六月末、缺失或H1与Q2冲突都失败，两种冲突顺序都一样；不能拼接旧H1标题和新Q2说明后采用任意匹配，也不能last-wins。首块可用同块完整标题证明H1；没有新标题的重复列头必须用自己的完整H1说明证明期间，并使用自己的年份/口径列序。坏块仍占据自己的来源区间，不能过滤掉再回借早期好表头。普通项目、分类与换行不改变已完成表块；页界清空。文字和视觉复用这一生产归属规则，不增加模型字段、Subject入口或另一套解析器。

财务计算只生成一份规范review投影。先从来源绑定的完整原数词计算精确Decimal规范值，最后对每个展示结果ROUND_HALF_UP为两位。营业成本展示和增长按费用正值幅度；原始括号与符号仍保留。review.normalizations保留一条operating_cost记录，policy=expense_magnitude，current_signed_yuan/prior_signed_yuan为带原符号规范元字符串，current_yuan/prior_yuan为精确正费用幅度字符串。五个review.metrics各自保留原有字段，并含yoy_percent字符串或null；上期不为正时null。EPS不套金额倍率。毛利润使用未舍入收入减成本幅度，毛利率和归母净利率使用未舍入规范值相除，不能从两位展示字符串重算或相减。

review的最小财务字段固定为metrics五项、gross_profit={current,prior,unit:"亿元"}、gross_margin_percent={current:百分比字符串或null}、net_margin_percent={current:百分比字符串或null}及上述normalizations。不再输出重复金额副本review.summary或review.series；保留人工复核、来源和证明元数据。图表从同一metrics选择值，额外派生输出若存在也须使用同一未舍入计算，不要求新增两期利润率差额功能。在实际生产web/task-view.mjs导出纯展示选择函数reviewCards(review)，返回恰好三张卡：{id:"revenue",label:"营业收入",current,prior,unit:"亿元"}、{id:"parent_net_profit",label:"归母净利润",current,prior,unit:"亿元"}、{id:"gross_profit",label:"毛利润",current,prior,unit:"亿元"}。前两张按metrics的准确metric ID取值，毛利卡只取review.gross_profit，不能复用收入对象。该函数不做财务计算；正常web/app.js的实时结果、刷新和历史恢复都调用同一函数渲染摘要，不能只为测试导出却让真实页面读另一套数据。公开test_06通过同一个正常冻结worker检查Decimal结果、成本记录和实际生产JS函数，并配对改变收入/毛利润来证明卡片归属。

新增内容只扩既有05/06；仍35方法，原30方法不动。合成当前收入/成本让两位展示相减产生错误，另一期收入与毛利展示不同，能检出错卡别名。公开资料只包含虚构数值，不含真实财报答案。

## 显式边界先于表头完整性

先识别表头边界，再验证表头是否完整。这两个判断必须分开。识别到新的财务表题或以独立项目列单元格起始的显式列头，就立即关闭旧区段并建立新块；即使新头只有项目/附注、没有年份、只有一个年份、缺少可证明唯一列归属的口径证据、口径列数不符或声明冲突，也保留为拥有后续行的无效区段。不能以至少两个年份、期间成立或口径解析成功作为是否存在新边界的条件，也不能跳过无效块后回找旧H1。新块先收集自己的连续期间和全部列声明，再证明唯一两期合并索引；本块相互矛盾的多次口径声明不能first/last-wins。合法四列中重复的合并/公司单元格不是声明冲突；本块合并单一表标题与完整两年份可以证明口径，仍不强求独立口径行。目标行只使用自己所属的块，所属块无效就失败；既有紧凑表形的兼容路径也不能绕过已发现的无效块。后一个完整本地表头可以恢复有效，不因坏块拒绝整页。只有显式表格结构触发边界，项目开发成本、普通项目附注说明及含年份的自然正文不是独立项目列头；普通长表体、分类、换行与页界规则保持不变。文字与视觉共用同一binder，仍不新增观察字段或Subject入口。

既有05/06加入完整新头、零/一年度、必要口径缺失及冲突的配对。坏头后的指标保持旧四列原序和原值，不能靠数值错位偶然失败；普通项目正文与坏块后完整新头仍应通过。正常长表/舍入陷阱的同一冻结worker与38/27行页长保持，仍35方法、原30不变。

## 完整表头说明链

表题到列头也按完整结构链关联，不能再有另一处距离窗口。在同一物理页向前保存尚未归属的表题、全部期间声明和连续单位说明，遇到所属的显式项目列头时一次消费整条链。标题、期间与列头之间可以有任意条一致的单位说明，不按行数、字符数或最后N行截断，也不扩大一个固定回看常数。结构归属只由新的表题、显式列头、普通表体或页界决定。已完成表头进入表体后，清空供下一个列头使用的待归属链，但普通长表体和分类不取消当前有效owner；后来的无标题列头必须有自己的期间，不能穿过旧表体借标题。新列头无论年份或口径是否完整都先结束旧owner，无效块保留且阻止任何兼容路径回退。整条本地链中的明确期间统一判定，较长单位说明不能掩盖H1/Q2冲突，两种顺序都失败。清晰的合并单表标题与完整两年份仍能证明口径，不强加独立口径行。文字、视觉和最终compare都复用同一个生产binder。现有test_05用16/64行连续单位说明配对合法联合表与合并单表、冲突期间和无效owner；test_06同一次正常冻结worker同时覆盖长表体和长表头，不新增观察字段、Subject接口或测试专用解析器。

05保留原长表体、完整EPS及边界反例，再加入16/64行原有单位说明的合法联合/合并单表和长链坏头配对。06仍只有一次正常worker：第一页38行原样，第二页将16条表体填充移至列头前改为原有单位说明，仍27行，目标值、候选、EPS行位置和两页边界保持，PDF与视觉页图按新页面正常生成。35方法、原30和全部旧断言不减。

## 本块每条期间逐一认证

每个本地表块的期间认证使用完整的正向规则。先发现属于本块的每条明确期间声明，再把整条期间表达归一化为完整目标H1、明确其他期间或无法完整解释三类；只发现合法H1的匹配不是声明发现。至少存在一条目标声明，并且所有明确声明都完整等义于目标H1，才可通过。目标沿用已有1–6月、1月1日至6月30日、截至6月30日止六个月的等义形式；明确的其他结束日、其他时长、其他起点、缺日或缺时长都拒绝，不能因另一条H1成立而忽略。保留每条声明及原文，不先过滤无法解析的声明再all，不用any(H1)+noQ2、黑名单、最后一条或未锚定子串搜索代替。合法重复或等义H1可多次出现；2026与2025两期的月份窗口可等义，列年归属仍由已有年份检查确定。只有年份的普通列单元格或正文不是期间声明，单位说明也不是声明。本块标题中带期间的分句和自己的完整连续metadata链都纳入认证，不能只看候选主动引用的好句；保持无固定距离、旧表体阻断新头借证、无效owner不回退、后完整块可恢复和合并单表口径例外。表头与两期column_path复用同一期间语义，文字、视觉及最终compare仍使用同一个生产binder，不新增观察字段、Subject入口或第二解析器。

05/06在同一原四列表中保留合法候选与全部原数词，加入16/64行单位说明隔开的H1与其他结束日、时长、起点、缺日或缺时长双序；合法重复及等义H1也配对。已有普通年份表体、年列、坏块恢复和所有EPS/长表断言不变。06只新增纯compare子例，正常worker两页逐字保持上一版38/27布局，仍一次运行。

## 开发执行顺序与结果证据

每步先确认实际项目根目录。生产修改采用“小段写入→编译→检查→按失败局部读源”的顺序，在同一条消息内自动继续。第5步首次业务写入前禁止读取acceptance下测试与fixture源码；最多两次必要接口读取，工具回传正文合计不超过6000字符，只读当前生产接口、observation约定或本步runtime提示词的必要片段，已在对话中的约定不重复读取。首次写入须新增本步可执行生产行为，目录、文档、注释或纯占位不计。首次生产写入并编译、取得本步真实失败后，每轮只读首个失败涉及的一个测试定义或一个fixture helper的局部，单次以80行和4000字符为参考目标；完整定义更长时只读当前失败所需的连续片段并记录实际范围；先修生产并编译、重测，再展开下一个问题，不连续拼读整份源码。读取限制只约束开发工具回传，不限制财报原文、来源metadata链或生产绑定距离。公开最终检查与默认本地检查仍全部执行且串行，原断言和全部业务规则不变。

完整检查日志保留在本项目runtime/step-N，不把全量日志展开到对话。执行python -m acceptance.checks --through N时只将stderr重定向到该步日志，stdout中的真实JSON结果原样回传，保留同一次检查的退出状态；失败再按用例名和行号读取首个相关片段。不要把真实结果截断、改写成自述，或用后一次命令输出冒充本次结果。本地检查也保存完整日志并回传实际结果。日志与测试输出仍全部可审查。

这是执行顺序检查，未修改35项业务断言。首个生产写入、编译、失败与局部读取须能从真实工具事件定位；不能仅凭Agent自述、文件mtime或CLI退出0判为完成。

## 表块与两期列路径的单一闭合期间证书

在现有来源binder内建立唯一内部纯入口certify_period_context(fragments)，返回一个PeriodCertificate，保留每条claim的完整原文、位置和target_h1/explicit_other/unresolved分类；accepted只由claims非空且每条完整target_h1派生。表块及current/prior两期column_path只消费同一个证书结论，不分别接收好句/坏句列表再自行判断。先按声明边界发现完整或缺损的明确期间，再认证整表达，不能把合法H1匹配当发现。截至加可选年份、结束日期、止及其时长或缺损时长属于同一完整声明；缺日或缺时长仍保留为unresolved，有无年份不改变完整性。已有完整起止日期和1–6月表达也按整句发现。日期正则只能提取端点字段；裸2026年6月30日、六月末命中或H1子串不能独立生成target_h1，已发现的坏声明不能再次被扫描成更短的好日期或好H1。不能让unresolved恒为空，不能只枚举几个已知缺损句式。至少存在一条完整目标声明，且所有明确声明都完整等义于目标H1才通过：完整1–6月、1月1日至6月30日、截至6月30日止六个月为既有允许形式；保留已支持的可选年份和空白。其他结束日、起点、时长或无法完整解释的声明都拒绝。不先过滤无法解析的声明再all，不用any(H1)+noQ2、有限黑名单、最后一条或未锚定search放行。合法重复或等义H1可多次出现，2026与2025月份窗口可等义，列年归属仍独立按原2026/2025和来源列索引证明。只有年份的普通列单元格或正文不是期间声明，单位说明也不是声明；不要把普通年份粗暴判成unresolved。本块标题期间分句和完整连续metadata链全部认证，保持无固定距离、表体阻断新头借证、无效owner不回退、后完整块恢复及合并单表口径例外。column_path复用同一期间证书，每个额外期间组件即使有逐字引文也必须完整认证，不能让另一个好H1洗掉五个月或缺时长；path原文覆盖与列年检查另行保留。先写证书入口并编译，再将本地表块和两期path都接到它，搜索全部有效性出口，删除或替换旧_period_target/_bad_period的独立宽松判定，不能仅新增未接入helper或在compare再补黑名单。文字、视觉和最终compare继续走同一生产binder，不新增观察字段、Subject接口或第二解析器。

公开05/06仅在已有虚构四列表中增加显式年份完整/缺时长配对，以及合法表不变时两期path的等义H1、五个月和缺时长逐字引文双序。新增06为纯compare子例，不增加正常worker；所有原180来源调用与35方法均保留。80行/4000字符是开发局部读取参考目标，真实输出如实记账，不作为新增业务门槛。

## 同一原文片段中的多条声明

一个fragment、一行、一个path组件或一条quote都可能含多条期间声明，不能把它当作单条claim。证书内部严格依次执行：先从左到右完整发现每个期间意图的独立声明span，再逐span整表达分类，最后全称认证。每条记录保留fragment_id、start/end半开原文范围、raw和status；每个明确期间起点都必须属于且仅属于一个完整span，缺日、缺时长或无法完整解析仍产生unresolved记录。先完成覆盖清单，再产生任何target，不得把已有h1/other标记作为是否检查剩余文字的条件。发现器不能只寻找成功的H1模式。已消费span不能重扫成更短目标，后一条截至声明不能借前一条的日期或时长；同一片段内各声明独立保留，不按归一化状态去重丢失原文。证书accepted只在声明非空、每条完整target_h1且不存在未覆盖/待分类的期间意图时为真。完整H1；完整等义H1在同一fragment中双序均通过，完整H1；截至同年6月30日止期间在同一fragment中双序均拒绝。分号可界定已有复合片段中的声明，不能仅split后search一个好子串；普通表名、公司、单位和年份保持中性，整表达匹配作用于每条声明span，不要求整个表题或整条引文都是期间词。

公开05/06在原四列表上成对改变同一片段的期间说明，保留全部原用例；block沿用16/64连续metadata链，两期path分别保留逐字引文。新增均为纯validate/compare，不改唯一正常worker的38/27页文本，不扩大表格或公开接口要求。第5步只保留原最小JSON首写→编译→首次真实失败的硬检查点；之后先按真实失败局部读取，再修改生产、编译和重测。期间覆盖生产者→三处消费是实现依赖，不增设对应测试读取前的第二道写入门槛。

## 三种既有期间表达各自独立通过

三个已允许完整家族各自都足以成为block和current/prior的唯一期间证据：1–6月、1月1日至6月30日、截至6月30日止六个月期间，每个家族都允许带年或无年。发现和整表达分类共享同一可选年份语法，不能只有月份区间或截至形式支持无年，而完整日期范围强制首端年份。完整月日范围本身必须产生声明span；年份缺失不是缺日或缺时长，不能当中性文字跳过或返回空claims。year=None如实保留，2026/2025归属继续由独立列头与来源列索引证明；不能向原文补造年份、改raw/span，或在adapter/compare另加无年H1兜底。已有重复终点年份、空白和区间分隔符支持保留，不扩通用日期格式；同一生产者仍保留其他窗口和缺损声明并完整认证，不能仅枚举几个target短句。每个允许家族要在没有另一种H1标题、metadata或path代偿时独立通过。

公开05/06各增六个sole-family正控；所有原216调用、缺损/其他期间负例和唯一38/27正常worker保留。当前规则在V22冻结前明确，V21开发次序false与无年完整日期误拒事实永久保留，不作追溯改判。

## 表题保留全部期间声明

完整raw title与metadata、两期path共用同一声明发现器；含利润表或损益表等中性表名，不授权裁剪标题、仅取首个期间前缀或提前return。调用者传完整原文，先发现标题内全部期间声明，再逐条分类；删除或替换表题专属first-prefix捷径，不在调用方或兼容路径重建。允许既有中性表名及口径词段，不能让它吞掉后续期间意图；完整H1后仍检查剩余原文。同一标题的两个完整等义H1双序均通过；完整H1与缺时长声明双序均拒绝，不能靠顺序、后面metadata的合法H1或另页EPS代偿。

公开05/06各增四个title-only配对，原222来源调用与35方法、原30方法体、唯一38/27正常worker保持。新增用例只改原第一页表题及逐字scope quote，metadata、两期path、数字、列头和第二页完全不变。V22的来源falseaccept及已记录开发指引偏离保留，不能追溯改判。
