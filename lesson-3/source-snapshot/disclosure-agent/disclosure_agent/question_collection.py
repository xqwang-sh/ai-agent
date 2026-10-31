"""Optional display of an explicit, source-bound question collection range."""
from datetime import date
import re
from .source_text import event_deadline_label

DATE_RANGE = re.compile(
    r'(?:(?P<sy>20\d{2})年)?(?P<sm>\d{1,2})月(?P<sd>\d{1,2})日'
    r'(?:[（(](?:星期|周)[一二三四五六日天][）)])?'
    r'(?P<st>(?:上午|下午|晚上|中午)?\d{1,2}[:：]\d{2})?(?:起|开始)?(?:至|到|—|–|-)'
    r'(?:(?P<ey>20\d{2})年)?(?:(?P<em>\d{1,2})月)?(?P<ed>\d{1,2})日'
    r'(?:[（(](?:星期|周)[一二三四五六日天][）)])?'
    r'(?P<et>(?:上午|下午|晚上|中午)?\d{1,2}[:：]\d{2})?')


def clock(value):
    if not value:
        return None
    match = re.fullmatch(r'(上午|下午|晚上|中午)?(\d{1,2})[:：](\d{2})', value)
    hour, minute = int(match[2]), int(match[3])
    if match[1] in {'下午', '晚上', '中午'} and hour < 12:
        hour += 12
    if match[1] == '上午' and hour == 12:
        hour = 0
    return f'{hour:02}:{minute:02}' if hour < 24 and minute < 60 else None


def question_collection_range(event, notices, sources):
    if (event_deadline_label(event, notices) != '提问截止'
            or not event.get('question_deadline_date') or event.get('status') != 'scheduled'
            or event.get('validity') == 'needs_review'
            or any(key.startswith('question_deadline') for key in event.get('pending_fields', {}))):
        return None
    latest_id = next(reversed(event.get('source_ids', [])), None)
    extraction = notices.get(latest_id, {}).get('extraction', {})
    if (extraction.get('question_deadline_date') != event['question_deadline_date']
            or extraction.get('question_deadline_time') != event.get('question_deadline_time')):
        return None
    evidence = extraction.get('deadline_evidence') or {}
    parts = evidence.get('parts') or [evidence]
    source = next((item for item in sources if item['id'] == latest_id), {})
    found = []
    for excerpt in source.get('participation', []):
        original = excerpt['quote']
        offsets = [i for i, char in enumerate(original) if not char.isspace()]
        text = ''.join(original[i] for i in offsets)
        anchors = []
        for part in parts:
            if part.get('page') != excerpt['page']:
                continue
            quote = re.sub(r'\s+', '', part.get('quote', ''))
            start = text.find(quote) if quote else -1
            if start >= 0:
                anchors.append((start, start + len(quote)))
        for match in DATE_RANGE.finditer(text):
            if not any(match.start() < end and match.end() > start for start, end in anchors):
                continue
            left = max(text.rfind('。', 0, match.start()), text.rfind('；', 0, match.start())) + 1
            right = re.search(r'[。；]', text[match.end():])
            finish = match.end() + right.start() if right else min(len(text), match.end() + 160)
            if not re.search(r'提问|问题征集|征集.{0,20}问题', text[left:finish]):
                continue
            try:
                expected = date.fromisoformat(event['question_deadline_date'])
                end = date(int(match['ey'] or expected.year), int(match['em'] or match['sm']), int(match['ed']))
                start = date(int(match['sy'] or end.year), int(match['sm']), int(match['sd']))
            except ValueError:
                continue
            start_time, end_time = clock(match['st']), clock(match['et'])
            if end != expected or start > end or (match['st'] and not start_time) or (match['et'] and not end_time):
                continue
            if end_time != event.get('question_deadline_time'):
                continue
            if start == end and start_time and end_time and start_time > end_time:
                continue
            label = lambda day: (str(day.year)+'年' if day.year != expected.year else '') + f'{day.month}月{day.day}日'
            display = label(start) + (start_time or '') + '至' + label(end) + (end_time or '')
            found.append({'text': display, 'source_id': latest_id, 'page': excerpt['page'],
                          'quote': original[offsets[match.start()]:offsets[match.end()-1]+1]})
    return found[0] if found and len({item['text'] for item in found}) == 1 else None
