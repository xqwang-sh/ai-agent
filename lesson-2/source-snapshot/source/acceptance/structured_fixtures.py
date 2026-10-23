"""Answer-free source-binding fixtures with realistic table structure."""
from copy import deepcopy
from decimal import Decimal


STRUCTURED_COMPANY = '结构测试股份有限公司'
STRUCTURED_THSCODE = '000001.SZ'

_ROWS = {
    'revenue': {
        'label': '一、营业收入',
        'consolidated': {'2026': '310', '2025': '280'},
        'company': {'2026': '31', '2025': '28'},
        'note': '三(8)',
    },
    'operating_cost': {
        'label': '减：营业成本',
        'consolidated': {'2026': '(190)', '2025': '(170)'},
        'company': {'2026': '(19)', '2025': '(17)'},
        'note': '三(8)',
    },
    'operating_profit': {
        'label': '二、营业利润',
        'consolidated': {'2026': '70', '2025': '60'},
        'company': {'2026': '7', '2025': '6'},
        'note': '',
    },
    'parent_net_profit': {
        'label': '归属于母公司股东的净利润',
        'consolidated': {'2026': '45', '2025': '40'},
        'company': {'2026': '不适用', '2025': '不适用'},
        'note': '',
    },
    'basic_eps': {
        'label': '基本每股收益(人民币元)',
        'consolidated': {'2026': '1.25', '2025': '1.10'},
        'company': {'2026': '0.25', '2025': '0.20'},
        'note': '三(19)',
    },
}

_DISTRACTORS = {
    'total_revenue': {'label': '营业总收入', '2026': '350', '2025': '320'},
    'total_cost': {'label': '营业总成本', '2026': '(250)', '2025': '(230)'},
    'diluted_eps': {'label': '稀释每股收益(人民币元)', '2026': '1.20', '2025': '1.05'},
}


def _columns(order):
    if order == 'consolidated_first':
        return [('2026', '合并'), ('2025', '合并'), ('2026', '公司'), ('2025', '公司')]
    if order == 'company_first':
        return [('2026', '公司'), ('2025', '公司'), ('2026', '合并'), ('2025', '合并')]
    if order == 'reversed_years':
        return [('2025', '合并'), ('2026', '合并'), ('2025', '公司'), ('2026', '公司')]
    raise ValueError(f'unknown structured column order: {order!r}')


def _cells(row, columns):
    groups = {'合并': 'consolidated', '公司': 'company'}
    return [row[groups[scope]][year] for year, scope in columns]


def _continuation_columns(order):
    if order == 'company_first':
        return _columns('reversed_years')
    return _columns('company_first')


