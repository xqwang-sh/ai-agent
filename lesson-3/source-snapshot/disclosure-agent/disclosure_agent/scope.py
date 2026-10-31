"""Explicit reporting-period boundaries, independent of dates mentioned in context."""
from datetime import date
import hashlib
import re


def _briefing_pattern():
    distribution = r'(?:(?:暨|及|与|和)(?:\d{4}年?(?:年度)?)?(?:现金分红|分红|利润分配)(?:预案|方案|政策)?)?'
    return r'业绩' + distribution + r'(?:网上|线上|网络|电话)?说明会'


def _period_pattern():
    labels = {"半年度": "H1", "中期": "H1", "半年报": "H1", "中报": "H1", "上半年": "H1",
              "前三季度": "Q3", "前三季": "Q3", "年度": "FY", "年报": "FY"}
    for index, numeral in enumerate("一二三四", 1):
        for label in (f"第{numeral}季度", f"{numeral}季度", f"{numeral}季报", f"第{numeral}季", f"{numeral}季",
                      f"第{index}季度", f"{index}季度", f"{index}季报", f"Q{index}"):
            labels[label] = f"Q{index}"
    alternatives = "|".join(sorted(labels, key=len, reverse=True))
    description = r'(?:的)?(?:报告|经营成果|情况|' + _briefing_pattern() + '|业绩)'
    pattern = (rf"(\d{{4}})年?({alternatives})((?:(?:{description})?[，,]?"
               rf"(?:以及|暨|及|和|与|、|/|\+)(?:\d{{4}}年?)?(?:{alternatives}))*)")
    return pattern, alternatives, labels


def source_period(text):
    """Normalize literal period mentions; current-purpose readers bind captures."""
    pattern, alternatives, labels = _period_pattern()
    found = []
    compact = re.sub(r"\s+", "", text or "")
    for match in re.finditer(pattern, compact):
        if re.match(r"战略|规划|计划|目标|发展规划|投资策略", compact[match.end():]):
            continue
        year, first, joined = match.groups()
        found.append(year + "-" + labels[first])
        for explicit_year, label in re.findall(rf"(?:暨|及|和|与|、|/|\+)(?:(\d{{4}})年?)?({alternatives})", joined):
            year = explicit_year or year
            found.append(year + "-" + labels[label])
    return "+".join(dict.fromkeys(found)) if found else None


def _period_value(match):
    _, alternatives, labels = _period_pattern()
    year, first, joined = match.groups()[:3]
    found = [year + '-' + labels[first]]
    joined = re.sub(_briefing_pattern(), '', joined)
    for explicit_year, label in re.findall(rf"(?:暨|及|和|与|、|/|\+)(?:(\d{{4}})年?)?({alternatives})", joined):
        year = explicit_year or year
        found.append(year + '-' + labels[label])
    return '+'.join(dict.fromkeys(found))


def is_update_title(title):
    return bool(re.search(r'变更|调整|延期|更正|补充|取消|推迟|延后|暂停|终止|顺延', title or ''))


def source_heading_period(text):
    pattern, _, labels = _period_pattern()
    compact = re.sub(r"\s+", "", text or "")
    def declared_in_heading(value):
        activity = r'(?:' + _briefing_pattern() + r'|(?:上市公司)?集体接待日)'
        matches = re.finditer(pattern + r"(?:报告|的|集体|网上|线上|网络|电话|投资者|经营)*" + activity, value)
        periods = [_period_value(match) for match in matches]
        return '+'.join(dict.fromkeys(period for value in periods if value for period in value.split('+'))) or None
    declared = declared_in_heading(compact)
    if declared:
        return declared
    alternatives = '|'.join(sorted((label for label, period in labels.items() if period == 'Q3'), key=len, reverse=True))
    def bind_region(match):
        return match[1] + match[3] if re.search(r"辖区|地区|上市公司", match[2]) else match[0]
    bound = re.sub(rf"(\d{{4}}年)([^\d。；;！？!?]{{1,24}}?)({alternatives})", bind_region,
                   compact)
    return declared_in_heading(bound)


def is_quarterly_briefing(title):
    return bool(any(period.endswith('-Q3') for period in (source_heading_period(title) or '').split('+'))
                and re.search(_briefing_pattern(), title or ''))


