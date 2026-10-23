"""Run learner unit tests with the public guard installed before discovery."""
from .offline_guard import install
install()

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', type=Path, default=Path.cwd())
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    project = args.project.resolve()
    output = (args.output or project / 'tests/output/local-checks').resolve()
    if not output.is_relative_to(project):
        parser.error('--output must be inside the current project')
    output.mkdir(parents=True, exist_ok=True)
    temporary = output / 'tmp'
    temporary.mkdir(exist_ok=True)
    os.environ['TMPDIR'] = str(temporary)
    os.environ['TEMP'] = str(temporary)
    os.environ['TMP'] = str(temporary)
    tempfile.tempdir = str(temporary)
    tests = project / 'tests'
    if not (tests / '__init__.py').is_file():
        parser.error('create tests/__init__.py before running local checks')
    sys.path.insert(0, str(project))
    suite = unittest.defaultTestLoader.discover(str(tests), top_level_dir=str(project))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    receipt = {'ok': result.wasSuccessful(), 'tests': result.testsRun,
               'failures': len(result.failures), 'errors': len(result.errors),
               'guard_installed_before_discovery': True,
               'temporary_directory': str(temporary),
               'network_guard': 'process-level, inherited by Python workers; not an OS sandbox'}
    (output / 'summary.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
