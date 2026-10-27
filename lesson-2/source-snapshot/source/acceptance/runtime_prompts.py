"""Check runtime prompts only when their development step is reached."""
import hashlib
import json
from pathlib import Path


PROMPT_STEPS = {'locate.md': 5, 'extract.md': 5, 'vision.md': 6, 'feedback.md': 7}


def read_prompt(project, name):
    root = Path(project).resolve()
    path = root / 'prompts/runtime' / name
    if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError(f'Generate a project-local ordinary file: prompts/runtime/{name}')
    try:
        text = path.read_text(encoding='utf-8')
    except UnicodeError as error:
        raise ValueError(f'Runtime prompt must be UTF-8: {name}') from error
    if not text.strip():
        raise ValueError(f'Runtime prompt must not be empty: {name}')
    return path, text


def check_runtime_prompts(project, through):
    required = []
    for name, step in PROMPT_STEPS.items():
        if step <= through:
            path, _ = read_prompt(project, name)
            required.append({'path': 'prompts/runtime/' + name, 'step': step,
                             'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    return {'ok': True, 'required': required}


def _strings(value):
    if isinstance(value, str):
        yield value
        try:
            parsed = json.loads(value)
        except ValueError:
            return
        else:
            if parsed != value:
                yield from _strings(parsed)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)


def check_feedback_requests(program, request_messages, required_count):
    if len(request_messages) != required_count:
        raise ValueError('Select exactly the actual feedback requests, excluding ordinary tool exchanges')
    if not required_count:
        return
    _, prompt = read_prompt(program, 'feedback.md')
    for messages in request_messages:
        if not any(message.get('role') == 'assistant' for message in messages):
            raise ValueError('Feedback request must retain its model conversation history')
        if not any(prompt in text for message in messages if message.get('role') in ('system', 'developer', 'user', 'tool')
                   for text in _strings(message.get('content'))):
            raise ValueError('Each actual feedback request must include the frozen feedback.md text')