def structured_source_case(order='consolidated_first'):
    """Return selected full-page text and its consolidated H1 observation."""
    columns = _columns(order)
    continuation_columns = _continuation_columns(order)
    title = '截至 2026 年 6 月 30 日止六个月期间合并及公司利润表'
    period = '截至 6 月 30 日止六个月期间'
    lines = [
        STRUCTURED_COMPANY,
        title,
        '（除基本每股收益外，金额单位为人民币万元）',
        period,
        '项目 附注 ' + ' '.join(year + '年' for year, _ in columns),
        ' '.join(scope for _, scope in columns),
    ]
    for metric in ('revenue', 'operating_cost', 'operating_profit',
                   'parent_net_profit'):
        row = _ROWS[metric]
        prefix = row['label'] + ((' ' + row['note']) if row['note'] else '')
        lines.append(prefix + ' ' + ' '.join(_cells(row, columns)))
    lines.extend([
        '营业总收入 350 320 35 32',
        '营业总成本 (250) (230) (25) (23)',
    ])
    continuation_title = title + '(续)'
    continuation = [
        STRUCTURED_COMPANY,
        continuation_title,
        '（除基本每股收益外，金额单位为人民币万元）',
        period,
        '项目 附注 ' + ' '.join(year + '年' for year, _ in continuation_columns),
        ' '.join(scope for _, scope in continuation_columns),
        (_ROWS['basic_eps']['label'] + ' ' + _ROWS['basic_eps']['note'] + ' '
         + ' '.join(_cells(_ROWS['basic_eps'], continuation_columns))),
        '稀释每股收益(人民币元) 三(19) 0.24 0.19 1.20 1.05',
    ]
    pages = [
        {'physical_page': 1, 'text': '\n'.join(lines)},
        {'physical_page': 2, 'text': '\n'.join(continuation)},
    ]
    observation = {
        'company': STRUCTURED_COMPANY,
        'scope': 'consolidated',
        'current_period': '2026H1',
        'prior_period': '2025H1',
        'scope_evidence': {'page': 1, 'quote': title},
        'current_column_path': [period, '2026年', '合并'],
        'prior_column_path': [period, '2025年', '合并'],
        'current_column_evidence': [
            {'page': 1, 'quote': period},
            {'page': 1, 'quote': '2026年'},
            {'page': 1, 'quote': '合并'},
            {'page': 2, 'quote': period},
            {'page': 2, 'quote': '2026年'},
            {'page': 2, 'quote': '合并'},
        ],
        'prior_column_evidence': [
            {'page': 1, 'quote': period},
            {'page': 1, 'quote': '2025年'},
            {'page': 1, 'quote': '合并'},
            {'page': 2, 'quote': period},
            {'page': 2, 'quote': '2025年'},
            {'page': 2, 'quote': '合并'},
        ],
        'rows': [],
    }
    for metric in ('revenue', 'operating_cost', 'operating_profit',
                   'parent_net_profit', 'basic_eps'):
        row = _ROWS[metric]
        observation['rows'].append({
            'metric': metric,
            'original_label': row['label'],
            'current': row['consolidated']['2026'],
            'prior': row['consolidated']['2025'],
            'unit': '元/股' if metric == 'basic_eps' else '万元',
            'value_page': 2 if metric == 'basic_eps' else 1,
            'unit_page': 2 if metric == 'basic_eps' else 1,
            'unit_quote': ('基本每股收益(人民币元)' if metric == 'basic_eps'
                           else '（除基本每股收益外，金额单位为人民币万元）'),
        })
    return pages, observation



def structured_long_source_case(filler_count=16, order='consolidated_first'):
    """Length/section variants; use 18 fillers for the normal-sized PDF proof."""
    pages, value = structured_source_case(order)
    ordinary = [f'普通明细{index + 1:02d} 2 1 2 1'
                for index in range(filler_count)]
    lines = pages[0]['text'].splitlines()
    profit = next(index for index, line in enumerate(lines)
                  if line.startswith(_ROWS['operating_profit']['label']))
    lines[profit:profit] = ordinary
    parent = next(index for index, line in enumerate(lines)
                  if line.startswith(_ROWS['parent_net_profit']['label']))
    lines[parent:parent] = [f'归属明细{index + 1:02d} 2 1 2 1'
                           for index in range(6)] + [
                               '按经营持续性分类：', '按所有权归属分类：']
    pages[0]['text'] = '\n'.join(lines)
    lines = pages[1]['text'].splitlines()
    eps = next(index for index, line in enumerate(lines)
               if line.startswith(_ROWS['basic_eps']['label']))
    lines[eps:eps] = ordinary + ['七、每股收益']
    pages[1]['text'] = '\n'.join(lines)
    return pages, value


