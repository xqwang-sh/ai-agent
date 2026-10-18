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
              'source_binding': 'Longest complete numeric lexeme, exact row alias, scope and per-component column citations. Source precision only. EPS label per-share plus yuan is a permitted explicit alias.',
              'freeze': 'Atomically copy allowlisted executable source, selected PDF, prompts, contracts and nonsecret config; execute a fresh child from frozen root; verify hashes before any model call; exclude secrets/symlinks/traversal/root runtime outputs; include prompts/runtime inputs.',
              'tools': {'search_fulltext': ['query', 'offset'], 'read_pages': ['pages'], 'select_pages': ['selection'], 'submit': ['observation']},
              'reference': {'command': 'financials.income', 'period': 'quarterly', 'fiscal_period': 'Q2', 'years': [2026, 2025], 'period_end': 'June 30 in Asia/Shanghai reporting calendar; year matches fiscal_year', 'response_shape': 'CLI success envelope ok/command/data.item/meta; fiscal_year, fiscal_period, period_end_ms, currency and per-record thscode; no undocumented cumulative flag required', 'currency': 'CNY', 'unique_records_required': True, 'envelope_required': {'ok': True, 'command': 'financials.income', 'record_period': 'quarterly'},
                            'fields': dict(zip(metrics, ['operating_income', 'operating_costs', 'operating_profit', 'parent_holder_net_profit', 'basic_eps'])),
                            'precision': 'Round reference/currency factor to each original PDF numeric lexeme precision using Decimal ROUND_HALF_UP; compare canonical values, no relative tolerance.',
                            'max_attempts': 2, 'timeout_seconds': 120, 'role': 'external gold standard declared for this teaching exercise; values never sent to runtime models'},
              'states': ['queued', 'running', 'candidate_ready', 'stopped', 'interrupted'], 'human_review_required': True}
    save(PROJECT / 'contracts/workflow.json', policy)
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
    task += '收入/成本/营业利润/归母净利润展示亿元，EPS展示元/股。同比=(本期-上期)/上期*100，上期<=0时不适用。毛利润=营业收入-营业成本；毛利率=毛利润/营业收入*100；归母净利率=归母净利润/营业收入*100，收入<=0时相应比率不适用。利润率两期差额用百分点，不写同比百分比。全程Decimal，两位展示精度不能反过来做计算。\n\n'
    task += '定位selection包含status、pages、anchors、reason。anchors每项含page、原文quote和purpose，purpose为statement、continuation、amount_unit、eps_unit、header之一；最终引用只来自最终页包的完整已读文本。模型反馈只指出自己的失败与已有进度，禁止泄露外部参考值、差额或答案页。视觉失败续跑留在独立视觉会话，文字候选变化后开启全新视觉会话。\n\n'
    task += '同花顺CLI可用时先读取当前schema，完整原始响应落盘；请求仅公司证券代码、季度报告窗口和有界条数，唯一筛选2026/2025 Q2累计H1。缺失或非唯一不猜。当前已核验的命令形状是 hithink-finance financials income --thscode 所选真实代码 --period quarterly --limit 8 --output 本轮/reference/income.json --format json，实际参数以当前schema为准。\n\n'
    task += 'API Key不放在项目、网页、请求回执、聊天或命令参数。后台从用户级安全凭据或进程环境读取。前端不直接调用模型或金融数据服务。后台仅监听127.0.0.1，限制允许的证据路由并核对变更请求。\n'
    write(PROJECT / 'TASKBOOK.md', task)
    task += '\n## 公共验收与当前证明\n\n阅读acceptance/README.md，实现生产模块适配器。第5/6/7/8步运行 python -m acceptance.checks --through 对应数字。默认测试不联网，公共断言不改动。程序动作先分派再提交，视觉/外部分歧可回原文字会话；仅当前同一候选的两层证据有效才封存。终身进度与当前有效性分开。任务实际执行复制的源码，不能只记录摘要。\n'
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
