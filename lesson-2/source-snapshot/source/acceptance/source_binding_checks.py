"""Public synthetic regressions for structured source binding."""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP, localcontext
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

from .fixtures import income_envelope, write_pdf
from .services import run_with_services
from .structured_fixtures import (
    STRUCTURED_COMPANY,
    STRUCTURED_THSCODE,
    structured_company_value_candidate,
    structured_continuation_wrong_indices_candidate,
    structured_distractors,
    structured_reference,
    structured_scenario,
    structured_source_case,
    structured_long_source_case,
    structured_long_header_case,
    structured_period_consistency_case,
    structured_year_period_case,
    structured_column_path_period_case,
    structured_fragment_period_case,
    structured_sole_period_case,
    structured_title_period_case,
    structured_header_period_case,
    structured_incomplete_header_case,
    structured_review_case,
    structured_table_boundary_case,
    structured_wrong_year_candidate,
)


_NODE_REVIEW_CARDS = r'''
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {pathToFileURL} from 'node:url';
const {reviewCards} = await import(pathToFileURL(process.argv[1]).href);
assert.equal(typeof reviewCards, 'function', 'export the actual production reviewCards');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const copy = value => JSON.parse(JSON.stringify(value));
const expected = input.expected_cards;
function select(review, cards) {
  const before = copy(review);
  const actual = reviewCards(review);
  assert.deepEqual(actual, cards, 'card ID, label, units and both values must agree');
  assert.deepEqual(review, before, 'display selection must not mutate canonical review');
}
select(input.review, expected);
const reordered = copy(input.review);
reordered.metrics.reverse();
select(reordered, expected);
const grossChanged = copy(input.review);
grossChanged.gross_profit.current = '901.23';
grossChanged.gross_profit.prior = '802.34';
const grossCards = copy(expected);
Object.assign(grossCards.find(card => card.id === 'gross_profit'),
              {current: '901.23', prior: '802.34'});
select(grossChanged, grossCards);
const revenueChanged = copy(input.review);
Object.assign(revenueChanged.metrics.find(row => row.metric === 'revenue'),
              {current: '703.45', prior: '604.56'});
const revenueCards = copy(expected);
Object.assign(revenueCards.find(card => card.id === 'revenue'),
              {current: '703.45', prior: '604.56'});
select(revenueChanged, revenueCards);
console.log(JSON.stringify({ok: true, checks: 4,
                           card_ids: expected.map(card => card.id)}));
'''


def _load(path):
    return json.loads(Path(path).read_text())