def structured_table_boundary_case(kind):
    """Fictional same-page ownership and page-boundary controls."""
    pages, value = structured_source_case()
    title = value['scope_evidence']['quote']
    period = value['current_column_path'][0]
    unit = '（除基本每股收益外，金额单位为人民币万元）'
    if kind == 'valid_after_invalid':
        pages, value = structured_source_case('company_first')
        decoy = [STRUCTURED_COMPANY, '2026年4-6月单季公司利润表', unit,
                 '4-6月单季', '项目 附注 2026年 2025年', '公司 公司',
                 '无关明细 3 2']
        pages[0]['text'] = '\n'.join(decoy) + '\n' + pages[0]['text']
        return pages, value
    if kind == 'page2_headerless':
        lines = pages[1]['text'].splitlines()
        lines = lines[:4] + lines[6:]
        lines[4] = (_ROWS['basic_eps']['label'] + ' ' + _ROWS['basic_eps']['note']
                    + ' ' + ' '.join(_cells(_ROWS['basic_eps'], _columns('consolidated_first'))))
        lines[5] = '稀释每股收益(人民币元) 三(19) 1.20 1.05 0.24 0.19'
        pages[1]['text'] = '\n'.join(lines)
        for side in ('current', 'prior'):
            value[side + '_column_evidence'] = [
                item for item in value[side + '_column_evidence'] if item['page'] == 1]
        return pages, value
    kinds = {'second_h1', 'second_q2', 'second_company',
             'second_headerless', 'header_only_company'}
    if kind not in kinds:
        raise ValueError(f'unknown table-boundary case: {kind!r}')
    next_title = title.replace('合并及公司利润表', '第二张合并及公司利润表')
    next_period = period
    columns = _columns('company_first') if kind == 'second_h1' else _columns('consolidated_first')
    scopes = [scope for _, scope in columns]
    if kind == 'second_q2':
        next_title = '2026年4-6月单季合并及公司利润表'
        next_period = '4-6月单季'
    if kind in ('second_company', 'header_only_company'):
        next_title = title.replace('合并及公司利润表', '公司及母公司利润表')
        scopes = ['公司', '公司', '母公司', '母公司']
    block = [] if kind == 'header_only_company' else [next_title]
    block.extend([unit, next_period])
    if kind != 'second_headerless':
        block.extend(['项目 附注 ' + ' '.join(year + '年' for year, _ in columns),
                      ' '.join(scopes)])
    lines = pages[0]['text'].splitlines()
    start = next(index for index, line in enumerate(lines)
                 if line.startswith(_ROWS['operating_profit']['label']))
    if kind == 'second_h1':
        for metric in ('operating_profit', 'parent_net_profit'):
            index = next(i for i, line in enumerate(lines)
                         if line.startswith(_ROWS[metric]['label']))
            lines[index] = _ROWS[metric]['label'] + ' ' + ' '.join(_cells(_ROWS[metric], columns))
    lines[start:start] = block
    pages[0]['text'] = '\n'.join(lines)
    return pages, value



def structured_header_period_case(kind):
    """An untitled new header must prove its own period, in its own columns."""
    pages, value = structured_source_case()
    period = value['current_column_path'][0]
    declarations = {
        'h1': [period],
        'q2': ['截至 6 月 30 日止三个月期间'],
        'h1_q2': [period, '截至 6 月 30 日止三个月期间'],
        'q2_h1': ['截至 6 月 30 日止三个月期间', period],
        'missing': [],
    }
    if kind not in declarations:
        raise ValueError(f'unknown header-period case: {kind!r}')
    columns = _columns('company_first')
    block = declarations[kind] + [
        '项目 附注 ' + ' '.join(year + '年' for year, _ in columns),
        ' '.join(scope for _, scope in columns),
    ]
    lines = pages[0]['text'].splitlines()
    for metric in ('operating_profit', 'parent_net_profit'):
        index = next(i for i, line in enumerate(lines)
                     if line.startswith(_ROWS[metric]['label']))
        lines[index] = (_ROWS[metric]['label'] + ' '
                        + ' '.join(_cells(_ROWS[metric], columns)))
    index = next(i for i, line in enumerate(lines)
                 if line.startswith(_ROWS['operating_profit']['label']))
    lines[index:index] = block
    pages[0]['text'] = '\n'.join(lines)
    return pages, value



