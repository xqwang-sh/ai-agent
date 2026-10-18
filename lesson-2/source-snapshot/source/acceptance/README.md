# 公共合成验收

这里没有成品应用。fixtures.py 中的公司、页、数值及服务响应都是编造的。checks.py 调用学习者自己实现的生产模块，不能把测试数据放进真实公司的 review。

先读 checks.py 与 fixtures.py，再实现 app/acceptance.py 中唯一工厂 create_subject(project_root)。工厂返回对象，下列方法只适配生产代码的输入输出，不重新实现校验或阶段循环。

- validate(observation, pages, selected_pages, expected_company=None) 返回 passed、rules、五项 bound_rows。rules 非空即不能通过。pages 是 physical_page/text 对象数组。
- dispatch(actions, pages, phase) 驱动生产 ExtractSession 的同一动作分派。返回 trace 动作名称数组、candidate_count、source_actions、failures。裸selection和裸完整observation先归一化。
- compare(text, vision, reference, pages, expected_thscode, expected_company=None) 调用生产两层核验与反馈脱敏。返回 internal/external，各有 passed、matched、total，以及只含规则和指标的 feedback。合成 reference.records 是规范化传输夹具，进入生产唯一H1筛选和比较函数，不另写测试比较。
- progress(events) 驱动生产 WorkflowController，返回 snapshots、stopped、reason、counters。snapshot 含 no_progress、ever_passed；counters 含 failed_gate_evaluations、feedback_emitted。gate事件 rules=[] 表示通过，candidate_changed仅使当前证明失效。未知终态usage阻止后续准入。
- run(scenario, output_root, after_create=None, wait_timeout_seconds=None) 调用网页相同的 TaskManager 创建、原子冻结和真实 TaskRunner。after_create(task_dir) 在冻结完成、启动子进程前执行。工作进程实际从 task_dir/program 执行。仅替换模型和外部传输，不替换编排、检索、页图渲染、计算、核验或交付。测试传输脚本是显式测试依赖，不写进生产预设，真实运行不启用。

run 返回真实路径 task_dir、state_file、trace_file、ledger_file、freeze_manifest_file、execution_file、sealed_archive、prepared_file、proof_file。允许适配命名，禁止伪造成功摘要。

state_file 包含 status、review、counters、latest_failure、current。current 有 candidate_id 和 internal/external，每层有 passed/matched/total/candidate_id。counters 至少有 failed_gate_evaluations、feedback_emitted、feedback_requests。两次无进展失败应显示两次失败评估、一次已发反馈、一次实际补证请求。

trace_file 包含 actions 和 requests。actions 每项有 action；requests 按实际调用顺序含 request_id、stage、session_id、request_path、response_path。request_path 是真正送到传输边界的无认证头请求，messages 与 model_receipts 中同 request_id 的 messages 一致。response_path 保存原始usage。ledger_file 含 requests 与 total_tokens。

freeze_manifest_file 的 files 每项含相对 program 根目录的 path、sha256。execution_file 含实际 pid、entrypoint、loaded_modules 名称到实际模块文件路径映射。sealed_archive 含同样的 program/ 文件和哈希。工作区后改的模块、提示词、配置不能影响已创建任务。

第5步执行 `python -m acceptance.checks --through 5`，第6、7、8步改成相应数字。第0步可先用 --through 0。缺接口、阶段或证据就失败，不能skip、删断言或新增测试专用成功路径。函数检查用于定位问题，第8步完整生产组合才证明离线接线。

默认检查在导入应用前阻止本进程及继承环境的Python子进程出站连接、DNS和常见外部网络命令，只允许回环测试服务。这是进程级保护，不是操作系统沙箱。不导入live测试、不查询真实证券身份、不读服务凭据。应用默认单元测试也在相同守卫下运行，联网检查必须显式启用。

合成组合包含来源失败后检索、视觉分歧退回、外部分歧退回，以及终身无进展。完整循环使用同一合成PDF中两张相互竞争、各自原文引用有效的不同数字表，测试图/文字或外部不一致时退回修订。第二次候选选择另一张实际印刷的表，不是把同花顺数值填进原表。外部一致只证明该合成候选的比较结果；两张原页和先前差异必须保留，不能据此声称已解决文档权威性。源检查负例会另测交换或错误取值；文字检查不声称通用理解PDF的二维排版。视觉请求只含完整原页图和身份/期间任务，不含抄录文本、参考答案、文字历史或外部差值。

