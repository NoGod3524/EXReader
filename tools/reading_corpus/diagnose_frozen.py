#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only raw-input diagnostic; no SDK, benchmark or acceptance grant."""
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

from collect import fetch, sha, structure


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ValueError('Diagnostic runs only in Actions')
    output = Path('build/raw-input-diagnostic')
    output.mkdir(parents=True, exist_ok=False)
    manifest_path = Path('tools/reading_corpus/real-v1.json')
    frozen = json.loads(manifest_path.read_bytes())
    report = {'diagnostic_only': True, 'accepted': False, 'engine_executed': False,
              'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'run_attempt': os.environ['GITHUB_RUN_ATTEMPT']}
    for name, command in (
        ('protocol', [sys.executable, 'tests/reading_corpus/check_collect.py']),
        ('recovery', [sys.executable, 'tools/reading_corpus/collect.py', 'cached', str(manifest_path), str(output / 'recovered')])
    ):
        with (output / (name + '.log')).open('wb') as log:
            process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=900)
        report[name + '_exit_code'] = process.returncode
        print(json.dumps({name + '_exit_code': process.returncode}), flush=True)
        if name == 'protocol' and process.returncode:
            print((output / (name + '.log')).read_text(), flush=True)
    recovery_path = output / 'recovered/manifest.json'
    if recovery_path.exists():
        recovery = json.loads(recovery_path.read_bytes())
        report['recovery'] = {'complete': recovery['complete'], 'documents': len(recovery['files']),
                              'raw_input_archive': recovery.get('raw_input_archive'),
                              'collection_failures': recovery['collection_failures'],
                              'inputs': [{'id': row['id'], 'size': row['size'], 'sha256': row['sha256'],
                                          'retrieved_url': row['retrieved_url'], 'input_origin': row['input_origin'],
                                          'observed_license_sha256': row['observed_license_sha256'],
                                          'source_structure': row['source_structure']} for row in recovery['files']]}
    entry = next(row for row in frozen['files'] if row['id'] == 'pg84-frankenstein')
    probe = {'id': entry['id'], 'source_url': entry['source_url'],
             'frozen_size': entry['size'], 'frozen_sha256': entry['sha256']}
    try:
        data, final_url = fetch(entry['source_url'], entry['limits']['download_bytes'])
        probe.update(size=len(data), sha256=sha(data), final_url=final_url,
                     matches_frozen_size=len(data) == entry['size'], matches_frozen_sha256=sha(data) == entry['sha256'])
        path = output / 'publisher-pg84.epub'
        path.write_bytes(data)
        with zipfile.ZipFile(path) as archive:
            if archive.read('mimetype').strip() != b'application/epub+zip':
                raise ValueError('EPUB mimetype refused')
        probe['source_structure'] = structure(path, entry)
        probe['valid_epub_structure'] = True
    except Exception as error:
        probe.update(valid_epub_structure=False, error_type=type(error).__name__, error=str(error))
    report['publisher_probe'] = probe
    report['diagnostic_completed'] = (report['protocol_exit_code'] == 0 and report['recovery_exit_code'] == 0 and
                                      report.get('recovery', {}).get('complete') is True and
                                      report['recovery']['documents'] == 8)
    (output / 'summary.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report['diagnostic_completed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
