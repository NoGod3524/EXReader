"""Actions-only: bind both independent native suites to one program and source."""
import hashlib
import json
import os
from pathlib import Path

assert os.environ.get('GITHUB_ACTIONS') == 'true'
root = Path(__file__).resolve().parents[2]
evidence = root / 'build/windows-font/evidence'
exe = root / 'build/windows-font/host/EXReaderWave3.exe'
digest = hashlib.sha256(exe.read_bytes()).hexdigest()
reports = [json.loads((evidence / name).read_text(encoding='utf-8')) for name in ('report.json', 'txt/report.json')]
assert [len(report['checks']) for report in reports] == [8, 5]
for report in reports:
    assert report['accepted'] is True and not report['problems']
    assert report['source_sha'] == os.environ['GITHUB_SHA']
    assert str(report['run_id']) == os.environ['GITHUB_RUN_ID']
    assert str(report['attempt']) == os.environ['GITHUB_RUN_ATTEMPT']
    assert report['program_sha256'] == digest
    assert report['checks'] and all(row['passed'] is True for row in report['checks'])
result = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
          'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'program_sha256': digest,
          'checks': [{'name': 'one-source-one-native-host-both-font-suites', 'passed': True}],
          'case_counts': [len(report['checks']) for report in reports]}
(evidence / 'same-source.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result), flush=True)