def structured_incomplete_header_case(kind):
    """Explicit header barriers keep the unchanged four-cell body they own."""
    pages, value = structured_source_case()
    period = value['current_column_path'][0]
    quarter = '截至 6 月 30 日止三个月期间'
    full = '项目 附注 2026年 2025年 2026年 2025年'
    scopes = '合并 合并 公司 公司'
    reversed_scopes = '公司 公司 合并 合并'
    blocks = {
        'complete_h1': [period, full, scopes],
        'ordinary_prose': ['项目开发成本 2 1 2 1', '普通项目附注说明含2026年'],
        'zero_year': [period, '项目 附注', scopes],
        'one_year': [period, '项目 附注 2026年', scopes],
        'missing_scope': [period, full],
        'scope_count_mismatch': [period, full, '合并 公司 公司'],
        'scope_conflict': [period, full, scopes, reversed_scopes],
        'scope_conflict_reverse': [period, full, reversed_scopes, scopes],
        'zero_year_q2': [quarter, '项目 附注', scopes],
        'one_year_q2': [quarter, '项目 附注 2026年', scopes],
        'complete_after_zero': [period, '项目 附注', scopes, period, full, scopes],
        'complete_after_one': [period, '项目 附注 2026年', scopes, period, full, scopes],
    }
    if kind not in blocks:
        raise ValueError(f'unknown incomplete-header case: {kind!r}')
    lines = pages[0]['text'].splitlines()
    index = next(i for i, line in enumerate(lines)
                 if line.startswith(_ROWS['operating_profit']['label']))
    lines[index:index] = blocks[kind]
    pages[0]['text'] = '\n'.join(lines)
    return pages, value



def structured_long_header_case(metadata_lines=16, order='consolidated_first',
                                kind='complete_h1'):
    """Continuous existing unit captions vary length without financial cells."""
    caption = '（除基本每股收益外，金额单位为人民币万元）'
    if metadata_lines < 1:
        raise ValueError('metadata_lines must be positive')
    captions = [caption] * metadata_lines
    if kind in ('one_year', 'scope_conflict', 'scope_conflict_reverse'):
        pages, value = structured_incomplete_header_case(kind)
        lines = pages[0]['text'].splitlines()
        headers = [i for i, line in enumerate(lines) if line.startswith('项目 ')]
        lines[headers[1]:headers[1]] = captions
        pages[0]['text'] = '\n'.join(lines)
        return pages, value
    pages, value = structured_source_case(order)
    if kind in ('h1_q2', 'q2_h1'):
        lines = pages[0]['text'].splitlines()
        period = value['current_column_path'][0]
        quarter = '截至 6 月 30 日止三个月期间'
        first, last = (period, quarter) if kind == 'h1_q2' else (quarter, period)
        lines[lines.index(period)] = first
        index = next(i for i, line in enumerate(lines) if line.startswith('项目 '))
        lines[index:index] = captions + [last]
        pages[0]['text'] = '\n'.join(lines)
        return pages, value
    if kind not in ('complete_h1', 'consolidated_only'):
        raise ValueError(f'unknown long-header case: {kind!r}')
    if kind == 'consolidated_only':
        pages[1]['text'] = '\n'.join([
            STRUCTURED_COMPANY,
            '截至 2026 年 6 月 30 日止六个月期间合并利润表(续)',
            caption,
            value['current_column_path'][0],
            '项目 2026年 2025年',
            '基本每股收益(人民币元) 1.25 1.10',
            '稀释每股收益(人民币元) 1.20 1.05',
        ])
    for page in pages:
        lines = page['text'].splitlines()
        index = next(i for i, line in enumerate(lines) if line.startswith('项目 '))
        lines[index:index] = captions
        page['text'] = '\n'.join(lines)
    return pages, value



