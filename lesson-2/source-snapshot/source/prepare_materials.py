"""Build answer-free contracts for the learner's own coding Agent."""
import hashlib
import json
from pathlib import Path
import stat

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / 'materials/earnings-review'


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(path.parent.stat().st_mode | stat.S_IWUSR)
    if path.exists():
        path.chmod(path.stat().st_mode | stat.S_IWUSR)
    path.write_text(value)


def save(path, value):
    write(path, json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    metrics = ['revenue', 'operating_cost', 'operating_profit', 'parent_net_profit', 'basic_eps']
    nullable_string = {'type': ['string', 'null']}
    nullable_page = {'type': ['integer', 'null'], 'minimum': 1}
    row = {'type': 'object', 'additionalProperties': False,
           'required': ['metric', 'original_label', 'current', 'prior', 'unit', 'value_page', 'unit_page', 'unit_quote'],
           'properties': {'metric': {'enum': metrics}, 'original_label': nullable_string,
                          'current': nullable_string, 'prior': nullable_string,
                          'unit': {'enum': ['元', '千元', '万元', '亿元', '元/股', None]},
                          'value_page': nullable_page, 'unit_page': nullable_page, 'unit_quote': nullable_string}}
    schema = {'$schema': 'https://json-schema.org/draft/2020-12/schema', 'title': '原文候选，结构通过不等于财务核验通过',
              'type': 'object', 'additionalProperties': False,
              'required': ['company', 'scope', 'current_period', 'prior_period', 'current_column_path', 'prior_column_path', 'scope_evidence', 'current_column_evidence', 'prior_column_evidence', 'rows'],
              'properties': {'company': nullable_string, 'scope': {'enum': ['consolidated', 'unknown']},
                             'current_period': {'enum': ['2026H1', None]}, 'prior_period': {'enum': ['2025H1', None]},
                             'current_column_path': {'type': ['array', 'null'], 'items': {'type': 'string'}},
                             'prior_column_path': {'type': ['array', 'null'], 'items': {'type': 'string'}},
                             'rows': {'type': 'array', 'minItems': 5, 'maxItems': 5, 'items': row},
                             'scope_evidence': {'type': ['object', 'null'], 'properties': {'page': nullable_page, 'quote': nullable_string}, 'required': ['page', 'quote'], 'additionalProperties': False}}}
    citation = {'type': 'object', 'additionalProperties': False, 'required': ['page', 'quote'], 'properties': {'page': nullable_page, 'quote': nullable_string}}
    for period in ('current', 'prior'):
        schema['properties'][period + '_column_evidence'] = {'type': ['array', 'null'], 'items': citation}
    save(PROJECT / 'contracts/observation.schema.json', schema)
    policy = {'schema': 2, 'scope': {'report': '2026H1', 'compare': '2025H1', 'consolidation': 'consolidated', 'currency': 'CNY', 'metrics': metrics},
              'stages': ['prepare', 'locate', 'extract', 'vision', 'external', 'delivery'],
              'presets': {'qwen27': {'text_model': 'Qwen/Qwen3.8-27B', 'vision_model': 'Qwen/Qwen3.8-27B'},
                          'qwen9': {'text_model': 'Qwen/Qwen3.5-9B', 'vision_model': 'Qwen/Qwen3.8-27B'}},
              'endpoint': 'https://api.siliconflow.cn/v1',
              'sampling': {'enable_thinking': False, 'temperature': 0, 'top_p': 0.95, 'max_tokens': 8192, 'stream': False},
              'budget': {'max_requests': 12, 'reported_token_stop': 250000, 'admission_seconds': 900, 'max_feedback': 6, 'no_progress_stop': 2, 'repeated_failed_state_stop': 2, 'max_source_actions': 6, 'max_selected_pages': 12, 'max_read_pages': 24, 'max_whole_page_chars': 60000, 'transport_retries': 0, 'unknown_usage': 'stop'},
              'budget_semantics': 'Token/time thresholds decide admission of the next request; the last admitted response may exceed either threshold. All text/vision continuation calls share this ledger. Cache tokens are included in input.',
              'progress': 'Run-lifetime best rule sets and ever-passed flags survive candidate changes. First failure counts as no progress. Only a strict subset of lifetime best rules or first-ever gate pass resets the run-wide streak. Repeated source pass does not reset it. Retrieval is not progress.',
              'counters': ['gate_evaluations', 'failed_gate_evaluations', 'feedback_emitted', 'feedback_requests', 'source_actions', 'model_requests'],
              'feedback_semantics': 'max_feedback caps actual messages emitted. At the terminal second no-progress/repeated failure emit no further feedback. State keys exclude candidate/request IDs and hashes.',
              'source_binding': 'Longest complete numeric lexeme, exact displayed label with bounded ordinal/add/subtract prefixes, scope and per-component column citations. Distinguish note references structurally from negative numeric cells. Prove expected year, cumulative H1 including six months ended June30, consolidation and header source index before selecting row cells; preserve placeholders and reject ambiguity, never take first two numbers. One binder for text and vision. Source precision only. EPS aliases require a row-linked complete unit expression: only yuan/share, RMB yuan/share, or explicit RMB yuan for named basic EPS; consume both boundaries.',
              'freeze': 'Atomically copy allowlisted executable source, selected PDF, prompts, contracts and nonsecret config; execute a fresh child from frozen root; verify hashes before any model call; exclude secrets/symlinks/traversal/root runtime outputs; include prompts/runtime inputs.',
              'tools': {'search_fulltext': ['query', 'offset'], 'read_pages': ['pages'], 'select_pages': ['selection'], 'submit': ['observation']},
              'reference': {'command': 'financials.income', 'argv_command': ['financials', 'income'], 'period': 'quarterly', 'fiscal_period': 'Q2', 'years': [2026, 2025], 'period_end': 'June 30 in Asia/Shanghai reporting calendar; year matches fiscal_year', 'response_shape': 'CLI success envelope ok/command/data.item/meta; fiscal_year, fiscal_period, period_end_ms, currency and per-record thscode; no undocumented cumulative flag required', 'currency': 'CNY', 'unique_records_required': True, 'envelope_required': {'ok': True, 'command': 'financials.income', 'record_period': 'quarterly'},
                            'fields': dict(zip(metrics, ['operating_income', 'operating_costs', 'operating_profit', 'parent_holder_net_profit', 'basic_eps'])),
                            'precision': 'Round reference/currency factor to each original PDF numeric lexeme precision using Decimal ROUND_HALF_UP; compare canonical values, no relative tolerance.',
                            'max_attempts': 2, 'timeout_seconds': 120, 'role': 'external gold standard declared for this teaching exercise; values never sent to runtime models'},
              'states': ['queued', 'running', 'candidate_ready', 'stopped', 'interrupted'], 'human_review_required': True}
    policy['reply_parser'] = {'accepted': ['one complete JSON object', 'one complete json or unlabeled fence containing one object'],
                              'reject': ['surrounding prose', 'multiple objects/fences', 'arrays/scalars', 'truncation', 'wrong field types'],
                              'shared_by': ['locate', 'extract', 'vision'], 'invalid_reply': 'record raw reply and actual usage through the same dispatcher; stop after two consecutive invalid replies'}
    policy['joint_statement'] = 'A combined consolidated/company or parent-company title is permitted only when both H1 column paths explicitly select consolidated columns with source citations. Company-only, parent-only, ambiguous and single-quarter columns fail.'
    policy['source_binding'] += ' H1 requires positive June30 plus six-month/Jan-to-June context. Bind each row to its own closest complete local table header; no first-page or unrelated-table header borrowing. Missing/ambiguous local period/year/scope/index fails.'
    policy['source_binding'] += ' Match the complete H1 date boundary, not a June prefix. Own consolidated-only table title may prove scope; never default company/parent tables to consolidated using unrelated text. EPS citation must prove unscaled yuan per share, not a scaled amount exception sentence. An explicit note column may contain a bare parenthesized index; financial parenthesized negatives remain numeric cells.'
    policy['source_binding'] += ' EPS unit/currency/scale is a complete expression tied to its row: yuan-per-share must not match a suffix inside scaled or foreign-currency units. Preserve valid own-row unscaled EPS proof even when the surrounding quote also contains an amount-scale exception.'
    policy['source_binding'] += ' Extract the entire EPS-own unit expression with currency and scale boundaries, then full-match only yuan/share, RMB yuan/share, or explicit RMB yuan in the named basic-EPS row or its own caption. Normalize whitespace/brackets only; never delete unknown prefixes or accept a suffix after a finite blacklist. Keep amount-scale context separate from the EPS-own expression. The same positive grammar serves text and vision.'
    policy['source_binding'] += ' Both expression boundaries must be consumed: extract the entire own-row bracket or named EPS unit clause before positive full-match. Never stop capture at yuan/share or use unanchored RMB-yuan fallback; unknown right suffixes also fail.'
    policy['source_binding'] += ' Local means same-page table ownership, not a fixed lookback distance. Index title/period/year/scope/header blocks and their body intervals; ordinary body rows and sections do not expire a header. A new table title or column-header structure closes the previous interval even if invalid or incomplete. Never skip that barrier, inherit another page, or guess indices. A later valid local table may pass independently. Text and vision share this binder without new observation fields.'
    policy['source_binding'] += ' Each new column-header block owns its immediately associated period declarations, including header-only blocks. A previous title date is not an H1 default. Collect all explicit declarations; Q2/other-end/missing/conflicting H1-Q2 fails regardless of order. Invalid blocks occupy their own intervals. Repeated untitled H1 headers require their own complete H1 proof.'
    policy['review_projection'] = {'owner': 'one Decimal projection from source-bound raw values; final HALF_UP only', 'fields': ['metrics', 'gross_profit', 'gross_margin_percent', 'net_margin_percent', 'normalizations'], 'no_duplicate_amount_projections': ['summary', 'series'], 'metric_growth': 'yoy_percent string or null', 'expense_policy': {'metric': 'operating_cost', 'policy': 'expense_magnitude', 'exact_string_fields': ['current_signed_yuan', 'prior_signed_yuan', 'current_yuan', 'prior_yuan']}, 'browser': {'module': 'web/task-view.mjs', 'function': 'reviewCards', 'card_ids': ['revenue', 'parent_net_profit', 'gross_profit'], 'normal_page_uses_same_function': True, 'does_financial_calculations': False}}
    policy['source_binding'] += ' Detect every explicit financial title or standalone item-column heading before validating it, including zero/one-year headings. End the old owner first; retain rejected regions for incomplete/conflicting period/year/scope evidence. Never use successful year parsing as the boundary test or fall back past a rejected region. Ordinary item names/prose are not standalone column headings; later complete headers can recover.'
    policy['header_boundary'] = {'recognition_independent_of_completeness': True, 'invalid_region_owns_following_rows': True, 'fallback_past_rejected_region': False, 'ordinary_prose_is_not_column_heading': True, 'later_complete_header_can_recover': True, 'consolidated_only_title_may_prove_scope': True, 'repeated_scope_cells_are_not_conflicting_declarations': True, 'new_subject_interfaces': False}
    policy['source_binding'] += ' An explicit consolidated-only local title plus complete two-year columns may prove scope without a separate group row. Repeated equal scope cells are not contradictory declarations; ambiguity or conflicting declarations is invalid.'
    policy['source_binding'] += ' Title-to-header context is a complete same-page structural metadata chain, consumed by its explicit item heading; never truncate by line/character count or last-N evidence. A completed body clears pending context for a later heading without expiring the current owner. All local period declarations survive arbitrary consistent unit-caption continuation. Invalid owners still block fallback; consolidated-only title plus complete two-year header remains valid without a separate scope row.'
    policy['header_chain'] = {'complete_structural_metadata': True, 'fixed_distance_limit': False, 'consumed_by_explicit_header': True, 'old_body_blocks_stale_title_inheritance': True, 'ordinary_body_keeps_current_owner': True, 'all_period_declarations_retained': True, 'one_binder_for_text_vision_compare': True, 'new_subject_interfaces': False}
    policy['source_binding'] += ' Discover every explicit local period claim before target matching. Normalize the entire claim as target H1, explicit other, or unresolved; require nonempty evidence and every claim target H1. Another valid H1 cannot mask a different end date, duration, start or incomplete claim. Repeated equivalent H1 is valid; year-only cells/prose and unit captions are not claims. Header and column-path certification share these semantics; retain existing year-column binding and invalid-owner barriers. Never filter failed parses before all(), use any-H1/no-Q2, a blacklist, last-wins or a matching substring.'
    policy['period_certificate'] = {'discover_before_target_matching': True, 'explicit_claim_statuses': ['target_h1', 'explicit_other', 'unresolved'], 'require_nonempty_claims': True, 'every_claim_must_be_target_h1': True, 'discard_unparsed_claims': False, 'equivalent_duplicate_h1_is_valid': True, 'year_only_is_period_claim': False, 'shared_header_and_column_path_semantics': True, 'new_subject_interfaces': False}
    policy['period_certificate'].update({'single_closed_consumer_boundary': True, 'block_and_both_paths_use_same_certificate': True, 'bare_date_cannot_produce_target': True, 'consumed_bad_claim_cannot_be_rediscovered_as_target_substring': True, 'optional_year_does_not_supply_missing_duration': True})
    policy['period_certificate'].update({'every_declaration_span_covered_before_classification': True, 'fragment_can_contain_multiple_claims': True, 'good_claim_cannot_suppress_unresolved': True, 'duplicate_claim_records_preserved': True, 'uncovered_period_intent_blocks_acceptance': True})
    policy['period_certificate'].update({'allowed_complete_families': ['month_range', 'date_range', 'end_duration'], 'optional_year_same_discovery_grammar': True, 'sole_family_sufficient_for_each_owner': True, 'missing_year_is_not_missing_day_or_duration': True})
    policy['period_certificate'].update({'raw_title_and_metadata_share_discovery': True, 'first_title_prefix_shortcut': False})
    policy['model_role_routing'] = 'Actual stage enforces the frozen model in one client/dispatcher: locate/extract and text continuations use text_model, vision and vision continuations use vision_model. No default-text fallback for vision. Assert actual retained request.model under the mixed qwen9 preset through the same frozen worker.'
    policy['reference']['target_record_identity'] = 'Every target CLI data.item row requires its own nonempty string thscode exactly equal to expected_thscode. Missing/null/empty/wrong fail; a matching outer code cannot substitute. Normalized records may use their documented top-level code without weakening CLI checks.'
    policy['reference']['transport_check'] = 'Normal frozen worker uses ReferenceClient CLI subprocess; synthetic reference_cli path replaces executable only, no reference_endpoint, no alternate normalization or runner. Schema ID financials.income is not argv; actual argv command is financials income.'
    policy['reference']['selection'] = 'Preserve complete raw quarterly window, ignore non-target quarters, then validate exactly one target Q2 per year; wrong target identity/currency/window/date/fields and duplicate or missing targets fail.'
    policy['reference']['immutability'] = 'Freeze first successful raw reference per task or retain distinct immutable versions; recompute comparison for every changed candidate without overwriting earlier evidence.'
    policy['development'] = {'main_messages': 9, 'extra_messages': 0, 'private_observation_inputs': False,
                             'incremental_public_checks': [1,1,3,6,6,11,16,35,35], 'production_complete_by_step': 7,
                             'self_correction': 'Read public failures and repair within the original main message before returning.',
                             'test_scheduling': 'Public freeze/canary and all other freeze/local tests execute sequentially.',
                             'local_test_entry': 'python -m acceptance.local_checks; guard installed before discovery, project-local temp; tests/__init__ alone is insufficient'}
    policy['admission'] = 'Inside one creation lock: resolve same key, check active task, reserve identity, verify scanned and copied PDF hashes, freeze atomically, launch at most one real worker.'
    policy['journal'] = {'file': 'stage-journal.json', 'events': ['sequence', 'stage', 'kind', 'at', 'outcome on end'],
                          'invariant': 'Persist start before work, pair every entered interval on all terminal exits, keep repeated-stage intervals, derive fixed terminal durations from persisted records.'}
    policy['candidate_retention'] = 'trace.candidates contains sequence/candidate_id/path/sha256 for every parseable text submission before gates; independent files even for identical content; seal all candidates with unique ZIP members.'
    policy['usage_projection'] = 'Keep known subtotal visible beside pending and unknown. Once worker interruption is confirmed, every unfinished receipt becomes unknown, terminal pending is zero.'
    save(PROJECT / 'contracts/workflow.json', policy)
    save(PROJECT / 'contracts/development-checks.json', json.loads((ROOT / 'source/repair-coverage.json').read_text()))
    examples = {'label': 'Synthetic unit tests only; these are not any company financial values.',
                'unit_cases': [{'unit': '千元', 'raw': '100,000', 'canonical_yuan': '100000000', 'display_yi': '1.00'}, {'unit': '元/股', 'raw': '0.83', 'canonical': '0.83', 'display': '0.83'}, {'metric': 'operating_cost', 'unit': '万元', 'raw': '(600)', 'canonical_yuan_magnitude': '6000000', 'normalization_must_be_recorded': True}],
                'yoy_cases': [{'current': '110', 'prior': '100', 'yoy_percent': '10.00'}, {'current': '10', 'prior': '0', 'yoy_percent': None}, {'current': '-5', 'prior': '-10', 'yoy_percent': None}],
                'precision_cases': [{'pdf_original': '1.2', 'unit': '元', 'reference_yuan': '1.24', 'rounded_yuan': '1.2', 'match': True}, {'pdf_original': '1.2', 'unit': '元', 'reference_yuan': '1.25', 'rounded_yuan': '1.3', 'match': False}],
                'usage_cases': {'receipts': [{'id': '001', 'prompt_tokens': 100, 'completion_tokens': 10, 'total_tokens': 110, 'cached_tokens': 30}, {'id': '002', 'prompt_tokens': 200, 'completion_tokens': 20, 'total_tokens': 220, 'cached_tokens': 40}], 'expected_total_tokens': 330, 'cached_included_not_added': 70},
                'required_failure_cases': ['partial numeric token', 'wrong total row label', 'invented header', 'missing scope', 'Q2-only column', 'parent-only column', 'text action routed as candidate', 'visual disagreement returns to text', 'external disagreement returns to text', 'candidate change resets lifetime progress', 'mutable workspace imported by frozen worker', 'latest error hidden by best historical rule', 'default tests call identity service', 'missing unit quote', 'quote absent from cited physical page', 'EPS amount unit', 'wrong company', 'missing/ambiguous H1 reference record', 'old vision after text revision', 'reserved pending vs terminal unknown usage', 'repeated failed state', 'two no-progress failures', 'duplicate start creates one task', 'different selected company receives late old response']}
    save(PROJECT / 'contracts/check_examples.json', examples)
    lesson = json.loads((ROOT / 'source/lesson.json').read_text())
    task = '# 本地Earnings Review任务书\n\n' + lesson['lead'] + '\n\n## 做成什么样\n\n' + '\n'.join('- ' + s for s in lesson['success'])
    task += '\n\n## 共同约定\n\n' + lesson['fixed'] + '\n\n'
    task += 'reports是唯一真实财报输入。contracts是公开的结构、规则与合成检查。prompts/runtime是程序以后发送给财报模型的指令，不是现在让OpenCode立即执行的任务。程序代码由学习者自己的Agent分步创建。\n\n'
    task += '每个开发步骤结束时更新project_status.md。完整真实运行到第8步才由学习者手动点击开始，前面使用本地合成测试。缺少服务授权时如实停止，样例、合成测试与真实结果分别标记。\n\n'
    task += 'OpenCode开发对话的tokens由编码工具自身统计；网页账本只统计本轮财报程序实际发出的模型调用，包含文本和视觉续跑，不包含外部数据服务调用或这次编程对话。\n\n'
    task += '实现适配当前操作系统。不要依赖作者电脑的路径、凭据或已有运行。所有源PDF按哈希绑定。只有当前文字候选、独立视觉结果与外部比较全部一致，才封存并生成复盘，仍保留人工复核。\n\n'
    task += '程序处理器至少检查JSON结构、公司/合并口径/期间声明、原值与原单位、引用页已完整读取、逐字证据及原文邻近性。文字检查不单独证明语义正确。视觉应有合并标题及两期列头证据；数字10/10但其他约束失败时整体仍失败。\n\n'
    task += '收入/成本/营业利润/归母净利润展示亿元，EPS展示元/股。同比=(本期-上期)/上期*100，上期<=0时不适用。毛利润=营业收入-营业成本；毛利率=毛利润/营业收入*100；归母净利率=归母净利润/营业收入*100，收入<=0时相应比率不适用。若额外展示两期利润率差额，用百分点，不写同比百分比；本讲最小投影只要求本期利润率。全程Decimal，两位展示精度不能反过来做计算。\n\n'
    task += '定位selection包含status、pages、anchors、reason。anchors每项含page、原文quote和purpose，purpose为statement、continuation、amount_unit、eps_unit、header之一；最终引用只来自最终页包的完整已读文本。模型反馈只指出自己的失败与已有进度，禁止泄露外部参考值、差额或答案页。视觉失败续跑留在独立视觉会话，文字候选变化后开启全新视觉会话。\n\n'
    task += '同花顺CLI可用时先读取当前schema，完整原始响应落盘；请求仅公司证券代码、季度报告窗口和有界条数，唯一筛选2026/2025 Q2累计H1。缺失或非唯一不猜。当前已核验的命令形状是 hithink-finance financials income --thscode 所选真实代码 --period quarterly --limit 8 --output 本轮/reference/income.json --format json，实际参数以当前schema为准。\n\n'
    task += 'API Key不放在项目、网页、请求回执、聊天或命令参数。后台从用户级安全凭据或进程环境读取。前端不直接调用模型或金融数据服务。后台仅监听127.0.0.1，限制允许的证据路由并核对变更请求。\n'
    task += '\n本版默认编码配置为macOS、OpenCode＋DeepSeek、Build、deepseek/deepseek-flash、High推理档，输出上限沿用本机32000，不启用实验性输出覆盖。连接编码模型后直接从第0步开始，不额外发送测试对话。CLI的run方式使用 --model deepseek/deepseek-flash --variant high；交互界面按本机模型选项切到High。若High出现无进展、输出上限耗尽、以length结束或效果不足，保留该次结果，在全新空项目中用Max重跑（CLI使用 --variant max），不把两档结果合并为同一次。编码模型和财报运行模型不是同一个配置，财报默认仍是Qwen27B。其他配置需另记实跑。\n第5步现在先执行首个生产检查点，不先阅读验收测试或fixture。确认根目录后，最多两次读取必要的现有生产接口、observation.schema或本步runtime提示词片段，工具回传正文合计不超过6000字符；已在本对话中的约定不重复读取。随后立即把严格JSON回复解码与基本输入校验的最小可执行实现写入同一app/contracts.py、app/extract.py，并编译。这段必须真实识别合法对象、完整单围栏与非法传输，缺失的来源能力诚实失败，不能只写pass、TODO、未接入的helper或全为未实现的壳。首次业务写入前禁止读取acceptance测试体；首次写入和编译完成后立即运行through5公开检查。接着以首个真实失败为线索，每轮只读一个相关测试或fixture的局部定义，以80行和4000字符为参考目标；完整定义更长时只读当前失败所需的连续片段并记录实际范围；完成该段生产修正、编译和重测后再读下一段。先补输入/动作协议与完整数词，再补同一binder的表块、期间、列、单位绑定，最后接现有冻结TaskRunner来源循环。每段在当前消息内自动继续，不等新的指令。所有下文业务要求仍有效，最终完整through5全部11项及本地检查均须通过，不得改验收或以阶段性失败交付。\n完整检查日志保留在本项目runtime/step-N，不把全量日志展开到对话。执行python -m acceptance.checks --through N时只将stderr重定向到该步日志，stdout中的真实JSON结果原样回传，保留同一次检查的退出状态；失败再按用例名和行号读取首个相关片段。不要把真实结果截断、改写成自述，或用后一次命令输出冒充本次结果。本地检查也保存完整日志并回传实际结果。日志与测试输出仍全部可审查。\n'
    write(PROJECT / 'TASKBOOK.md', task)
    task += '\n## 公共验收与当前证明\n\n阅读acceptance/README.md，实现生产模块适配器。每步运行 python -m acceptance.checks --through 对应数字。第2步检查真实生产前端恢复模块，第3步有真实冻结worker，第5步接来源循环及结构化行绑定，第6步有完整封存成功链，第7步原30项及新增5项共35项生产验收，第8步网页回归和启动。默认测试不联网，公共断言不改动。程序动作先分派再提交，视觉/外部分歧可回原文字会话；仅当前同一候选的两层证据有效才封存。终身进度与当前有效性分开。任务实际执行复制的源码，不能只记录摘要。\n'
    task += '\n## 九条主线与公开反例\n\n按0–8九条主Prompt完成。每条消息内根据公开验收失败自行修改生产代码并重测，不要求学习者另发修复、恢复或观察消息。只使用本项目材料，不读其它项目、历史应用或讲义外观察文件。contracts/development-checks.json逐项映射此前暴露的问题、所属主步骤和可执行公开检查。\n'
    task += '\n第2步先跑 --through 2；所有0–8数字均可用。公共冻结/canary、合成任务和本地单测串行，不能同时改工作区并冻结。原始回复解析、联合标题、混合季度、真实并发/状态/历史、全部候选封存、单位与DOM都有公开检查；不允许仅用自写测试替代。\n'
    task += '\napp.acceptance.serve(scenario, output_root)是唯一新增服务测试入口，使用正常启动也用的真实server工厂、TaskManager和冻结worker，仅注入已确认的合成身份与回环传输。它不能另造状态、计算或编排。网页状态从持久ledger、proof和stage-journal投影。第8步给出服务后，学习者点击即可让固定程序自行完成，不需要第二条观察指令。\n'
    task += '\n路径约束：每步先从工具输出确认当前项目根目录。支持相对路径的命令和文件工具使用项目相对路径；要求绝对路径的写入工具，必须从刚确认的根目录原文生成，禁止重打、猜写目录名或日期。写入前确认父目录实际存在且属于本项目；无法确保时改用当前目录下的相对路径写入命令，不试探项目外写入。\n'
    task += '\n默认本地检查统一用 python -m acceptance.local_checks，在发现/导入前安装公开守卫，并把临时目录设在本项目。先建tests/__init__.py，不能只依赖它的副作用再用裸unittest discover。每步日志、诊断、试渲染都留在runtime/step-N或tests/output，不请求系统临时目录权限。该入口与acceptance.checks串行。\n'
    task += '\n来源绑定按真实显示行名、附注位置、完整数词及已证明表头列索引进行；半年累计允许原文六个月止六月三十日表达，仍须绑定各自年份和合并列，不能借公司列、附注或单季。文字/视觉共用一个绑定器。刷新及重选报告通过正常网页使用的task-view.mjs恢复同一持久任务，按报告id+PDF哈希匹配、显示冻结模型，恢复只有GET，错误不冒充空记录。公开检查对这些问题使用纯合成正反例，并通过正常CLI子进程分支验证financials income两段命令；只有显式合成配置可注入reference_cli假可执行路径。\n'
    write(PROJECT / 'TASKBOOK.md', task)
    acceptance_hashes = {}
    for source in sorted((ROOT / 'source/acceptance').rglob('*')):
        if source.is_file() and '__pycache__' not in source.parts and source.suffix in ('.py', '.md'):
            target = PROJECT / 'acceptance' / source.relative_to(ROOT / 'source/acceptance')
            write(target, source.read_text())
            acceptance_hashes[str(target.relative_to(PROJECT))] = hashlib.sha256(target.read_bytes()).hexdigest()
    inputs = json.loads((PROJECT / 'reports/SOURCES.json').read_text())
    provenance = {'created_date': '2026-10-18', 'purpose': 'answer-free build materials', 'pdfs': inputs, 'runtime_prompt_hashes': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((PROJECT / 'prompts/runtime').glob('*.md'))}, 'contains_application_code': False, 'contains_synthetic_acceptance_code': True, 'acceptance_hashes': acceptance_hashes, 'contains_precomputed_financial_answer_key_or_selected_pages': False}
    save(PROJECT / 'MATERIALS.json', provenance)
    print('Prepared contracts and learner taskbook without finished app or financial answers.')


if __name__ == '__main__':
    main()