def source_current_period(title, pages):
    """Read a declared current purpose, never an arbitrary historical body mention."""
    declared = source_heading_period(title)
    if declared:
        return declared
    heading = []
    first_text_page = next((page for page in pages if page.strip()), '')
    for line in first_text_page.splitlines()[:24]:
        line = re.sub(r"\s+", "", line)
        if re.match(r"(?:本公司|本行|本公告|重要内容提示|[一二三四五六七八九十]+、)", line):
            break
        heading.append(line)
        candidate = "".join(heading)
        if len(candidate) > 700:
            break
        if re.search(_briefing_pattern()+r"[^。；;！？!?]*?(?:公告|通知)$", candidate):
            declared = source_heading_period(candidate)
            if declared:
                return declared
            break
    pattern, _, _ = _period_pattern()
    name = pattern + r"(?:报告|网上|线上|网络|投资者|的)*"+_briefing_pattern()
    current = []
    for sentence in re.split(r"[。；;！？!?]", re.sub(r"\s+", "", "\n".join(pages))):
        for plan in re.finditer(r"(?:计划|拟|定|将)(?:于|在)?[^。；;]{0,120}?(?:召开|举行|举办)", sentence):
            if re.search(r"(?:曾|原|此前|当时|过去|曾经).{0,4}$", sentence[:plan.start()]):
                continue
            meeting = re.search(name, sentence[plan.end():].split("，", 1)[0])
            if meeting:
                current.append(_period_value(meeting))
        for meeting in re.finditer(name, sentence):
            if re.match(r"(?:现)?(?:计划|拟|定|将)(?:于|在)", sentence[meeting.end():]) and not re.search(
                    r"(?:曾|此前|当时|过去|往期)", sentence[:meeting.start()]):
                current.append(_period_value(meeting))
        if re.search(r"本次(?:业绩|投资者)?说明会|本次活动|届时", sentence):
            purpose = re.search(r"(?:将(?:在线)?(?:就|针对|介绍|围绕)|公司将针对)(.*)", sentence)
            if purpose and not re.search(r"历史|往期|此前|曾", purpose.group(1)):
                financial = pattern + r"(?:的)?(?:报告|经营成果|财务|业绩|经营情况|经营状况|生产经营|情况)"
                purpose_text = re.split(r"对比|比较|对照", purpose.group(1), maxsplit=1)[0]
                current.extend(_period_value(match) for match in re.finditer(financial, purpose_text))
    return '+'.join(dict.fromkeys(period for value in current if value for period in value.split('+'))) or None


def period_matches(value, target):
    return not target or target in (value or "").split("+")


def mentions_period_family(text, target):
    if not target:
        return False
    family = target.rsplit('-', 1)[-1]
    _, _, labels = _period_pattern()
    aliases = '|'.join(sorted((label for label, value in labels.items() if value == family), key=len, reverse=True))
    return bool(aliases and re.search(aliases, re.sub(r'\s+', '', text or ''), re.I))


def title_outside_scope(title, target):
    if not target:
        return False
    period = source_heading_period(title)
    _, alternatives, labels = _period_pattern()
    family_text = re.sub(r'\s+', '', title or '')
    target_family = target.rsplit('-', 1)[-1]
    all_families = {labels[match.group().upper() if match.group().lower().startswith('q') else match.group()]
                    for match in re.finditer(alternatives, family_text, re.I)}
    bound_labels = '|'.join(sorted((label for label in labels if label != '中期'), key=len, reverse=True))
    family_phrase = (rf'((?:{bound_labels})(?:(?:暨|及|和|与|、|/|\+)(?:\d{{4}}年?)?'
                     rf'(?:{bound_labels}))*)(?:报告|报告期|集体|网上|线上|网络|投资者)*' + _briefing_pattern())
    families = set()
    for phrase in re.finditer(family_phrase, family_text, re.I):
        families.update(labels[match.group().upper() if match.group().lower().startswith('q') else match.group()]
                        for match in re.finditer(bound_labels, phrase[1], re.I))
    if period:
        declared_families = {value.rsplit('-', 1)[-1] for value in period.split('+')}
        if target_family in all_families and target_family not in declared_families:
            return False
        return not period_matches(period, target)
    return bool(families and target_family not in all_families)


_SOURCE_DATE = re.compile(r'(?:(\d{4})年)?(\d{1,2})月(?:(\d{1,2})日)?'
                          r'|(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)')


