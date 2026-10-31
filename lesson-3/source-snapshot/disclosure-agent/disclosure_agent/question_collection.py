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


def question_action(prefix, suffix):
    if re.search(r'(?:提问预征集|问题征集|提问)(?:时间|时段|期间|安排)?(?:为|自|从|于|：|:)?$',prefix):
        return True
    if '报名' in prefix:
        return False
    first=suffix.split('，',1)[0]
    if re.search(r'(?:完成|进行|提交|办理|参加|接受|在线)预?报名|报名(?:时间|期间|截止)',first):
        return False
    local='，'.join(suffix.split('，',2)[:2])
    return bool(re.search(r'(?:登录|登陆|点击|进入|访问|通过|使用|选择).{0,160}(?:提问预征集|问题征集)',local)
                or re.search(r'(?:征集|收集|提交|提出|发送|提供|填写).{0,12}(?:问题|提问)',local)
                or re.search(r'(?:问题|提问).{0,30}(?:发送|提交|提供)',local)
                or re.search(r'(?:前|期间|内)(?:可|进行|向公司|向本公司|在线){0,4}提问',local))


def question_collection_range(event, notices, sources):
    if (not event.get('question_deadline_date') or event.get('status') != 'scheduled'
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
            left = max(text.rfind('。', 0, match.start()), text.rfind('；', 0, match.start())) + 1
            right = re.search(r'[。；]', text[match.end():])
            finish = match.end() + right.start() if right else min(len(text), match.end() + 160)
            context=text[left:finish]
            anchored=any(match.start() < end and match.end() > start for start, end in anchors)
            verified_question=anchored and event_deadline_label(event, notices)=='提问截止' and re.search(r'提问|问题征集|征集.{0,20}问题',context)
            prefix=text[left:match.start()]
            explicit_question=re.search(r'提问预征集|问题征集',context)
            if not question_action(prefix,text[match.end():finish]) or not (verified_question or explicit_question):
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
                          'context_quote':original[offsets[left]:offsets[finish-1]+1],
                          'quote': original[offsets[match.start()]:offsets[match.end()-1]+1]})
    return found[0] if found and len({item['text'] for item in found}) == 1 else None