def structured_period_consistency_case(kind, metadata_lines=16, order='h1_first'):
    """Every explicit local period survives the same long unit-caption chain."""
    pages, value = structured_long_header_case(metadata_lines)
    period = value['current_column_path'][0]
    declarations = {
        'May31': '截至 5 月 31 日止六个月期间',
        'Jun15': '截至 6 月 15 日止六个月期间',
        'five_months': '截至 6 月 30 日止五个月期间',
        'Feb1_start': '2026年2月1日至6月30日',
        'missing_day': '截至 6 月止六个月期间',
        'missing_duration_June30': '截至 6 月 30 日止期间',
        'repeat_same_H1': period,
        'equivalent_Jan1_Jun30': '2026年1月1日至6月30日',
    }
    if kind not in declarations:
        raise ValueError(f'unknown period-consistency case: {kind!r}')
    if order not in ('h1_first', 'other_first'):
        raise ValueError(f'unknown period declaration order: {order!r}')
    other = declarations[kind]
    first, last = (period, other) if order == 'h1_first' else (other, period)
    lines = pages[0]['text'].splitlines()
    start = lines.index(period)
    stop = next(i for i, line in enumerate(lines) if line.startswith('项目 '))
    caption = '（除基本每股收益外，金额单位为人民币万元）'
    lines[start:stop] = [first] + [caption] * metadata_lines + [last]
    pages[0]['text'] = '\n'.join(lines)
    return pages, value


def structured_year_period_case(kind, metadata_lines=16, order='h1_first'):
    """A year prefix cannot supply the missing duration of a whole declaration."""
    kinds = {'complete_H1': 'repeat_same_H1',
             'missing_duration': 'missing_duration_June30'}
    if kind not in kinds:
        raise ValueError(f'unknown year-period case: {kind!r}')
    pages, value = structured_period_consistency_case(kinds[kind], metadata_lines, order)
    lines = pages[0]['text'].splitlines()
    header = next(i for i, line in enumerate(lines) if line.startswith('项目 '))
    index = header - 1 if order == 'h1_first' else header - metadata_lines - 2
    lines[index] = ('截至 2026 年 6 月 30 日止六个月期间' if kind == 'complete_H1'
                    else '截至 2026 年 6 月 30 日止期间')
    pages[0]['text'] = '\n'.join(lines)
    return pages, value


def structured_column_path_period_case(kind, side='current', order='h1_first'):
    """An extra cited path declaration must agree with the complete local H1."""
    if side not in ('current', 'prior'):
        raise ValueError(f'unknown period side: {side!r}')
    if order not in ('h1_first', 'other_first'):
        raise ValueError(f'unknown path declaration order: {order!r}')
    year = '2026' if side == 'current' else '2025'
    declarations = {
        'complete_H1': f'{year}年1月1日至6月30日',
        'other_duration': f'截至{year}年6月30日止五个月期间',
        'missing_duration': f'截至{year}年6月30日止期间',
    }
    if kind not in declarations:
        raise ValueError(f'unknown column-path period case: {kind!r}')
    pages, value = structured_source_case()
    declaration = declarations[kind]
    pages[0]['text'] += '\n期间原文补充：' + declaration
    evidence = {'page': 1, 'quote': declaration}
    if order == 'h1_first':
        value[side + '_column_path'].append(declaration)
        value[side + '_column_evidence'].append(evidence)
    else:
        value[side + '_column_path'].insert(0, declaration)
        value[side + '_column_evidence'].insert(0, evidence)
    return pages, value


