"""Actions-only replay of an authenticated original GTK host; no acceptance."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile

from final import Bundle, fetch, identity, pages, require


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    run_id = int(sys.argv[1])
    run = fetch('actions/runs/%d' % run_id)
    require(run['path'] == '.github/workflows/reader-hosts-integration.yml',
            'not a shared-host run')
    source, attempt = run['head_sha'], run['run_attempt']
    subprocess.run(['git', 'merge-base', '--is-ancestor', source, 'HEAD'], check=True)
    # Fixtures and actual navigation code must still match the old program.
    # Other host changes are listed as differences, never granted by this run.
    subprocess.run(['git', 'diff', '--exit-code', source, 'HEAD', '--', 'src', 'include', 'cmake',
                    'CMakeLists.txt', 'bindings', 'tests/fixtures', 'apps/reader/navigation',
                    'examples/linux/navigation_backend.inc', 'examples/linux/navigation_ui.inc',
                    'tests/reader_navigation/make_navigation_fixtures.py',
                    'tests/reader_gtk_navigation/make_inputs.py', 'tests/linux_host/generate_fixed.py'], check=True)
    producers = {'GTK G03 G04 reading records and retained native suites': 'reader-gtk-reading-records',
                 'GTK book file drop paste and retained native suites': 'reader-gtk-drop-import'}
    jobs = [j for j in pages('actions/runs/%d/attempts/%d/jobs' % (run_id, attempt), 'jobs')
            if j['name'] in producers]
    require(len(jobs) == 1 and jobs[0]['status'] == 'completed' and jobs[0]['head_sha'] == source,
            'original GTK producer missing')
    names = [a for a in pages('actions/runs/%d/artifacts' % run_id, 'artifacts')
             if a['name'] == '%s-%d-%d' % (producers[jobs[0]['name']], run_id, attempt)]
    require(len(names) == 1 and names[0]['workflow_run']['head_sha'] == source and
            names[0]['workflow_run']['id'] == run_id, 'foreign or duplicate original artifact')
    out = Path('build/navigation-probe');out.mkdir(parents=True, exist_ok=True)
    bundle = Bundle(names[0])
    try:
        original = bundle.report('gtk-navigation-ui/result.json');identity(original, source, run_id, attempt)
        (out / 'original-report.json').write_text(json.dumps(original, indent=2) + '\n')
        # CFI inputs are emitted by the original installed SDK consumer. Copy
        # the authenticated original fixtures, including those captured CFIs.
        fixture_hashes = {};fixture_bytes = 0
        for item in bundle.zip.infolist():
            parts = PurePosixPath(item.filename).parts
            if 'gtk-navigation-fixtures' not in parts or item.is_dir():continue
            relative = PurePosixPath(*parts[parts.index('gtk-navigation-fixtures') + 1:])
            require(relative.parts and str(relative) not in fixture_hashes and len(fixture_hashes) < 200,
                    'duplicate or unbounded original navigation fixtures')
            data = bundle.bytes(item.filename, 32 * 1024**2);fixture_bytes += len(data)
            require(fixture_bytes <= 64 * 1024**2, 'unbounded navigation fixture bytes')
            destination = out / 'fixtures' / str(relative)
            destination.parent.mkdir(parents=True, exist_ok=True);destination.write_bytes(data)
            fixture_hashes[str(relative)] = hashlib.sha256(data).hexdigest()
        require({'surrogate.cfi', 'collapsed.cfi', 'normal.cfi', 'cancel.epub'} <= set(fixture_hashes),
                'actual captured navigation inputs absent')
        payload = out / 'payload';payload.mkdir()
        found, members, unpacked = set(), 0, 0
        info = bundle.info('account-package/EXReader-Linux.tar.gz')
        with bundle.zip.open(info) as stream, tarfile.open(fileobj=stream, mode='r|gz') as archive:
            for entry in archive:
                members += 1;unpacked += entry.size
                require(members <= 10000 and 0 <= entry.size <= 128 * 1024**2 and unpacked <= 512 * 1024**2,
                        'oversized original host package')
                target = next((name for name in ('bin/exreader-linux', 'Reader.otf')
                               if entry.name == name or entry.name.endswith('/' + name)), None)
                if target is None:continue
                require(target not in found and entry.isfile(), 'duplicate or nonregular host member')
                found.add(target)
                data = archive.extractfile(entry).read(entry.size + 1)
                require(len(data) == entry.size, 'truncated original host member')
                path = payload / target;path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(data)
        require(found == {'bin/exreader-linux', 'Reader.otf'}, 'original host binary/font absent')
        binary = payload / 'bin/exreader-linux';binary.chmod(0o755)
        require(hashlib.sha256(binary.read_bytes()).hexdigest() == original['program_sha256'],
                'original navigation program bytes differ')
        record = dict(accepted=False, diagnostic_only=True, program_source_sha=source,
                      program_sha256=original['program_sha256'], original_run=run_id, original_attempt=attempt,
                      test_source_sha=os.environ['GITHUB_SHA'], test_run=os.environ['GITHUB_RUN_ID'],
                      original_fixture_sha256=fixture_hashes,
                      artifact={k: names[0][k] for k in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
        (out / 'input.json').write_text(json.dumps(record, indent=2) + '\n')
        with open(os.environ['GITHUB_ENV'], 'a') as env:
            env.write('NAV_PROBE_PAYLOAD=' + str(payload.resolve()) + '\n')
            env.write('GTK_NAVIGATION_PROGRAM_SOURCE=' + source + '\n')
        print(json.dumps(record), flush=True)
    finally:
        bundle.close()


if __name__ == '__main__':
    main()
