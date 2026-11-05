#!/usr/bin/env python3
"""Check the extracted full GTK package, build flags and measurement identity."""
import hashlib
import json
import os
from pathlib import Path
import sys

sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
payload = Path('build/full-gtk-extracted/EXReader-Linux')
manifest = json.loads(Path('build/c10-package/build.json').read_text())
cache = Path('build/c10-desktop/CMakeCache.txt').read_text()
source = os.environ['GITHUB_SHA']
assert manifest['source_sha'] == source and manifest['sdk_version'] == '3.41.0'
flags = ('EXR_READER_GTK_ACCOUNT', 'EXR_READER_GTK_PREFERENCES', 'EXR_READER_GTK_SEARCH',
         'EXR_READER_GTK_NAVIGATION', 'EXR_READER_GTK_READING_RECORDS', 'EXR_READER_GTK_BATCH_IMPORT',
         'EXR_READER_GTK_DROP_IMPORT', 'EXR_READER_GTK_WAVE3', 'EXR_READER_PAGE_BACKGROUND', 'EXR_READER_BUILD_GTK')
for flag in flags:
    assert flag + ':BOOL=ON' in cache, flag
actual = {str(path.relative_to(payload)): sha(path) for path in payload.rglob('*') if path.is_file()}
assert actual == manifest['files'], 'extracted package differs from manifest'
exe = payload / 'bin/exreader-linux'
archive = Path('build/c10-package/EXReader-Linux.tar.gz')
identity = {'source_sha': source, 'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
            'program_sha256': sha(exe), 'archive_sha256': sha(archive), 'archive_bytes': archive.stat().st_size,
            'config_flags': list(flags), 'frame_time_measured': False, 'performance_accepted': False,
            'physical_device_execution': False}
if '--preflight' in sys.argv:
    path = Path('build/full-gtk-guards/full-package-identity.json')
else:
    prior = json.loads(Path('build/full-gtk-guards/full-package-identity.json').read_text())
    summary = json.loads(Path('build/full-gtk-evidence/summary.json').read_text())
    report = json.loads(Path('build/full-gtk-evidence/report.json').read_text())
    assert prior == identity
    assert summary['source_sha'] == report['source_sha'] == source
    assert str(summary['run_id']) == str(report['run_id']) == os.environ['GITHUB_RUN_ID']
    assert str(summary['attempt']) == str(report['attempt']) == os.environ['GITHUB_RUN_ATTEMPT']
    assert summary['environment']['payload']['binary_sha256'] == identity['program_sha256']
    assert summary['environment']['package']['tarball_sha256'] == identity['archive_sha256']
    assert report['complete_product'] is False and report['grants']['frame_clock_interval'] is False
    assert report['grants']['hard_cpu_or_memory_budget'] is False
    path = Path('build/full-gtk-evidence/full-package-identity.json')
path.write_text(json.dumps(identity, indent=2) + '\n')
print(json.dumps(identity))