def structured_fragment_period_case(kind, order='h1_first', *, metadata_lines=None, side=None):
    """One cited fragment may contain two independently meaningful declarations."""
    if kind not in ('complete_H1', 'missing_duration'):
        raise ValueError(f'unknown fragment-period case: {kind!r}')
    if order not in ('h1_first', 'other_first'):
        raise ValueError(f'unknown fragment declaration order: {order!r}')
    if (metadata_lines is None) == (side is None):
        raise ValueError('choose either a local metadata chain or one column-path side')
    if metadata_lines is not None:
        pages, value = structured_year_period_case('complete_H1', metadata_lines, 'h1_first')
        year = '2026'
    else:
        pages, value = structured_column_path_period_case('complete_H1', side, 'h1_first')
        year = '2026' if side == 'current' else '2025'
    complete = f'{year}年1月1日至6月30日'
    other = (f'截至{year}年6月30日止六个月期间' if kind == 'complete_H1'
             else f'截至{year}年6月30日止期间')
    fragment = '；'.join((complete, other) if order == 'h1_first' else (other, complete))
    if metadata_lines is not None:
        lines = pages[0]['text'].splitlines()
        header = next(i for i, line in enumerate(lines) if line.startswith('项目 '))
        lines[header - 1] = fragment
        pages[0]['text'] = '\n'.join(lines)
    else:
        footer = '\n期间原文补充：'
        pages[0]['text'] = pages[0]['text'].rsplit(footer, 1)[0] + footer + fragment
        value[side + '_column_path'][-1] = fragment
        value[side + '_column_evidence'][-1]['quote'] = fragment
    return pages, value



def structured_title_period_case(kind, order='h1_first'):
    """Move an existing compound period into the original first-page title only."""
    _, fragment_value = structured_fragment_period_case(kind, order, side='current')
    fragment = fragment_value['current_column_path'][-1]
    pages, value = structured_source_case()
    old_title = value['scope_evidence']['quote']
    title = fragment + '合并及公司利润表'
    pages[0]['text'] = pages[0]['text'].replace(old_title, title, 1)
    value['scope_evidence']['quote'] = title
    return pages, value


def structured_sole_period_case(form, with_year):
    """Every local/path period uses one allowed family, with no other H1 backup."""
    if form not in ('month_range', 'date_range', 'end_duration'):
        raise ValueError(f'unknown sole period form: {form!r}')
    if type(with_year) is not bool:
        raise ValueError('with_year must be boolean')

    def expression(year):
        prefix = year + '年' if with_year else ''
        if form == 'month_range':
            return prefix + '1–6月'
        if form == 'date_range':
            return prefix + '1月1日至6月30日'
        return '截至' + prefix + '6月30日止六个月期间'

    pages, value = structured_source_case()
    old_title = value['scope_evidence']['quote']
    old_period = value['current_column_path'][0]
    current_period = expression('2026')
    prior_period = expression('2025')
    title = current_period + '合并及公司利润表'
    metadata = current_period + '；' + prior_period if with_year else current_period
    for page in pages:
        page['text'] = page['text'].replace(old_title, title).replace(old_period, metadata)
    value['scope_evidence']['quote'] = title
    for side, period in (('current', current_period), ('prior', prior_period)):
        value[side + '_column_path'][0] = period
        for evidence in value[side + '_column_evidence']:
            if evidence['quote'] == old_period:
                evidence['quote'] = period
            elif evidence['quote'] == old_title:
                evidence['quote'] = title
    return pages, value


def structured_review_case():
    """One visible long PDF with local H1 header and fictional rounding traps."""
    pages, value = structured_long_source_case(18)
    lines = pages[0]['text'].splitlines()
    changes = {'revenue': '149', 'operating_cost': '(51)'}
    for metric, literal in changes.items():
        row = deepcopy(_ROWS[metric])
        row['consolidated']['2026'] = literal
        index = next(i for i, line in enumerate(lines)
                     if line.startswith(row['label']))
        prefix = row['label'] + ((' ' + row['note']) if row['note'] else '')
        lines[index] = prefix + ' ' + ' '.join(_cells(row, _columns('consolidated_first')))
        next(item for item in value['rows'] if item['metric'] == metric)['current'] = literal
    replacement = [value['current_column_path'][0],
                   '项目 附注 2026年 2025年 2026年 2025年',
                   '合并 合并 公司 公司']
    for number, line in enumerate(replacement, 1):
        index = lines.index(f'普通明细{number:02d} 2 1 2 1')
        lines[index] = line
    pages[0]['text'] = '\n'.join(lines)
    lines = pages[1]['text'].splitlines()
    for number in range(1, 17):
        lines.remove(f'普通明细{number:02d} 2 1 2 1')
    header = next(i for i, line in enumerate(lines) if line.startswith('项目 '))
    lines[header:header] = ['（除基本每股收益外，金额单位为人民币万元）'] * 16
    pages[1]['text'] = '\n'.join(lines)
    return pages, value