另需浏览器核对运行中/终态文字、刷新、重复点击、公司切换、晚到响应。真实任务的身份、模型回执、原始页图、私有同花顺响应、当前两层10/10和封存交付，在第8步手动运行后单独核对。合成验收不能替代真实运行。

run场景不提供预抽取页文字或模型/参考答案。公共services.py拥有回环HTTP传输脚本和独立回执，传给run的scenario只有pdf_path、合成身份、preset、model_endpoint与reference_endpoint。生产ModelClient在注入的测试端点按正常Chat Completions形状发请求；ReferenceClient测试传输GET/POST reference_endpoint取得与已安装CLI相同的完整success envelope（data.item）后，仍用同一个生产解析/H1筛选/比较。只在显式合成模式使用这些端点，不读真实服务密钥。生产代码不能导入public fixtures脚本取得答案。
prepared_file含pdf_path、pages_path和images，每个images项有path/sha256/physical_page。pages_path的逐页text须与传入PDF实际pypdf提取一致，图片必须从同一PDF渲染。公共测试独立记录服务边界请求、响应ID和完整usage，与任务证据逐项对齐。app/contracts.py、prompts/runtime/extract.md、contracts/workflow.json是本讲已明确约定的路径，冻结检查会先导入app.contracts再改工作区这三项。

视觉自己的证据失败必须留在同一视觉会话，后续请求保留它自己的历史；新文字候选才创建新盲读会话。公共检查只在每个视觉会话首请求排除文字/外部答案，续跑允许自身原回复。来源工具预算检查会连续检索6次后停止，不能把检索动作计成财务失败。每个实际模型请求的system指令必须包含冻结目录对应runtime提示词原文。

外部参考可在本轮私有冻结后缓存。combined/external_revision允许1–2次实际HTTP取数，但trace_file.external_evaluations必须保存两次实际比较，不能复用通过标记。每项含递增sequence、candidate_id、candidate_path（原始observation对象）、candidate_sha256、reference_path（保留的完整原始CLI形状JSON响应）、reference_sha256、after_request_id（本次盲读视觉请求ID）、passed/matched/total及comparisons（metric/period/current或prior/matched）。两候选内容哈希不同、同一参考哈希，第一轮8/10失败，第二轮10/10通过；适配器从真实生产比较记录映射这些字段。数据仅留私有核验记录，不进入模型反馈。冻结允许prompts/runtime下的运行时提示词，禁止根目录runtime输出及密钥。

外部核验的expected_thscode来自已确认的报告身份，不能从参考响应反推。日期必须解析且年份与record.year和目标年一致。列头证据不得为空，也不得用较短引文证明虚构的完整path。模型回执中的prompt/completion/total须齐全且为非负整数，total=prompt+completion；缓存量含在prompt内，不可超过prompt。缺失、负数、非整数或矛盾回执标unknown并停止后续准入，不补零或猜测用量。每张实际发送的视觉图前紧邻text标注physical_page=原PDF物理页编号，自身续跑保留相同图片和标注；不以图片序号替代。

封存不能只有文件路径索引。ZIP必须实际包含与本轮哈希一致的原PDF、逐页文字、所有已发模型请求及原始响应、原始页图、各候选、冻结参考、执行记录、prepared和冻结manifest，以及完整模型请求账本和动作/比较轨迹。公开检查逐个核对实际文件内容哈希，不能以prepared.json里列出图片路径代替嵌入图片，也不能只打包最终成功候选而丢弃本轮失败和补证。状态投影可在封存后加入ZIP哈希等元数据，原始回执及比较记录不得改变。

原始参考响应固定使用官方CLI的{ok,command,data:{timestamp,item:[]},meta}形状。记录字段为thscode/ticker/period/period_end_ms/report_date_ms/fiscal_year/fiscal_period/currency和财务字段，不能要求未文档化的cumulative字段。季度Q2是报表窗口，不等于单季度利润。以financials.income命令语义、quarterly窗口、唯一fiscal_year/Q2及CNY核对H1；期末毫秒按明确的Asia/Shanghai报表日期规则转换，要求6月30日且年与fiscal_year一致，保存原始时间戳与规则，不按操作者本地时区转换。直接compare的规范records夹具仍用于独立诊断；两种输入必须进入同一生产参考归一化和比较边界，不能只在synthetic分支转换。

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