def _date_token(text, offset):
    match = _SOURCE_DATE.match(text, offset)
    if not match:
        return None
    year, month, day, iso_year, iso_month, iso_day = match.groups()
    year, month, day = year or iso_year, month or iso_month, day or iso_day
    year, month, day = int(year) if year else None, int(month), int(day) if day else None
    if day is None:
        return None
    if day is None and match.end() < len(text) and text[match.end()].isdigit():
        return None
    try:
        date(year if year is not None else 2000, month, day or 1)
    except ValueError:
        return None
    suffix = re.sub(r'^[（(](?:星期|周)[一二三四五六日天][）)]', '', text[match.end():])
    if re.match(r'(?:至|到|和|及|或|、|起|后|前|的|以内|以外|左右|开始|持续|为期|[-—－~～/])', suffix):
        return None
    clock = r'\d{1,2}(?:[:：]\d{1,2}|时(?:\d{1,2}分)?)'
    first_clock = re.match(r'(?:上午|下午|中午|晚上|晚间|早上)?' + clock, suffix)
    if first_clock:
        connection = re.match(r'(?:至|到|[-—－~～])', suffix[first_clock.end():])
        if connection and not re.match(clock, suffix[first_clock.end() + connection.end():]):
            return None
    if re.match(r'(?:至|到|和|及|、|[-—－~～/])(?:(?:\d{4}年)?\d{1,2}(?:月(?:\d{1,2}日)?|日)|\d{4}[-/.]\d{1,2}[-/.]\d{1,2})', text[match.end():]):
        return None
    return {'year': year, 'month': month, 'day': day, 'end': match.end()}


