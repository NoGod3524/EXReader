#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only evidence for the separate real Apple import-mapping UI flows."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collect_evidence import command, load_results
from evidence_contract import digest, inventory, require, tree_digest, validate_sdk

CASES = {
    'testFormatsDuplicateUnicodeAndStoredReading': ['fresh-start', 'library.import.epub', 'library.import.pdf',
        'library.import.mapping-text', 'library.import.epub.duplicate', 'library.import.unicode',
        'four-source-mappings', 'stored-original-opens'],
    'testPrepublicationCancellationLeavesNoBookOrCopy': ['fresh-start', 'cancelled-without-publication'],
    'testRecoversAfterProcessTerminationBetweenDatabases': ['fresh-start', 'before-process-termination',
        'restart-and-repair', 'recovered-original-with-one-mapping'],
    'testRecoversAfterProcessTerminationInsideProductTransaction': ['fresh-start', 'before-process-termination',
        'restart-and-repair', 'recovered-original-with-one-mapping'],
}
SCREENSHOTS = {
    'testFormatsDuplicateUnicodeAndStoredReading': ['four-source-mappings', 'stored-original-opens'],
    'testPrepublicationCancellationLeavesNoBookOrCopy': ['cancelled-without-publication'],
    'testRecoversAfterProcessTerminationBetweenDatabases': ['before-process-termination', 'recovered-original-with-one-mapping'],
    'testRecoversAfterProcessTerminationInsideProductTransaction': ['before-process-termination', 'recovered-original-with-one-mapping'],
}


def key(value):
    names = re.findall(r'\btest[A-Za-z0-9_]+\b', value or '')
    require(len(names) == 1 and names[0] in CASES, 'unknown/ambiguous mapping UI case')
    return names[0]


def probe(value):
    parts = [item.split('=', 1) for item in value.split(';')]
    require(all(len(item) == 2 for item in parts) and len({item[0] for item in parts}) == len(parts), 'invalid mapping observation')
    fields = dict(parts)
    require(set(fields) == {'books', 'local', 'epub_chapter', 'reflow_global', 'fixed_page', 'staging', 'keys'}, 'missing mapping observation')
    for name in set(fields) - {'keys'}:
        require(re.fullmatch(r'0|[1-9]\d{0,5}', fields[name]), 'invalid mapping count')
        fields[name] = int(fields[name])
    fields['keys'] = fields['keys'].split('|') if fields['keys'] else []
    require(fields['local'] == fields['epub_chapter'] + fields['reflow_global'] + fields['fixed_page'], 'mode count differs')
    return fields


