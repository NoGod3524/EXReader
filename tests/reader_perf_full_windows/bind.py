#!/usr/bin/env python3
"""Bind the observed executable to this run's full production ZIP."""
import hashlib
import json
import os
from pathlib import Path

root = Path('build/c09')
report = json.loads((root / 'report.json').read_text())
manifest = json.loads((root / 'package/build.json').read_text())
summary = json.loads(Path('build/full-perf-windows/summary.json').read_text())
exe = root / 'unzipped/EXReader/EXReader.exe'
archive = root / 'EXReader-wave3-windows.zip'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
source, run, attempt = (os.environ[key] for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
assert report['accepted'] is True and not report['failures'] and report['cloud_content_bound'] is True
assert report['source_sha'] == manifest['source_sha'] == summary['source_sha'] == source
assert str(report['run_id']) == str(summary['run_id']) == run
assert str(report['attempt']) == str(summary['attempt']) == attempt
assert sha(exe) == report['program_sha256'] == manifest['files']['EXReader.exe'] == summary['environment']['artifacts']['exe_sha256']
assert sha(archive) == report['zip']['sha256'] and archive.stat().st_size == report['zip']['bytes']
cache = (root / 'wave3-host/CMakeCache.txt').read_text(errors='replace')
assert 'EXR_READER_WINDOWS_WAVE3:BOOL=ON' in cache and 'EXR_READER_WINDOWS_CLOUD_CONTENT_BOUND:BOOL=ON' in cache
assert summary['performance_accepted'] is False and summary['frame_time']['measured'] is False
result = {'source_sha': source, 'run_id': run, 'attempt': attempt, 'program_sha256': sha(exe),
          'zip_sha256': sha(archive), 'zip_bytes': archive.stat().st_size,
          'full_config': 'C09 wave3, cloud content bound', 'performance_accepted': False,
          'frame_time_measured': False, 'physical_device_execution': False}
Path('build/full-perf-windows/full-package-identity.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
