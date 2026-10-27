"""Exercise staged prompt generation and actual feedback-request checks."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'source'))
from acceptance.runtime_prompts import PROMPT_STEPS, check_runtime_prompts, check_feedback_requests


class RuntimePromptChecks(unittest.TestCase):
    def setUp(self):
        output = ROOT / 'qa/runtime-prompt-checks'
        output.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=output)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'project'
        self.root.mkdir()

    def write_prompt(self, name, text=None):
        path = self.root / 'prompts/runtime' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text if text is not None else 'Generated prompt: ' + name + '\n', encoding='utf-8')
        return path

    def test_initial_steps_need_no_prompt_files(self):
        for step in range(5):
            self.assertEqual(check_runtime_prompts(self.root, step)['required'], [])
        self.assertFalse((self.root / 'prompts').exists())

    def test_files_become_required_at_their_step(self):
        for step in (5, 6, 7):
            with self.assertRaises(ValueError):
                check_runtime_prompts(self.root, step)
            for name, due in PROMPT_STEPS.items():
                if due == step:
                    self.write_prompt(name)
            result = check_runtime_prompts(self.root, step)
            self.assertEqual(len(result['required']), {5: 2, 6: 3, 7: 4}[step])
            self.assertTrue(all(len(item['sha256']) == 64 for item in result['required']))
        self.assertEqual(len(check_runtime_prompts(self.root, 8)['required']), 4)
        self.assertEqual(check_runtime_prompts(self.root, 3)['required'], [])

    def test_one_missing_step5_file_fails(self):
        self.write_prompt('locate.md')
        with self.assertRaisesRegex(ValueError, 'extract.md'):
            check_runtime_prompts(self.root, 5)

    def test_empty_and_non_utf8_prompts_fail(self):
        path = self.write_prompt('locate.md', ' \n\t')
        self.write_prompt('extract.md')
        with self.assertRaisesRegex(ValueError, 'empty'):
            check_runtime_prompts(self.root, 5)
        path.write_bytes(b'\xff\xfe')
        with self.assertRaisesRegex(ValueError, 'UTF-8'):
            check_runtime_prompts(self.root, 5)

    def test_symlink_prompt_fails(self):
        target = self.root / 'other.md'
        target.write_text('ordinary text')
        path = self.write_prompt('locate.md')
        path.unlink()
        path.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'ordinary file'):
            check_runtime_prompts(self.root, 5)

    def test_parent_escape_fails(self):
        outside = Path(self.temporary.name) / 'outside'
        outside.mkdir()
        (outside / 'runtime').mkdir()
        (outside / 'runtime/locate.md').write_text('outside content')
        (self.root / 'prompts').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'project-local'):
            check_runtime_prompts(self.root, 5)

    def test_feedback_is_not_required_without_continuation(self):
        check_feedback_requests(self.root, [], 0)

    def test_feedback_must_reach_real_continuation_messages(self):
        self.write_prompt('feedback.md', 'generated feedback instructions\n')
        initial = [{'role': 'system', 'content': 'base stage instructions'},
                   {'role': 'user', 'content': 'start'}]
        with self.assertRaises(ValueError):
            check_feedback_requests(self.root, [initial], 1)
        bad = initial + [{'role': 'assistant', 'content': '{}'}, {'role': 'user', 'content': 'retry'}]
        with self.assertRaises(ValueError):
            check_feedback_requests(self.root, [bad], 1)
        echo_only = initial + [{'role': 'assistant', 'content': 'generated feedback instructions\n'},
                               {'role': 'user', 'content': 'retry'}]
        with self.assertRaises(ValueError):
            check_feedback_requests(self.root, [echo_only], 1)
        good = initial + [{'role': 'assistant', 'content': '{}'},
                          {'role': 'user', 'content': [{'type': 'text', 'text': 'generated feedback instructions\nfailed rules'}]}]
        check_feedback_requests(self.root, [good], 1)
        with self.assertRaises(ValueError):
            check_feedback_requests(self.root, [good], 2)
        check_feedback_requests(self.root, [good, good], 2)
        with self.assertRaises(ValueError):
            check_feedback_requests(self.root, [good, bad], 2)
        with self.assertRaises(ValueError):
            check_feedback_requests(self.root, [good, good, bad], 2)
        encoded = initial + [{'role': 'assistant', 'content': '{}'},
                             {'role': 'user', 'content': json.dumps({'instruction': 'generated feedback instructions\n'})}]
        check_feedback_requests(self.root, [encoded], 1)
        system = [{'role': 'system', 'content': 'generated feedback instructions\n'},
                  {'role': 'user', 'content': 'start'}, {'role': 'assistant', 'content': '{}'},
                  {'role': 'user', 'content': 'failed rules'}]
        check_feedback_requests(self.root, [system], 1)

    def test_json_prompt_body_can_be_used_directly_or_encoded(self):
        prompt = '{"instruction":"Recheck sources"}'
        self.write_prompt('feedback.md', prompt)
        prefix = [{'role': 'system', 'content': 'base'}, {'role': 'assistant', 'content': '{}'}]
        for text in (prompt, json.dumps({'instruction': prompt})):
            check_feedback_requests(self.root, [prefix + [{'role': 'user', 'content': text}]], 1)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RuntimePromptChecks))
    print(json.dumps({'ok': result.wasSuccessful(), 'tests': result.testsRun,
                      'failures': len(result.failures), 'errors': len(result.errors)}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
