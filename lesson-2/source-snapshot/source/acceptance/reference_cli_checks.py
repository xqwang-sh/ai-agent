"""Exercise the production reference CLI branch through the frozen worker."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import zipfile

from .fixtures import income_envelope, write_pdf
from .services import run_with_services
from .structured_fixtures import (STRUCTURED_THSCODE, structured_reference,
                                  structured_scenario, structured_source_case)


# This executable is an independent transport fixture, never an application parser.
# Its command grammar catches confusing a schema ID with executable CLI tokens.
_FIXTURE_CLI = r'''
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

root = Path(__file__).resolve().parent
calls = root / 'calls'
calls.mkdir(exist_ok=True)
receipt_path = calls / (str(time.time_ns()) + '-' + uuid.uuid4().hex + '.json')
receipt = {'argv': sys.argv[1:], 'pid': os.getpid(), 'ppid': os.getppid(),
           'python_executable': sys.executable, 'kind': 'invalid', 'ok': False}
def save():
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
save()
try:
    tokens = sys.argv[1:]
    parser = argparse.ArgumentParser(allow_abbrev=False)
    if tokens[:2] == ['schema', 'financials.income']:
        parser.add_argument('--format', required=True, choices=['json'])
        parser.parse_args(tokens[2:])
        receipt.update(kind='schema', ok=True)
        save()
        print(json.dumps({'ok': True, 'command': 'schema',
              'data': {'id': 'financials.income', 'command': ['financials', 'income'],
                       'options': [
                           {'flags': '--thscode <code>', 'description': 'single A-share thscode',
                            'type': 'string', 'required': True},
                           {'flags': '--period <period>', 'description': 'financial period',
                            'type': 'string', 'choices': ['annual', 'quarterly'],
                            'defaultValue': 'annual'},
                           {'flags': '--limit <number>', 'description': 'recent report count (1-20)',
                            'type': 'integer'},
                           {'flags': '--start-ms <milliseconds>', 'description': 'range start in milliseconds',
                            'type': 'integer', 'queryName': 'start'},
                           {'flags': '--end-ms <milliseconds>', 'description': 'range end in milliseconds',
                            'type': 'integer', 'queryName': 'end'},
                           {'flags': '--output <path>',
                            'description': 'write the full JSON response envelope to a file',
                            'type': 'string'}],
                       'paging': 'none', 'window': 'ten-years'},
              'meta': {'requestId': 'synthetic-schema', 'truncated': False,
                       'schemaVersion': '1'}}))
    elif tokens[:2] == ['financials', 'income']:
        parser.add_argument('--thscode', required=True)
        parser.add_argument('--period', required=True, choices=['quarterly'])
        parser.add_argument('--limit', required=True, type=int, choices=[8])
        parser.add_argument('--format', required=True, choices=['json'])
        parser.add_argument('--output')
        args = parser.parse_args(tokens[2:])
        expected = json.loads((root / 'expected.json').read_text())
        if args.thscode != expected['thscode']:
            raise ValueError('wrong synthetic thscode')
        raw = (root / 'income-envelope.json').read_bytes()
        response_path = calls / (receipt_path.stem + '-response.json')
        response_path.write_bytes(raw)
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(raw)
        receipt.update(kind='income', ok=True, thscode=args.thscode,
                       period=args.period, limit=args.limit, format=args.format,
                       output=args.output, response_path=str(response_path),
                       response_sha256=hashlib.sha256(raw).hexdigest())
        save()
        sys.stdout.buffer.write(raw)
    else:
        raise ValueError('expected financials income; financials.income is a schema ID only')
except BaseException as error:
    receipt['error'] = str(error)
    save()
    raise
'''


def _load(path):
    return json.loads(Path(path).read_text())


class ReferenceCliChecks:
    """Uses only the existing Subject.run and independent loopback model service."""

    def test_06_reference_cli_transport(self):
        self.output.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix='reference-cli-', dir=self.output))
        transport = folder / 'transport'
        transport.mkdir()
        executable = transport / 'fixture-hithink'
        source = '#!' + sys.executable + '\n' + _FIXTURE_CLI
        compile(source, str(executable), 'exec')
        executable.write_text(source)
        executable.chmod(0o700)
        self.assertEqual(executable.stat().st_mode & 0o777, 0o700)
        envelope = income_envelope(structured_reference())
        raw = (json.dumps(envelope, ensure_ascii=False, indent=2) + '\n').encode()
        (transport / 'income-envelope.json').write_bytes(raw)
        (transport / 'expected.json').write_text(
            json.dumps({'thscode': STRUCTURED_THSCODE}) + '\n')
        pages, _ = structured_source_case()
        pdf = folder / 'structured-synthetic.pdf'
        write_pdf(pdf, texts=tuple(page['text'] for page in pages))
        scenario = structured_scenario(pdf)
        scenario['reference_cli'] = str(executable.resolve())
        scenario['reference_script'] = []  # Any fallback HTTP reference call fails.
        result, services = run_with_services(self.subject, scenario, folder / 'run')

        # Inspect independent receipts even if the application stopped at the CLI.
        receipt_files = sorted((transport / 'calls').glob('*.json'))
        receipts = [_load(path) for path in receipt_files
                    if not path.name.endswith('-response.json')]
        self.assertTrue(receipts, 'the real frozen worker must execute the reference CLI')
        self.assertTrue(all(item.get('ok') is True for item in receipts), receipts)
        self.assertTrue(all(item['kind'] in ('schema', 'income') for item in receipts), receipts)
        incomes = [item for item in receipts if item['kind'] == 'income']
        self.assertEqual(len(incomes), 1, receipts)
        call = incomes[0]
        self.assertEqual(call['argv'][:2], ['financials', 'income'])
        self.assertEqual(call['thscode'], STRUCTURED_THSCODE)
        self.assertEqual((call['period'], call['limit'], call['format']),
                         ('quarterly', 8, 'json'))
        self.assertEqual(Path(call['response_path']).read_bytes(), raw)
        self.assertEqual(call['response_sha256'], hashlib.sha256(raw).hexdigest())
        execution = _load(result['execution_file'])
        self.assertEqual(call['ppid'], execution['pid'],
                         'CLI acquisition must happen in the genuine frozen worker')
        self.assertNotEqual(call['pid'], execution['pid'])
        self.assertEqual(Path(call['python_executable']).resolve(), Path(sys.executable).resolve())
        self.assertEqual(services['reference_receipts'], [])
        self.assertEqual(services['errors'], [])
        self.assertEqual([item['expected_stage'] for item in services['model_receipts']],
                         ['locate', 'extract', 'vision'])
        state = _load(result['state_file'])
        self.assertEqual(state['status'], 'candidate_ready', state)
        self.assertTrue(state['review'], state)
        for gate in ('internal', 'external'):
            proof = state['current'][gate]
            self.assertTrue(proof['passed'], proof)
            self.assertEqual((proof['matched'], proof['total']), (10, 10))
            self.assertEqual(proof['candidate_id'], state['current']['candidate_id'])
        trace = _load(result['trace_file'])
        self.assertEqual([item['stage'] for item in trace['requests']],
                         ['locate', 'extract', 'vision'])
        evaluations = trace['external_evaluations']
        self.assertEqual(len(evaluations), 1)
        reference_path = Path(evaluations[0]['reference_path'])
        self.assertEqual(reference_path.read_bytes(), raw,
                         'retain the full raw CLI envelope including metadata')
        self.assertEqual(_load(reference_path), envelope)
        raw_sha = hashlib.sha256(raw).hexdigest()
        self.assertEqual(evaluations[0]['reference_sha256'], raw_sha)
        with zipfile.ZipFile(result['sealed_archive']) as archive:
            names = archive.namelist()
            self.assertEqual(len(names), len(set(names)))
            embedded = [name for name in names if not name.endswith('/')
                        and hashlib.sha256(archive.read(name)).hexdigest() == raw_sha]
            self.assertTrue(embedded, 'seal the actual full CLI response bytes')
            self.assertEqual(json.loads(archive.read(embedded[0])), envelope)
