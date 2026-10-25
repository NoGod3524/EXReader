#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""S10 desktop: a real file enters the desktop (drop/paste) entry and comes back.

The payload is the exact text/uri-list framing a GTK drop or clipboard read
delivers: one real file URI plus entries the entry must classify and reject.
The consumer then imports through the installed SDK sideload module and exports
the stored original again, so this script can compare it with the file the
"computer" put on the desktop by SHA-256.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--name', default='S10-Transfer.epub')
    args = parser.parse_args()
    binary = args.binary.absolute()
    fixtures, output = args.fixtures.absolute(), args.output.absolute()
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((fixtures / 'manifest.json').read_text())
    name = args.name
    expected = manifest[name]
    source = (fixtures / name).resolve()
    checks = []

    def check(check_id, ok, detail=''):
        checks.append({'id': check_id, 'passed': bool(ok), 'detail': detail})

    check('fixture.manifest-matches-file',
          hashlib.sha256(source.read_bytes()).hexdigest() == expected['sha256'],
          'local fixture bytes')

    working = output / 'entry'
    working.mkdir(exist_ok=True)
    directory = working / 'dropped-folder'
    directory.mkdir(exist_ok=True)
    lines = [
        source.as_uri(),
        directory.as_uri(),
        'mtp://S10Camera/1000000123/' + urllib.parse.quote(name),
        'https://example.invalid/' + urllib.parse.quote(name),
        'file://other-host.invalid/share/' + urllib.parse.quote(name),
    ]
    payload = working / 'payload.uri-list'
    payload.write_text('\r\n'.join(lines) + '\r\n', encoding='utf-8')
    library = working / 'library.sqlite'
    exported = working / ('exported-' + name)
    report_path = working / 'entry-report.json'
    result = subprocess.run([str(binary), '--payload', str(payload), '--library', str(library),
                             '--export', str(exported), '--report', str(report_path),
                             '--title', 'S10 transfer'],
                            capture_output=True, text=True, timeout=600)
    (output / 'entry.log').write_text(result.stdout + result.stderr)
    check('entry.exit-status', result.returncode == 0, 'returncode=' + str(result.returncode))
    entry = json.loads(report_path.read_text()) if report_path.is_file() else {}
    if not entry:
        check('entry.report-written', False, str(report_path))

    items = entry.get('items', [])
    files = [row for row in items if row.get('status') == 1]
    directories = [row for row in items if row.get('status') == 2]
    remote = [row for row in items if row.get('status') == 3]
    remote_host = [row for row in items if row.get('status') == 4]
    virtual = [row for row in items if row.get('status') == 5]
    check('entry.drop-parsed', entry.get('drop_status') == 0, json.dumps(entry.get('drop_status_name')))
    check('entry.real-file-classified',
          len(files) == 1 and Path(files[0].get('path') or '').resolve() == source,
          json.dumps(files, sort_keys=True))
    check('entry.directory-classified-not-recursed', len(directories) == 1,
          json.dumps([row.get('path') for row in directories]))
    check('entry.remote-surface-rejected',
          len(remote) == 1 and len(remote_host) == 1 and len(virtual) == 1,
          json.dumps({'remote': len(remote), 'remote_host': len(remote_host), 'virtual': len(virtual)}))
    check('entry.import-created-book',
          entry.get('import_status') == 0 and entry.get('created') == 1
          and int(entry.get('book_id') or 0) > 0,
          json.dumps({key: entry.get(key) for key in ('import_status', 'book_id', 'created', 'error')}))
    check('sdk.exported-original-bytes',
          entry.get('export_status') == 0 and entry.get('bytes_written') == expected['bytes'],
          json.dumps({key: entry.get(key) for key in ('export_status', 'bytes_written')}))
    exported_sha = hashlib.sha256(exported.read_bytes()).hexdigest() if exported.is_file() else ''
    check('sdk.exported-original-matches-fixture', exported_sha == expected['sha256'],
          'exported sha256 ' + exported_sha)

    problems = [row['id'] + ': ' + row['detail'] for row in checks if not row['passed']]
    report = {
        'schema': 1,
        'package': 'S10',
        'role': 'desktop',
        'platform': 'linux-desktop',
        'source_sha': os.environ.get('GITHUB_SHA', ''),
        'run_id': os.environ.get('GITHUB_RUN_ID', ''),
        'attempt': os.environ.get('GITHUB_RUN_ATTEMPT', ''),
        'fixture': {'name': name, 'sha256': expected['sha256'], 'bytes': expected['bytes']},
        'delivery': {'method': 'local file on the computer dropped as text/uri-list',
                     'payload': str(payload), 'physical_cable_or_server': False},
        'entry': {'module': 'extras/desktop-drop (unchanged public C ABI)',
                  'import': 'extras/sideload exr_sideload_import_file',
                  'export': 'extras/sideload exr_sideload_export_original'},
        'entry_report': entry,
        'checks': checks,
        'problems': problems,
        'accepted': not problems,
        'gui_drop_target_execution': False,
        'physical_device_execution': False,
    }
    (output / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'checks': len(checks), 'problems': problems}, indent=2))
    if problems:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