def validate_steps(owner, payload, fixtures):
    require(key(payload['test']) == owner and [row['id'] for row in payload['steps']] == CASES[owner], 'mapping named steps differ')
    rows = {row['id']: row for row in payload['steps']}
    if owner == 'testFormatsDuplicateUnicodeAndStoredReading':
        state = probe(rows['four-source-mappings']['probe'])
        expected = {'epub:' + fixtures['Sample.epub'], 'epub:' + fixtures['Unicode.epub'],
                    'pdf:' + fixtures['Sample.pdf'], 'txt:' + fixtures['Mapping.txt']}
        require(state['books'] == state['local'] == 4 and state['epub_chapter'] == 2 and
                state['reflow_global'] == state['fixed_page'] == 1 and state['staging'] == 0 and
                set(state['keys']) == expected, 'actual public source keys/modes differ from fixture bytes')
    elif owner == 'testPrepublicationCancellationLeavesNoBookOrCopy':
        state = probe(rows['cancelled-without-publication']['probe'])
        require(state['books'] == state['local'] == state['staging'] == 0 and not state['keys'], 'cancelled import left data')
    else:
        inside = owner.endswith('InsideProductTransaction')
        require(rows['before-process-termination']['status'] == ('登记事务已开始' if inside else '导入已保存，正在登记'), 'actual interruption boundary missing')
        state = probe(rows['recovered-original-with-one-mapping']['probe'])
        require(state['books'] == state['local'] == 1 and state['staging'] == 0 and
                state['fixed_page' if inside else 'epub_chapter'] == 1 and
                state['keys'] == [('pdf:' if inside else 'epub:') + fixtures['Sample.pdf' if inside else 'Sample.epub']],
                'real process restart failed to recover the original mapping')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('platform', 'xcresult', 'output', 'container', 'app', 'fixtures', 'sdk_root', 'sdk_identity', 'destination'):
        parser.add_argument('--' + name.replace('_', '-'), required=True)
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'collect mapping evidence only in GitHub Actions')
    output, result, app = Path(args.output), Path(args.xcresult), Path(args.app)
    output.mkdir(parents=True, exist_ok=False)
    source, run, attempt = (os.environ[name] for name in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    require(command('git', 'rev-parse', 'HEAD') == source, 'mapping checkout source differs')
    sdk = json.loads(Path(args.sdk_identity).read_text())
    validate_sdk(Path(args.sdk_root), sdk, source, run, attempt, 'macos' if args.platform == 'macos' else 'iphonesimulator')
    fixtures = json.loads(Path(args.fixtures).read_text())
    plist = app / ('Contents/Info.plist' if args.platform == 'macos' else 'Info.plist')
    require(plistlib.loads(plist.read_bytes())['EXRSourceSHA'] == source, 'mapping app is from another source')
    cases = load_results(result)
    require(len(cases) == 4 and {key(case['name']) for case in cases} == set(CASES) and
            all(case['result'] == 'Passed' for case in cases), 'mapping UI case failed, skipped or missing')
    attachments = output / 'attachments'
    command('xcrun', 'xcresulttool', 'export', 'attachments', '--path', result, '--output-path', attachments)
    manifest = json.loads((attachments / 'manifest.json').read_text())
    roles, payloads = set(), {}
    for group in manifest:
        owner = key(group.get('testIdentifier') or group.get('testName'))
        for item in group['attachments']:
            filename = item['exportedFileName']
            require(Path(filename).name == filename, 'mapping attachment path refused')
            path = attachments / filename
            require(path.is_file() and 0 < path.stat().st_size <= 16 * 1024 * 1024, 'mapping attachment bytes missing')
            match = re.fullmatch(r'(.+)_(?:0|[1-9]\d*)_[0-9A-Fa-f-]{36}\.(png|json|txt)', item['suggestedHumanReadableName'])
            require(match is not None, 'mapping attachment name changed')
            name, extension = match.groups()
            if name.startswith('mapping-steps-'):
                require(extension == 'json' and owner not in payloads, 'duplicate mapping step JSON')
                payloads[owner] = json.loads(path.read_text())
                validate_steps(owner, payloads[owner], fixtures)
                role = 'steps'
            else:
                require(name.startswith('mapping-') and name[8:] in SCREENSHOTS[owner] and extension == 'png' and
                        path.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n', 'unexpected mapping screenshot')
                role = name[8:]
            require((owner, role) not in roles, 'duplicate mapping attachment role')
            roles.add((owner, role))
    require(set(payloads) == set(CASES) and roles == {(owner, role) for owner in CASES for role in ['steps', *SCREENSHOTS[owner]]}, 'incomplete mapping attachment set')
    container = Path(args.container)
    folder = container if args.platform == 'macos' else container / 'Library/Application Support/EXReader'
    database_records = {}
    for name in ('library.sqlite', 'reader-catalog.db'):
        original, saved = folder / name, output / name
        with sqlite3.connect(original.resolve().as_uri() + '?mode=ro', uri=True) as database:
            with sqlite3.connect(saved) as target:
                database.backup(target)
        database_records[name] = {'sha256': digest(saved), 'bytes': saved.stat().st_size}
    with sqlite3.connect(output / 'reader-catalog.db') as database:
        require(database.execute('PRAGMA application_id').fetchone()[0] == 1163416144 and
                database.execute('PRAGMA integrity_check').fetchone()[0] == 'ok' and not database.execute('PRAGMA foreign_key_check').fetchall(), 'product catalog snapshot integrity differs')
        mappings = database.execute('SELECT b.book_key,b.source_bytes,l.sdk_book_id,l.location_kind FROM reader_books b JOIN reader_local_books l USING(book_key) ORDER BY b.book_key').fetchall()
    shutil.copytree(app, output / 'program/EXReaderHost.app')
    report = {'schema': 1, 'accepted': True, 'source_sha': source, 'run_id': run, 'attempt': attempt,
        'platform': args.platform, 'physical_device_execution': False, 'cases': cases, 'ui_cases': 4,
        'named_steps': 18, 'attachments': 11, 'attachment_files': inventory(attachments), 'databases': database_records,
        'mapping_rows': mappings, 'program_files': inventory(output / 'program'), 'xcresult_sha256': tree_digest(result),
        'fixtures': fixtures, 'sdk': sdk, 'destination': Path(args.destination).read_text(),
        'xcode': command('xcodebuild', '-version'), 'problems': []}
    (output / 'mapping-ui.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({name: report[name] for name in ('accepted', 'source_sha', 'run_id', 'attempt', 'platform', 'ui_cases', 'named_steps', 'attachments', 'mapping_rows', 'problems')}))


if __name__ == '__main__':
    main()