def source_date_outside_window(title, pages, start, end):
    """Prove exclusion from a single current meeting day with physical source text.

    An absent year stays unknown. Its month can exclude a window only when
    that month cannot occur anywhere in the requested interval.
    """
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
    except (ValueError, TypeError):
        return None
    heading = re.sub(r'\s+', '', title or '')
    if (first > last or not re.search(r'(?:召开|举行|举办|参加).*' + _briefing_pattern(), heading)
            or re.search(r'变更|延期|取消|补充|更正|调整|推迟|延后|暂停|终止|召开情况|举行情况|记录|纪要|说明会.{0,8}情况', heading)):
        return None
    full_text = re.sub(r'\s+', '', '\n'.join(pages))
    relative_date = r'次年(?!度)|次[日月周]|翌[日年月]|(?<!未)来[年月]|明[日年月天]|下(?:个|一)?[日月年周]'
    duration = r'(?:持续|延续)(?:至|到|[一二三四五六七八九十半\d]+[日天周月年])|为期|\d{1,2}(?:日|月)(?:起|开始)'
    if re.search(r'原定|原计划|原安排|原会议|原活动|此前|往期|历史会议|曾于|曾经|当时|上次|前次|延期|改期|更正|改为|改至|改到|(?:时间|日期).{0,8}调整|调整.{0,8}(?:时间|日期)|日期待定|时间待定|另行通知|第[一二三四五六七八九十\d]+场|' + relative_date + '|' + duration, full_text):
        return None
    span = (last.year - first.year) * 12 + last.month - first.month
    window_months = set(range(1, 13)) if span >= 11 else {(first.month - 1 + offset) % 12 + 1 for offset in range(span + 1)}
    # A date exclusion must not ignore a second, potentially relevant date.
    source_months = {int(match[1]) for match in re.finditer(r'(?<!\d)(\d{1,2})月', full_text)}
    source_months.update(int(match[1]) for match in re.finditer(
        r'(?<!\d)(0?[1-9]|1[012])[-/.](?:0?[1-9]|[12]\d|3[01])(?!\d)', full_text))
    chinese_months = {name: month for month, name in enumerate(
        ('一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '十一', '十二'), 1)}
    source_months.update(chinese_months[match[1]] for match in re.finditer(
        r'(?<![一二三四五六七八九十])(十二|十一|十|[一二三四五六七八九])月', full_text))
    if source_months & window_months or re.search(r'农历|阴历', full_text):
        return None
    candidates = []
    uncertain = False
    labels = (r'(?:会议召开日期和时间|会议召开日期|会议召开时间|会议时间|活动日期|活动时间|'
              r'(?:业绩(?:网上|线上|网络|电话)?)?说明会(?:召开|举办)?(?:时间|日期)|召开时间)[:：为]')
    plans = r'(?:公司|本行|本次活动|活动|本次(?:业绩)?说明会)(?:现)?(?:计划|拟|定|将)(?:于|在)'
    for page_number, page in enumerate(pages, 1):
        indices = [index for index, char in enumerate(page) if not char.isspace()]
        text = ''.join(page[index] for index in indices)

        def keep(token, left, right):
            candidates.append({**token, 'page': page_number,
                               'quote': page[indices[left]:indices[right - 1] + 1],
                               'page_text_sha256': hashlib.sha256(page.encode()).hexdigest()})

        for anchor in re.finditer(labels, text):
            prefix = text[max(0, anchor.start() - 10):anchor.start()]
            if re.search(r'披露|发布|报名|征集|提问|预约|登记', prefix):
                continue
            if re.search(r'原|旧|此前|往期|上次|前次|历史|过去|股东会|股东大会|董事会|监事会', prefix):
                uncertain = True
                continue
            offset = anchor.end()
            prefix_date = re.match(r'(?:为|于|定于|将于|拟于|计划于)?', text[offset:])
            offset += prefix_date.end()
            token = _date_token(text, offset)
            if token is None:
                uncertain = True
                continue
            keep(token, anchor.start(), token['end'])
        for anchor in re.finditer(plans, text):
            token = _date_token(text, anchor.end())
            if token is None:
                if _SOURCE_DATE.match(text, anchor.end()):
                    uncertain = True
                continue
            tail = re.split(r'[。；;！？!?]', text[token['end']:], maxsplit=1)[0][:220]
            action = re.search(r'召开|举行|举办|参加', tail)
            meeting = re.search(_briefing_pattern(), tail[action.end():]) if action else None
            if not action or not meeting:
                continue
            span_end = token['end'] + action.end() + meeting.end()
            bridge = text[token['end']:span_end]
            if re.search(r'披露|发布|报名|征集|提问|截止|股东大会|股东会|董事会会议|监事会会议|其他活动', bridge) or _SOURCE_DATE.search(bridge):
                uncertain = True
                continue
            keep(token, anchor.start(), span_end)
    if uncertain or not candidates:
        return None
    if len({(value['month'], value['day']) for value in candidates}) != 1:
        return None
    explicit_years = {value['year'] for value in candidates if value['year'] is not None}
    if len(explicit_years) > 1:
        return None
    chosen = next((value for value in candidates if value['year'] is not None), candidates[0])
    year, month, day = chosen['year'], chosen['month'], chosen['day']
    meeting_date = date(year, month, day).isoformat() if year and day else None
    if year:
        outside = not first <= date(year, month, day) <= last
        basis = 'explicit_meeting_date'
    else:
        span = (last.year - first.year) * 12 + last.month - first.month
        months = set(range(1, 13)) if span >= 11 else {(first.month - 1 + offset) % 12 + 1 for offset in range(span + 1)}
        outside = month not in months
        basis = 'month_without_year_outside_window'
    if not outside:
        return None
    return {'basis': basis, 'page': chosen['page'], 'physical_page': chosen['page'],
            'quote': chosen['quote'], 'page_text_sha256': chosen['page_text_sha256'],
            'meeting_date': meeting_date, 'meeting_year': year, 'meeting_month': month,
            'meeting_day': day, 'year_inferred': False, 'window_start': start, 'window_end': end}


def scoped_issues(state, issues, target):
    filtered = []
    for issue in issues:
        notice = state.get("notices", {}).get(str(issue.get("source_id")), {})
        event = state.get("events", {}).get(issue.get("event_id"), {})
        period = notice.get("extraction", {}).get("report_period") or event.get("report_period")
        if not period or period_matches(period, target):
            filtered.append(issue)
    return filtered


def meeting_window(event, scope):
    start, end = scope.get("meeting_start"), scope.get("meeting_end")
    if not start or not end:
        return "within"
    day = event.get("meeting_date")
    if day and start <= day <= end:
        return "within"
    was_within = any(start <= str(item.get("before", {}).get("meeting_date") or "") <= end
                     for item in event.get("history", []))
    if was_within:
        return "moved_out" if day else "within"
    return "outside"