def structured_selection():
    return {
        'status': 'located',
        'pages': [1, 2],
        'anchors': [
            {'page': 1, 'quote': '合并及公司利润表', 'purpose': 'statement'},
            {'page': 2, 'quote': '合并及公司利润表(续)', 'purpose': 'continuation'},
        ],
        'reason': '合成联合报表含累计期间、列组、金额单位与每股单位',
    }


def structured_reference(observation=None):
    fields = {
        'revenue': 'operating_income',
        'operating_cost': 'operating_costs',
        'operating_profit': 'operating_profit',
        'parent_net_profit': 'parent_holder_net_profit',
        'basic_eps': 'basic_eps',
    }
    records = []
    for year in ('2026', '2025'):
        record = {
            'year': int(year),
            'fiscal_period': 'Q2',
            'period_end': year + '-06-30',
            'currency': 'CNY',
            'cumulative': True,
        }
        for metric, field in fields.items():
            raw = (next(row for row in observation['rows'] if row['metric'] == metric)
                   ['current' if year == '2026' else 'prior'] if observation is not None
                   else _ROWS[metric]['consolidated'][year])
            value = Decimal(raw.strip('()'))
            record[field] = str(value if metric == 'basic_eps' else value * 10000)
        records.append(record)
    return {'synthetic': True, 'thscode': STRUCTURED_THSCODE, 'records': records}


def structured_company_value_candidate(order='consolidated_first'):
    _, value = structured_source_case(order)
    revenue = next(row for row in value['rows'] if row['metric'] == 'revenue')
    revenue['current'] = _ROWS['revenue']['company']['2026']
    revenue['prior'] = _ROWS['revenue']['company']['2025']
    return value


def structured_wrong_year_candidate(order='consolidated_first'):
    _, value = structured_source_case(order)
    value['current_column_path'], value['prior_column_path'] = (
        value['prior_column_path'], value['current_column_path'])
    value['current_column_evidence'], value['prior_column_evidence'] = (
        value['prior_column_evidence'], value['current_column_evidence'])
    for row in value['rows']:
        row['current'], row['prior'] = row['prior'], row['current']
    return value


def structured_continuation_wrong_indices_candidate(order='consolidated_first'):
    _, value = structured_source_case(order)
    eps = next(row for row in value['rows'] if row['metric'] == 'basic_eps')
    eps['current'] = _ROWS['basic_eps']['company']['2026']
    eps['prior'] = _ROWS['basic_eps']['company']['2025']
    return value


def structured_scenario(pdf_path, observation=None):
    _, value = structured_source_case()
    if observation is not None:
        value = deepcopy(observation)
    model_script = [
        {'stage': 'locate', 'response': {'action': 'select_pages',
                                         'selection': structured_selection()}},
        {'stage': 'extract', 'response': {'action': 'submit',
                                          'observation': deepcopy(value)}},
        {'stage': 'vision', 'response': deepcopy(value)},
    ]
    for index, item in enumerate(model_script, 1):
        item.update(id=f'structured-{index}',
                    usage={'prompt_tokens': 100, 'completion_tokens': 10,
                           'total_tokens': 110})
    return {
        'label': 'structured synthetic only',
        'company': {'company': STRUCTURED_COMPANY,
                    'thscode': STRUCTURED_THSCODE,
                    'identity_confirmed': True},
        'model_script': model_script,
        'reference_script': [structured_reference(value)],
        'preset': 'qwen27',
        'pdf_path': str(pdf_path),
    }


def structured_distractors():
    return deepcopy(_DISTRACTORS)
