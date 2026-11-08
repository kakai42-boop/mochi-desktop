"""Fail closed when a native smoke report is absent, stale or incomplete."""
import json
from pathlib import Path
import sys


def verify(report, run_id):
    if not run_id or report.get('run_id') != run_id:
        raise ValueError('Missing or stale smoke-test identity')
    if report.get('platform') != 'win32':
        raise ValueError('The application was not run on Windows')
    if report.get('error'):
        raise ValueError('Native smoke test reported an error')
    for key in ('native_surface', 'audio_plugins'):
        if report.get(key) is not True:
            raise ValueError('Incomplete native check: ' + key)


if __name__ == '__main__':
    verify(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')), sys.argv[2])