class SourceBindingChecks:
    """Requires subject and output properties from the host TestCase."""

    def _validate_structured(self, value, pages):
        return self.subject.validate(value, pages, [1, 2],
                                     expected_company=STRUCTURED_COMPANY)

    def _assert_five_bound_rows(self, result, value):
        self.assertTrue(result['passed'], result)
        bound = result.get('bound_rows')
        self.assertIsInstance(bound, list)
        self.assertEqual(len(bound), 5, result)
        expected = {row['metric']: (row['current'], row['prior'])
                    for row in value['rows']}
        self.assertEqual({row['metric'] for row in bound}, set(expected))
        for row in bound:
            self.assertEqual((row['current_literal'], row['prior_literal']),
                             expected[row['metric']])
            expected_page = next(item['value_page'] for item in value['rows']
                                 if item['metric'] == row['metric'])
            self.assertEqual(row['page'], expected_page)

    def _review_cards_node(self, module, payload):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Node.js is required for public frontend behavior checks')
        module = Path(module).resolve()
        self.assertTrue(module.is_file(), 'freeze the production web/task-view.mjs module')
        result = subprocess.run(
            [node, '--input-type=module', '-e', _NODE_REVIEW_CARDS, str(module)],
            input=json.dumps(payload), text=True, capture_output=True, timeout=10,
            cwd=module.parent.parent)
        record = {'returncode': result.returncode, 'stdout': result.stdout,
                  'stderr': result.stderr, 'production_module': str(module)}
        self.output.mkdir(parents=True, exist_ok=True)
        (self.output / 'structured-review-cards.json').write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + '\n')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        summary = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertTrue(summary['ok'])
        self.assertEqual(summary['checks'], 4)
        self.assertEqual(summary['card_ids'],
                         ['revenue', 'parent_net_profit', 'gross_profit'])

    def test_05_structured_source_binding(self):
        for order in ('consolidated_first', 'company_first', 'reversed_years'):
            with self.subTest(valid_order=order):
                pages, value = structured_source_case(order)
                self._assert_five_bound_rows(
                    self._validate_structured(value, pages), value)

        for filler_count in (16, 64):
            for order in ('consolidated_first', 'company_first', 'reversed_years'):
                with self.subTest(valid_long_body_and_sections=(filler_count, order)):
                    long_pages, candidate = structured_long_source_case(filler_count, order)
                    self._assert_five_bound_rows(
                        self._validate_structured(candidate, long_pages), candidate)

        for metadata_lines in (16, 64):
            for order in ('consolidated_first', 'company_first', 'reversed_years'):
                with self.subTest(valid_long_header_chain=(metadata_lines, order)):
                    header_pages, candidate = structured_long_header_case(metadata_lines, order)
                    self._assert_five_bound_rows(
                        self._validate_structured(candidate, header_pages), candidate)
            with self.subTest(valid_long_consolidated_only_header=metadata_lines):
                header_pages, candidate = structured_long_header_case(
                    metadata_lines, kind='consolidated_only')
                self._assert_five_bound_rows(
                    self._validate_structured(candidate, header_pages), candidate)

        for metadata_lines in (16, 64):
            for kind in ('repeat_same_H1', 'equivalent_Jan1_Jun30'):
                for order in ('h1_first', 'other_first'):
                    with self.subTest(valid_period_consistency=(metadata_lines, kind, order)):
                        period_pages, candidate = structured_period_consistency_case(
                            kind, metadata_lines, order)
                        self._assert_five_bound_rows(
                            self._validate_structured(candidate, period_pages), candidate)

        for metadata_lines in (16, 64):
            for order in ('h1_first', 'other_first'):
                with self.subTest(valid_year_prefixed_period=(metadata_lines, order)):
                    year_pages, candidate = structured_year_period_case(
                        'complete_H1', metadata_lines, order)
                    self._assert_five_bound_rows(
                        self._validate_structured(candidate, year_pages), candidate)

        for side in ('current', 'prior'):
            for order in ('h1_first', 'other_first'):
                with self.subTest(valid_extra_column_path_period=(side, order)):
                    path_pages, candidate = structured_column_path_period_case(
                        'complete_H1', side, order)
                    self._assert_five_bound_rows(
                        self._validate_structured(candidate, path_pages), candidate)

        for metadata_lines in (16, 64):
            for order in ('h1_first', 'other_first'):
                with self.subTest(valid_same_fragment_local_periods=(metadata_lines, order)):
                    fragment_pages, candidate = structured_fragment_period_case(
                        'complete_H1', order, metadata_lines=metadata_lines)
                    self._assert_five_bound_rows(
                        self._validate_structured(candidate, fragment_pages), candidate)

        for side in ('current', 'prior'):
            for order in ('h1_first', 'other_first'):
                with self.subTest(valid_same_fragment_path_periods=(side, order)):
                    fragment_pages, candidate = structured_fragment_period_case(
                        'complete_H1', order, side=side)
                    self._assert_five_bound_rows(
                        self._validate_structured(candidate, fragment_pages), candidate)

        for form in ('month_range', 'date_range', 'end_duration'):
            for with_year in (False, True):
                with self.subTest(valid_sole_period_form=(form, with_year)):
                    sole_pages, candidate = structured_sole_period_case(form, with_year)
                    self._assert_five_bound_rows(
                        self._validate_structured(candidate, sole_pages), candidate)

        for kind in ('complete_H1', 'missing_duration'):
            for order in ('h1_first', 'other_first'):
                with self.subTest(same_fragment_title_periods=(kind, order)):
                    title_pages, candidate = structured_title_period_case(kind, order)
                    local = self._validate_structured(candidate, title_pages)
                    if kind == 'complete_H1':
                        self._assert_five_bound_rows(local, candidate)
                    else:
                        self.assertFalse(local['passed'], local)

        wrapped_pages, candidate = structured_long_source_case(16)
        wrapped_pages[0]['text'] = wrapped_pages[0]['text'].replace(
            '普通明细01 2 1 2 1', '普通明细01 2 1 2 1\n该普通明细的说明续行')
        with self.subTest(valid_long_body_wrapped_description=True):
            self._assert_five_bound_rows(
                self._validate_structured(candidate, wrapped_pages), candidate)
        for kind in ('second_h1', 'valid_after_invalid'):
            with self.subTest(valid_nearer_table=kind):
                local_pages, candidate = structured_table_boundary_case(kind)
                self._assert_five_bound_rows(
                    self._validate_structured(candidate, local_pages), candidate)

        with self.subTest(valid_untitled_header_owns_H1=True):
            local_pages, candidate = structured_header_period_case('h1')
            self._assert_five_bound_rows(
                self._validate_structured(candidate, local_pages), candidate)

        for kind in ('complete_h1', 'ordinary_prose',
                     'complete_after_zero', 'complete_after_one'):
            with self.subTest(valid_incomplete_header_pair=kind):
                local_pages, candidate = structured_incomplete_header_case(kind)
                self._assert_five_bound_rows(
                    self._validate_structured(candidate, local_pages), candidate)

        pages, good = structured_source_case()
        distractors = structured_distractors()
        bads = []
        for kind in ('second_q2', 'second_company', 'second_headerless',
                     'header_only_company', 'page2_headerless'):
            local_pages, candidate = structured_table_boundary_case(kind)
            bads.append((f'local table boundary {kind} cannot borrow an earlier header',
                         local_pages, candidate))

        for kind in ('q2', 'h1_q2', 'q2_h1', 'missing'):
            local_pages, candidate = structured_header_period_case(kind)
            bads.append((f'untitled new header owns {kind} period and cannot inherit H1',
                         local_pages, candidate))

        for kind in ('zero_year', 'one_year', 'missing_scope',
                     'scope_count_mismatch', 'scope_conflict',
                     'scope_conflict_reverse', 'zero_year_q2', 'one_year_q2'):
            local_pages, candidate = structured_incomplete_header_case(kind)
            bads.append((f'explicit new {kind} header cannot fall through to an old owner',
                         local_pages, candidate))

        for metadata_lines in (16, 64):
            for kind in ('one_year', 'scope_conflict', 'scope_conflict_reverse',
                         'h1_q2', 'q2_h1'):
                header_pages, candidate = structured_long_header_case(
                    metadata_lines, kind=kind)
                bads.append((f'long metadata chain {metadata_lines} retains {kind} failure',
                             header_pages, candidate))

        for metadata_lines in (16, 64):
            for kind in ('May31', 'Jun15', 'five_months', 'Feb1_start',
                         'missing_day', 'missing_duration_June30'):
                for order in ('h1_first', 'other_first'):
                    period_pages, candidate = structured_period_consistency_case(
                        kind, metadata_lines, order)
                    bads.append((f'all local period declarations must agree: {metadata_lines}/{kind}/{order}',
                                 period_pages, candidate))

        for metadata_lines in (16, 64):
            for order in ('h1_first', 'other_first'):
                year_pages, candidate = structured_year_period_case(
                    'missing_duration', metadata_lines, order)
                bads.append((f'year prefix cannot complete a missing duration: {metadata_lines}/{order}',
                             year_pages, candidate))

        for kind in ('other_duration', 'missing_duration'):
            for side in ('current', 'prior'):
                for order in ('h1_first', 'other_first'):
                    path_pages, candidate = structured_column_path_period_case(kind, side, order)
                    bads.append((f'every cited column-path period must be complete H1: {kind}/{side}/{order}',
                                 path_pages, candidate))

        for metadata_lines in (16, 64):
            for order in ('h1_first', 'other_first'):
                fragment_pages, candidate = structured_fragment_period_case(
                    'missing_duration', order, metadata_lines=metadata_lines)
                bads.append((f'every local declaration inside one fragment must be complete: {metadata_lines}/{order}',
                             fragment_pages, candidate))

        for side in ('current', 'prior'):
            for order in ('h1_first', 'other_first'):
                fragment_pages, candidate = structured_fragment_period_case(
                    'missing_duration', order, side=side)
                bads.append((f'every column-path declaration inside one fragment must be complete: {side}/{order}',
                             fragment_pages, candidate))

        def period_variant(new_title, new_period):
            changed_pages = deepcopy(pages)
            old_title = good['scope_evidence']['quote']
            old_period = good['current_column_path'][0]
            for page in changed_pages:
                page['text'] = page['text'].replace(old_title, new_title)
                page['text'] = page['text'].replace(old_period, new_period)
            changed = deepcopy(good)
            changed['scope_evidence']['quote'] = new_title
            for side in ('current', 'prior'):
                changed[side + '_column_path'][0] = new_period
                for evidence in changed[side + '_column_evidence']:
                    if evidence['quote'] == old_period:
                        evidence['quote'] = new_period
            return changed_pages, changed

        one_to_six_pages = deepcopy(pages)
        old_title = good['scope_evidence']['quote']
        old_period = good['current_column_path'][0]
        current_range = '2026年1-6月'
        prior_range = '2025年1-6月'
        for page in one_to_six_pages:
            page['text'] = page['text'].replace(
                old_title, '2026年1-6月合并及公司利润表')
            page['text'] = page['text'].replace(old_period, '1-6月')
            page['text'] = page['text'].replace(
                '2026年 2025年 2026年 2025年',
                f'{current_range} {prior_range} {current_range} {prior_range}')
        one_to_six = deepcopy(good)
        one_to_six['scope_evidence']['quote'] = '2026年1-6月合并及公司利润表'
        one_to_six['current_column_path'] = [current_range, '合并']
        one_to_six['prior_column_path'] = [prior_range, '合并']
        one_to_six['current_column_evidence'] = [
            {'page': page, 'quote': quote}
            for page in (1, 2) for quote in (current_range, '合并')]
        one_to_six['prior_column_evidence'] = [
            {'page': page, 'quote': quote}
            for page in (1, 2) for quote in (prior_range, '合并')]
        with self.subTest(valid_full_January_to_June_range=True):
            self._assert_five_bound_rows(
                self._validate_structured(one_to_six, one_to_six_pages),
                one_to_six)

        exact_dates_pages = deepcopy(pages)
        exact_current = '2026年1月1日至6月30日'
        exact_prior = '2025年1月1日至6月30日'
        for page in exact_dates_pages:
            page['text'] = page['text'].replace(
                old_title, exact_current + '合并及公司利润表')
            page['text'] = page['text'].replace(
                old_period, '1月1日至6月30日')
            page['text'] = page['text'].replace(
                '2026年 2025年 2026年 2025年',
                f'{exact_current} {exact_prior} {exact_current} {exact_prior}')
        exact_dates = deepcopy(good)
        exact_dates['scope_evidence']['quote'] = exact_current + '合并及公司利润表'
        exact_dates['current_column_path'] = [exact_current, '合并']
        exact_dates['prior_column_path'] = [exact_prior, '合并']
        exact_dates['current_column_evidence'] = [
            {'page': page, 'quote': quote}
            for page in (1, 2) for quote in (exact_current, '合并')]
        exact_dates['prior_column_evidence'] = [
            {'page': page, 'quote': quote}
            for page in (1, 2) for quote in (exact_prior, '合并')]
        with self.subTest(valid_exact_January_1_through_June_30=True):
            self._assert_five_bound_rows(
                self._validate_structured(exact_dates, exact_dates_pages),
                exact_dates)

        bare_note_pages = deepcopy(pages)
        bare_note_pages[1]['text'] = bare_note_pages[1]['text'].replace(
            '三(19)', '(19)')
        with self.subTest(valid_parenthesized_note_cell=True):
            self._assert_five_bound_rows(
                self._validate_structured(good, bare_note_pages), good)

        contextual_eps_unit = deepcopy(good)
        page2_lines = pages[1]['text'].splitlines()
        context_start = page2_lines.index(
            '（除基本每股收益外，金额单位为人民币万元）')
        context_end = next(
            index for index, line in enumerate(page2_lines)
            if line.startswith('基本每股收益(人民币元)'))
        eps = next(row for row in contextual_eps_unit['rows']
                   if row['metric'] == 'basic_eps')
        eps['unit_quote'] = '\n'.join(page2_lines[context_start:context_end + 1])
        with self.subTest(valid_contiguous_EPS_unit_context=True):
            self._assert_five_bound_rows(
                self._validate_structured(contextual_eps_unit, pages),
                contextual_eps_unit)

        wrong_column = structured_company_value_candidate()
        bads.append(('company values under consolidated path', pages, wrong_column))

        wrong_continuation_indices = structured_continuation_wrong_indices_candidate()
        bads.append(('continuation row cannot reuse first-page column indices',
                     pages, wrong_continuation_indices))

        wrong_year = structured_wrong_year_candidate()
        bads.append(('current and prior year paths reversed', pages, wrong_year))

        quarter_pages, quarter = period_variant(
            '2026年4-6月单季合并及公司利润表', '4-6月单季')
        bads.append(('single quarter is not H1', quarter_pages, quarter))

        wrong_end_pages, wrong_end = period_variant(
            '截至 2026 年 9 月 30 日止六个月期间合并及公司利润表',
            '截至 9 月 30 日止六个月期间')
        bads.append(('six months ending outside H1', wrong_end_pages, wrong_end))

        may_end_pages, may_end = period_variant(
            '截至 2026 年 5 月 31 日止六个月期间合并及公司利润表',
            '截至 5 月 31 日止六个月期间')
        bads.append(('six months ending May 31 is not H1',
                     may_end_pages, may_end))

        dateless_pages, dateless = period_variant(
            '2026年六个月期间合并及公司利润表', '六个月期间')
        bads.append(('six months without an end date is not H1',
                     dateless_pages, dateless))

        three_month_pages, three_month = period_variant(
            '截至 2026 年 6 月 30 日止三个月期间合并及公司利润表',
            '截至 6 月 30 日止三个月期间')
        bads.append(('three months ending June 30 is not H1',
                     three_month_pages, three_month))

        incomplete = deepcopy(good)
        incomplete['current_column_path'] = ['2026年', '合并']
        incomplete['current_column_evidence'] = [
            {'page': 1, 'quote': '2026年'}, {'page': 1, 'quote': '合并'}]
        bads.append(('year and scope without cumulative context', pages, incomplete))

        wrong_total = deepcopy(good)
        revenue = next(row for row in wrong_total['rows']
                       if row['metric'] == 'revenue')
        revenue.update(original_label=distractors['total_revenue']['label'],
                       current=distractors['total_revenue']['2026'],
                       prior=distractors['total_revenue']['2025'])
        bads.append(('total revenue cannot satisfy revenue', pages, wrong_total))

        wrong_total_cost = deepcopy(good)
        cost = next(row for row in wrong_total_cost['rows']
                    if row['metric'] == 'operating_cost')
        cost.update(original_label=distractors['total_cost']['label'],
                    current=distractors['total_cost']['2026'],
                    prior=distractors['total_cost']['2025'])
        bads.append(('total cost cannot satisfy operating cost', pages,
                     wrong_total_cost))

        diluted = deepcopy(good)
        eps = next(row for row in diluted['rows'] if row['metric'] == 'basic_eps')
        eps.update(original_label=distractors['diluted_eps']['label'],
                   current=distractors['diluted_eps']['2026'],
                   prior=distractors['diluted_eps']['2025'],
                   unit_quote=distractors['diluted_eps']['label'])
        bads.append(('diluted EPS cannot satisfy basic EPS', pages, diluted))

        prefixed_pages = deepcopy(pages)
        prefixed_pages[0]['text'] += '\n其他营业收入 310 280 31 28'
        arbitrary_prefix = deepcopy(good)
        revenue = next(row for row in arbitrary_prefix['rows']
                       if row['metric'] == 'revenue')
        revenue['original_label'] = '其他营业收入'
        bads.append(('arbitrary display prefix cannot satisfy revenue',
                     prefixed_pages, arbitrary_prefix))

        note_as_number = deepcopy(good)
        eps = next(row for row in note_as_number['rows']
                   if row['metric'] == 'basic_eps')
        eps['current'] = '(19)'
        eps['prior'] = '1.25'
        bads.append(('note reference cannot become a financial value',
                     pages, note_as_number))

        amount_exclusion_as_eps_unit = deepcopy(good)
        eps = next(row for row in amount_exclusion_as_eps_unit['rows']
                   if row['metric'] == 'basic_eps')
        eps['unit_quote'] = '（除基本每股收益外，金额单位为人民币万元）'
        bads.append(('amount-unit exclusion does not prove unscaled EPS unit',
                     pages, amount_exclusion_as_eps_unit))

        def eps_caption_case(source_unit):
            caption_pages = deepcopy(pages)
            caption = ('（除基本每股收益外，金额单位为人民币万元；'
                       f'基本每股收益单位为{source_unit}）')
            caption_pages[1]['text'] = caption_pages[1]['text'].replace(
                '基本每股收益(人民币元) 三(19)', '基本每股收益 三(19)')
            caption_pages[1]['text'] = caption_pages[1]['text'].replace(
                '（除基本每股收益外，金额单位为人民币万元）', caption)
            candidate = deepcopy(good)
            eps = next(row for row in candidate['rows']
                       if row['metric'] == 'basic_eps')
            eps['original_label'] = '基本每股收益'
            eps['unit_quote'] = caption
            return caption_pages, candidate

        for source_unit in ('元/股', '人民币元/股', '人民币元'):
            caption_pages, candidate = eps_caption_case(source_unit)
            with self.subTest(valid_complete_EPS_caption_unit=source_unit):
                self._assert_five_bound_rows(
                    self._validate_structured(candidate, caption_pages),
                    candidate)

        for allowed_unit in ('元/股', '人民币元/股', '人民币元'):
            for suffix_kind, suffix in (('CJK', '未知'), ('ASCII', 'xyz'),
                                        ('digit', '7'), ('slash', '/未知')):
                source_unit = allowed_unit + suffix
                caption_pages, candidate = eps_caption_case(source_unit)
                bads.append((f'complete EPS unit {allowed_unit} with unknown {suffix_kind} suffix',
                             caption_pages, candidate))

        for allowed_unit in ('元/股', '人民币元/股', '人民币元'):
            for prefix_kind, prefix in (('CJK', '未知'), ('ASCII', 'xyz'),
                                        ('digit', '7'), ('slash', '/未知')):
                source_unit = prefix + allowed_unit
                caption_pages, candidate = eps_caption_case(source_unit)
                bads.append((f'complete EPS unit {allowed_unit} with unknown {prefix_kind} prefix',
                             caption_pages, candidate))

        inline_suffix_pages = deepcopy(pages)
        source_label = '基本每股收益(人民币元未知)'
        inline_suffix_pages[1]['text'] = inline_suffix_pages[1]['text'].replace(
            '基本每股收益(人民币元) 三(19)', source_label + ' 三(19)')
        inline_suffix = deepcopy(good)
        eps = next(row for row in inline_suffix['rows']
                   if row['metric'] == 'basic_eps')
        eps['original_label'] = source_label
        eps['unit_quote'] = source_label
        bads.append(('inline RMB-yuan EPS unit with unknown suffix is not a known complete unit',
                     inline_suffix_pages, inline_suffix))

        for allowed_unit in ('元/股', '人民币元/股', '人民币元'):
            for affix_kind, affix in (('CJK', '未知'), ('ASCII', 'xyz'),
                                      ('digit', '7'), ('slash', '/未知')):
                for side in ('left', 'right'):
                    if (allowed_unit, affix_kind, side) == ('人民币元', 'CJK', 'right'):
                        continue  # The unchanged inline_suffix case above covers this expression.
                    source_unit = (affix + allowed_unit if side == 'left'
                                   else allowed_unit + affix)
                    source_label = f'基本每股收益({source_unit})'
                    inline_pages = deepcopy(pages)
                    inline_pages[1]['text'] = inline_pages[1]['text'].replace(
                        '基本每股收益(人民币元) 三(19)', source_label + ' 三(19)')
                    candidate = deepcopy(good)
                    eps = next(row for row in candidate['rows']
                               if row['metric'] == 'basic_eps')
                    eps['original_label'] = source_label
                    eps['unit_quote'] = source_label
                    bads.append((f'inline EPS unit {allowed_unit} with unknown {affix_kind} {side} affix',
                                 inline_pages, candidate))

        unknown_currencies = tuple(f'合成币{index:02d}元/股'
                                   for index in (1, 2, 3))
        for source_unit in (('日元/股', '欧元/股', '英镑/股', '美元/股', '港元/股')
                            + unknown_currencies
                            + ('人民币百元/股', '人民币兆元/股')):
            caption_pages, candidate = eps_caption_case(source_unit)
            bads.append((f'complete EPS caption unit {source_unit} is not unscaled CNY',
                         caption_pages, candidate))

        for source_unit in ('人民币元/股', '元/股'):
            unscaled_pages = deepcopy(pages)
            source_label = f'基本每股收益({source_unit})'
            unscaled_pages[1]['text'] = unscaled_pages[1]['text'].replace(
                '基本每股收益(人民币元) 三(19)', source_label + ' 三(19)')
            unscaled = deepcopy(good)
            eps = next(row for row in unscaled['rows']
                       if row['metric'] == 'basic_eps')
            eps['original_label'] = source_label
            eps['unit_quote'] = source_label
            with self.subTest(valid_unscaled_EPS_unit=source_unit):
                self._assert_five_bound_rows(
                    self._validate_structured(unscaled, unscaled_pages),
                    unscaled)

        for source_unit in ('人民币千元', '人民币万元', '人民币亿元',
                            '人民币千元/股', '人民币万元/股', '人民币亿元/股',
                            '美元/股', '港元/股'):
            scaled_pages = deepcopy(pages)
            source_label = f'基本每股收益({source_unit})'
            scaled_pages[1]['text'] = scaled_pages[1]['text'].replace(
                '基本每股收益(人民币元) 三(19)', source_label + ' 三(19)')
            scaled = deepcopy(good)
            eps = next(row for row in scaled['rows']
                       if row['metric'] == 'basic_eps')
            eps['original_label'] = source_label
            eps['unit_quote'] = source_label
            bads.append((f'EPS label {source_unit} does not prove unscaled CNY 元/股',
                         scaled_pages, scaled))

        partial_h1_pages = deepcopy(pages)
        full_ranges = ('2026年1月1日至6月15日', '2025年1月1日至6月15日')
        for page in partial_h1_pages:
            page['text'] = page['text'].replace(
                old_title, '2026年1月1日至6月15日合并及公司利润表')
            page['text'] = page['text'].replace(old_period, '1月1日至6月15日')
            page['text'] = page['text'].replace(
                '2026年 2025年 2026年 2025年',
                f'{full_ranges[0]} {full_ranges[1]} {full_ranges[0]} {full_ranges[1]}')
        partial_h1 = deepcopy(good)
        partial_h1['scope_evidence']['quote'] = '2026年1月1日至6月15日合并及公司利润表'
        partial_h1['current_column_path'] = [full_ranges[0], '合并']
        partial_h1['prior_column_path'] = [full_ranges[1], '合并']
        partial_h1['current_column_evidence'] = [
            {'page': page, 'quote': quote}
            for page in (1, 2) for quote in (full_ranges[0], '合并')]
        partial_h1['prior_column_evidence'] = [
            {'page': page, 'quote': quote}
            for page in (1, 2) for quote in (full_ranges[1], '合并')]
        bads.append(('January 1 through June 15 is not full H1',
                     partial_h1_pages, partial_h1))

        page2_quarter_pages = deepcopy(pages)
        old_title = good['scope_evidence']['quote']
        old_period = good['current_column_path'][0]
        page2_quarter_pages[1]['text'] = page2_quarter_pages[1]['text'].replace(
            old_title, '截至 2026 年 6 月 30 日止三个月期间合并及公司利润表')
        page2_quarter_pages[1]['text'] = page2_quarter_pages[1]['text'].replace(
            old_period, '截至 6 月 30 日止三个月期间')
        page2_borrowing = deepcopy(good)
        for side in ('current', 'prior'):
            page2_borrowing[side + '_column_evidence'] = [
                evidence for evidence in page2_borrowing[side + '_column_evidence']
                if evidence['page'] == 1]
        bads.append(('page-2 EPS cannot borrow page-1 H1 citations',
                     page2_quarter_pages, page2_borrowing))

        unrelated_header_pages = deepcopy(pages)
        unrelated_header_pages[1]['text'] = '\n'.join([
            '另一张半年合并及公司数据表',
            '项目 附注 2026年 2025年 2026年 2025年',
            '合并 合并 公司 公司',
            '其他指标 99 88 9 8',
            '',
            unrelated_header_pages[1]['text'],
        ])
        with self.subTest(valid_multiple_tables_use_local_header=True):
            self._assert_five_bound_rows(
                self._validate_structured(good, unrelated_header_pages), good)
        earlier_header_values = deepcopy(good)
        eps = next(row for row in earlier_header_values['rows']
                   if row['metric'] == 'basic_eps')
        eps['current'] = '0.25'
        eps['prior'] = '0.20'
        bads.append(('row uses the closest local table header, not an earlier one',
                     unrelated_header_pages, earlier_header_values))

        consolidated_only_pages = deepcopy(pages)
        consolidated_only_pages[1]['text'] = '\n'.join([
            STRUCTURED_COMPANY,
            '截至 2026 年 6 月 30 日止六个月期间合并利润表(续)',
            '（除基本每股收益外，金额单位为人民币万元）',
            old_period,
            '项目 2026年 2025年',
            '基本每股收益(人民币元) 1.25 1.10',
            '稀释每股收益(人民币元) 1.20 1.05',
        ])
        with self.subTest(valid_consolidated_only_title_without_scope_row=True):
            self._assert_five_bound_rows(
                self._validate_structured(good, consolidated_only_pages), good)

        company_only_pages = deepcopy(pages)
        company_only_pages[1]['text'] = '\n'.join([
            STRUCTURED_COMPANY,
            '合并口径另表列示',
            '截至 2026 年 6 月 30 日止六个月期间公司利润表',
            old_period,
            '项目 2026年 2025年',
            '基本每股收益(人民币元) 0.25 0.20',
        ])
        company_only = deepcopy(good)
        eps = next(row for row in company_only['rows']
                   if row['metric'] == 'basic_eps')
        eps['current'] = '0.25'
        eps['prior'] = '0.20'
        bads.append(('company-only local table cannot default to consolidated',
                     company_only_pages, company_only))

        for label, bad_pages, value in bads:
            with self.subTest(rejected=label):
                result = self._validate_structured(value, bad_pages)
                self.assertFalse(result['passed'], result)
                self.assertTrue(result['rules'], result)

    def test_06_structured_verification(self):
        pages, value = structured_source_case()
        envelope = income_envelope(structured_reference())
        compared = self.subject.compare(
            value, value, envelope, pages,
            expected_thscode=STRUCTURED_THSCODE,
            expected_company=STRUCTURED_COMPANY,
        )
        self.assertTrue(compared['internal']['passed'], compared)
        self.assertEqual(compared['internal']['matched'], 10)
        self.assertTrue(compared['external']['passed'], compared)
        self.assertEqual(compared['external']['matched'], 10)

        for kind in ('h1', 'q2', 'h1_q2', 'q2_h1', 'missing'):
            with self.subTest(shared_binder_untitled_header_period=kind):
                local_pages, candidate = structured_header_period_case(kind)
                local = self.subject.compare(
                    candidate, candidate, envelope, local_pages,
                    expected_thscode=STRUCTURED_THSCODE,
                    expected_company=STRUCTURED_COMPANY,
                )
                self.assertEqual(local['internal']['passed'], kind == 'h1', local)
                self.assertEqual(local['external']['passed'], kind == 'h1', local)

        accepted_headers = ('complete_h1', 'ordinary_prose',
                            'complete_after_zero', 'complete_after_one')
        for kind in accepted_headers + ('zero_year', 'one_year', 'missing_scope',
                                        'scope_count_mismatch', 'scope_conflict',
                                        'scope_conflict_reverse', 'zero_year_q2',
                                        'one_year_q2'):
            with self.subTest(shared_binder_incomplete_header=kind):
                local_pages, candidate = structured_incomplete_header_case(kind)
                local = self.subject.compare(
                    candidate, candidate, envelope, local_pages,
                    expected_thscode=STRUCTURED_THSCODE,
                    expected_company=STRUCTURED_COMPANY,
                )
                self.assertEqual(local['internal']['passed'], kind in accepted_headers, local)
                self.assertEqual(local['external']['passed'], kind in accepted_headers, local)

        for metadata_lines in (16, 64):
            for kind in ('one_year', 'scope_conflict', 'scope_conflict_reverse',
                         'h1_q2', 'q2_h1'):
                with self.subTest(shared_binder_long_header_failure=(metadata_lines, kind)):
                    header_pages, candidate = structured_long_header_case(
                        metadata_lines, kind=kind)
                    local = self.subject.compare(
                        candidate, candidate, envelope, header_pages,
                        expected_thscode=STRUCTURED_THSCODE,
                        expected_company=STRUCTURED_COMPANY,
                    )
                    self.assertFalse(local['internal']['passed'], local)
                    self.assertFalse(local['external']['passed'], local)

        accepted_periods = ('repeat_same_H1', 'equivalent_Jan1_Jun30')
        for metadata_lines in (16, 64):
            for kind in accepted_periods + ('May31', 'Jun15', 'five_months', 'Feb1_start',
                                            'missing_day', 'missing_duration_June30'):
                for order in ('h1_first', 'other_first'):
                    with self.subTest(shared_binder_period_consistency=(metadata_lines, kind, order)):
                        period_pages, candidate = structured_period_consistency_case(
                            kind, metadata_lines, order)
                        local = self.subject.compare(
                            candidate, candidate, envelope, period_pages,
                            expected_thscode=STRUCTURED_THSCODE,
                            expected_company=STRUCTURED_COMPANY,
                        )
                        self.assertEqual(local['internal']['passed'], kind in accepted_periods, local)
                        self.assertEqual(local['external']['passed'], kind in accepted_periods, local)

        for metadata_lines in (16, 64):
            for kind in ('complete_H1', 'missing_duration'):
                for order in ('h1_first', 'other_first'):
                    with self.subTest(shared_binder_year_period=(metadata_lines, kind, order)):
                        year_pages, candidate = structured_year_period_case(kind, metadata_lines, order)
                        local = self.subject.compare(
                            candidate, candidate, envelope, year_pages,
                            expected_thscode=STRUCTURED_THSCODE,
                            expected_company=STRUCTURED_COMPANY,
                        )
                        self.assertEqual(local['internal']['passed'], kind == 'complete_H1', local)
                        self.assertEqual(local['external']['passed'], kind == 'complete_H1', local)

        for kind in ('complete_H1', 'other_duration', 'missing_duration'):
            for side in ('current', 'prior'):
                for order in ('h1_first', 'other_first'):
                    with self.subTest(shared_binder_column_path_period=(kind, side, order)):
                        path_pages, candidate = structured_column_path_period_case(kind, side, order)
                        local = self.subject.compare(
                            candidate, candidate, envelope, path_pages,
                            expected_thscode=STRUCTURED_THSCODE,
                            expected_company=STRUCTURED_COMPANY,
                        )
                        self.assertEqual(local['internal']['passed'], kind == 'complete_H1', local)
                        self.assertEqual(local['external']['passed'], kind == 'complete_H1', local)

        for metadata_lines in (16, 64):
            for kind in ('complete_H1', 'missing_duration'):
                for order in ('h1_first', 'other_first'):
                    with self.subTest(shared_binder_fragment_block=(metadata_lines, kind, order)):
                        fragment_pages, candidate = structured_fragment_period_case(
                            kind, order, metadata_lines=metadata_lines)
                        local = self.subject.compare(
                            candidate, candidate, envelope, fragment_pages,
                            expected_thscode=STRUCTURED_THSCODE,
                            expected_company=STRUCTURED_COMPANY,
                        )
                        self.assertEqual(local['internal']['passed'], kind == 'complete_H1', local)
                        self.assertEqual(local['external']['passed'], kind == 'complete_H1', local)

        for kind in ('complete_H1', 'missing_duration'):
            for side in ('current', 'prior'):
                for order in ('h1_first', 'other_first'):
                    with self.subTest(shared_binder_fragment_path=(kind, side, order)):
                        fragment_pages, candidate = structured_fragment_period_case(kind, order, side=side)
                        local = self.subject.compare(
                            candidate, candidate, envelope, fragment_pages,
                            expected_thscode=STRUCTURED_THSCODE,
                            expected_company=STRUCTURED_COMPANY,
                        )
                        self.assertEqual(local['internal']['passed'], kind == 'complete_H1', local)
                        self.assertEqual(local['external']['passed'], kind == 'complete_H1', local)

        for form in ('month_range', 'date_range', 'end_duration'):
            for with_year in (False, True):
                with self.subTest(shared_binder_sole_period_form=(form, with_year)):
                    sole_pages, candidate = structured_sole_period_case(form, with_year)
                    local = self.subject.compare(
                        candidate, candidate, envelope, sole_pages,
                        expected_thscode=STRUCTURED_THSCODE,
                        expected_company=STRUCTURED_COMPANY,
                    )
                    self.assertTrue(local['internal']['passed'], local)
                    self.assertTrue(local['external']['passed'], local)

        for kind in ('complete_H1', 'missing_duration'):
            for order in ('h1_first', 'other_first'):
                with self.subTest(shared_binder_title_periods=(kind, order)):
                    title_pages, candidate = structured_title_period_case(kind, order)
                    local = self.subject.compare(
                        candidate, candidate, envelope, title_pages,
                        expected_thscode=STRUCTURED_THSCODE,
                        expected_company=STRUCTURED_COMPANY,
                    )
                    self.assertEqual(local['internal']['passed'], kind == 'complete_H1', local)
                    self.assertEqual(local['external']['passed'], kind == 'complete_H1', local)

        for year in (2026, 2025):
            for identity_state in ('missing', 'null', 'empty'):
                with self.subTest(official_target_invalid_thscode=(year, identity_state)):
                    missing_identity = deepcopy(envelope)
                    missing_identity['thscode'] = STRUCTURED_THSCODE
                    target = next(item for item in missing_identity['data']['item']
                                  if item['fiscal_year'] == year)
                    if identity_state == 'missing':
                        del target['thscode']
                    else:
                        target['thscode'] = None if identity_state == 'null' else ''
                    rejected = self.subject.compare(
                        value, value, missing_identity, pages,
                        expected_thscode=STRUCTURED_THSCODE,
                        expected_company=STRUCTURED_COMPANY,
                    )
                    self.assertFalse(rejected['external']['passed'], rejected)

        visual_company_values = structured_continuation_wrong_indices_candidate()
        rejected = self.subject.compare(
            value, visual_company_values, envelope, pages,
            expected_thscode=STRUCTURED_THSCODE,
            expected_company=STRUCTURED_COMPANY,
        )
        self.assertFalse(rejected['internal']['passed'], rejected)

        folder = self.output / 'structured-source-binding'
        folder.mkdir(parents=True, exist_ok=True)
        pdf = folder / 'structured-synthetic.pdf'
        pages, value = structured_review_case()
        self.assertLessEqual(max(len(page['text'].splitlines()) for page in pages), 38,
                             'keep all source rows visible on the existing PDF page size')
        write_pdf(pdf, texts=tuple(page['text'] for page in pages))
        scenario = structured_scenario(pdf, value)
        scenario['preset'] = 'qwen9'
        result, receipts = run_with_services(
            self.subject, scenario, folder / 'run')

        state = _load(result['state_file'])
        trace = _load(result['trace_file'])
        self.assertEqual(state['status'], 'candidate_ready', state)
        self.assertTrue(state['review'], state)
        self.assertTrue(state['current']['internal']['passed'], state)
        self.assertEqual(state['current']['internal']['matched'], 10)
        self.assertTrue(state['current']['external']['passed'], state)
        self.assertEqual(state['current']['external']['matched'], 10)
        self.assertEqual([item['expected_stage']
                          for item in receipts['model_receipts']],
                         ['locate', 'extract', 'vision'])
        self.assertEqual(len(receipts['reference_receipts']), 1)
        self.assertEqual(receipts['errors'], [])
        self.assertEqual(len(trace['candidates']), 1)
        self.assertEqual([item['stage'] for item in trace['requests']],
                         ['locate', 'extract', 'vision'])
        preset = _load(self.project / 'contracts/workflow.json')['presets']['qwen9']
        self.assertNotEqual(preset['text_model'], preset['vision_model'])
        for receipt, request in zip(receipts['model_receipts'], trace['requests']):
            self.assertEqual(request['stage'], receipt['expected_stage'])
            expected_model = (preset['vision_model'] if receipt['expected_stage'] == 'vision'
                              else preset['text_model'])
            self.assertEqual(receipt['request']['model'], expected_model,
                             'actual provider-bound model must follow the frozen preset role')
            self.assertEqual(_load(request['request_path'])['model'], expected_model,
                             'retained actual request must use the same declared role model')

        review_rows = {row['metric']: row for row in state['review']['metrics']}
        self.assertEqual(set(review_rows),
                         {row['metric'] for row in value['rows']})
        for row in value['rows']:
            actual = review_rows[row['metric']]
            self.assertEqual(actual['current_raw'], row['current'])
            self.assertEqual(actual['prior_raw'], row['prior'])

        review = state['review']
        self.assertNotIn('summary', review, 'keep one canonical financial projection')
        self.assertNotIn('series', review, 'charts select the canonical metric rows')
        self.assertEqual(len(review['metrics']), 5)
        with localcontext() as context:
            context.prec = 50

            def source_number(raw):
                text = raw.replace(',', '')
                negative = text.startswith('(') and text.endswith(')')
                return -Decimal(text[1:-1]) if negative else Decimal(text)

            def display(number):
                return format(number.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), '.2f')

            canonical = {}
            for row in value['rows']:
                metric = row['metric']
                scale = Decimal(1) if metric == 'basic_eps' else Decimal(10000)
                signed = tuple(source_number(row[side]) * scale
                               for side in ('current', 'prior'))
                pair = tuple(abs(number) for number in signed) if metric == 'operating_cost' else signed
                canonical[metric] = pair
                actual = review_rows[metric]
                unit = '元/股' if metric == 'basic_eps' else '亿元'
                self.assertEqual(actual['unit'], unit)
                self.assertEqual(actual['display_unit'], unit)
                self.assertEqual(actual['source_unit'], row['unit'])
                divisor = Decimal(1) if metric == 'basic_eps' else Decimal(100000000)
                for side, number in zip(('current', 'prior'), pair):
                    self.assertEqual(actual[side], display(number / divisor))
                growth = display((pair[0] - pair[1]) / pair[1] * 100) if pair[1] > 0 else None
                self.assertEqual(actual['yoy_percent'], growth)
                if metric == 'operating_cost':
                    self.assertTrue(all(row[side].startswith('(') and row[side].endswith(')')
                                        for side in ('current', 'prior')))
                    self.assertEqual(review['normalizations'], [{
                        'metric': 'operating_cost', 'policy': 'expense_magnitude',
                        'current_signed_yuan': str(signed[0]),
                        'prior_signed_yuan': str(signed[1]),
                        'current_yuan': str(pair[0]), 'prior_yuan': str(pair[1]),
                    }])

            revenue = canonical['revenue']
            cost = canonical['operating_cost']
            gross = tuple(income - expense for income, expense in zip(revenue, cost))
            expected_gross = {
                'current': display(gross[0] / Decimal(100000000)),
                'prior': display(gross[1] / Decimal(100000000)), 'unit': '亿元',
            }
            self.assertEqual(review['gross_profit'], expected_gross)
            gross_margin = gross[0] / revenue[0] * 100
            net_margin = canonical['parent_net_profit'][0] / revenue[0] * 100
            self.assertEqual(review['gross_margin_percent']['current'], display(gross_margin))
            self.assertEqual(review['net_margin_percent']['current'], display(net_margin))
            displayed_revenue = Decimal(review_rows['revenue']['current'])
            displayed_cost = Decimal(review_rows['operating_cost']['current'])
            self.assertNotEqual(expected_gross['current'],
                                display(displayed_revenue - displayed_cost),
                                'the fixture must expose subtraction of rounded displays')
            self.assertNotEqual(display(gross_margin),
                                display(Decimal(expected_gross['current']) / displayed_revenue * 100),
                                'the fixture must expose ratios from rounded displays')
            self.assertNotEqual(display(net_margin),
                                display(Decimal(review_rows['parent_net_profit']['current'])
                                        / displayed_revenue * 100))
            self.assertNotEqual(expected_gross['prior'], review_rows['revenue']['prior'],
                                'the paired prior values must expose a revenue-as-gross alias')

        expected_cards = [
            {'id': metric, 'label': label, 'current': review_rows[metric]['current'],
             'prior': review_rows[metric]['prior'], 'unit': '亿元'}
            for metric, label in (('revenue', '营业收入'),
                                  ('parent_net_profit', '归母净利润'))
        ] + [{'id': 'gross_profit', 'label': '毛利润', **expected_gross}]
        self._review_cards_node(
            Path(result['task_dir']) / 'program' / 'web' / 'task-view.mjs',
            {'review': review, 'expected_cards': expected_cards})

        archive = Path(result['sealed_archive'])
        self.assertTrue(archive.is_file(), result)
        with zipfile.ZipFile(archive) as sealed:
            names = sealed.namelist()
            self.assertEqual(len(names), len(set(names)))
            candidate_name = Path(trace['candidates'][0]['path']).name
            self.assertTrue(any(name.endswith('/' + candidate_name)
                                or name == candidate_name for name in names), names)
