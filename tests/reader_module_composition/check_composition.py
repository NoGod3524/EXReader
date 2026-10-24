# SPDX-License-Identifier: MIT
"""Judge for the installed-prefix module composition (Actions only).

Runs the two installed consumers, the same-source relocated consumer and the
real TLS WebDAV fixture, then decides every item from the produced evidence:
the consumers' own named checks, the server's request journal, the published
byte identity and the final linker map.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from webdav_fixture import WebDAVFixture

# Items that must exist by name: a skipped block cannot pass silently.
REQUIRED_C = [
    'C credentials open a namespace',
    'C preferences save a document',
    'C preferences load their own document',
    'C product revision store opens',
    'C product catalog opens',
    'C library imports the original',
    'C typed book command commits its transaction',
    'C search opens over the document',
    'C search returns the exact literal offset',
    'C reading v2 encodes the capture',
    'C reading revision commits',
    'C product retains exactly one annotation entity',
    'C record decodes from retained bytes',
    'C receiver resolves the retained selector',
    'C WebDAV refuses a non-TLS root',
    'C session refuses an unbounded configuration',
]
REQUIRED_CXX = [
    'installed credentials package validates a namespace',
    'preferences save a device document',
    'preferences reload their own document',
    'installed catalog ships the unchanged schema1 migration',
    'batch enumeration finds exactly the two real documents',
    'batch import commits both documents through sideload',
    'sideload imports a fixed-page original',
    'typed book command commits metadata history and outbox',
    'installed search opens over the public document',
    'search returns the exact byte range of the literal',
    'the search capture is losslessly representable',
    'reading v2 encodes the SDK progress point',
    'reading v2 encodes the search capture',
    'reading v2 annotation commits through the product transaction',
    'the committed annotation selects as a safe head',
    'the decoded record keeps the exact search selector',
    'desktop metadata applies its intent',
    'the metadata intent reaches the product row',
    'sideload exports the exact immutable original',
    'native TLS client accepts the composition root',
    'every queued revision reached the immutable remote store',
    'the verified publication acknowledged the outbox',
    'the receiver adopted every published revision',
    'the receiver downloaded the verified original bytes',
    'the received annotation is a safe head on the second provider',
    'WebDAV preserved the exact retained revision bytes',
    'the second SDK resolves the transported selector exactly',
    'the session finished one complete sweep',
    'the session swept all 256 shards',
    'the session worker reached CLOSED',
]


def archive_providers(map_text):
    """Archives that supplied the SQLite amalgamation object (GNU ld / MSVC / ld64)."""
    providers = set(re.findall(r'([A-Za-z0-9_.\-]+\.a)\(sqlite3\.c\.o\)', map_text))
    providers |= {name + '.lib' for name in re.findall(r'([A-Za-z0-9_.\-]+?)(?:\.lib)?:sqlite3\.c\.obj', map_text)}
    providers |= {name for name in re.findall(r'/([A-Za-z0-9_.\-]+\.lib)\(sqlite3\.c\.obj\)', map_text)}
    return sorted(providers)


def direct_providers(map_text):
    """SQLite amalgamation objects linked directly instead of through an archive.

    A direct object always carries a path separator; an archive member appears as
    lib(name).a(sqlite3.c.o) (GNU/ld64) or name.lib:sqlite3.c.obj (MSVC), so both
    of those shapes are excluded here on purpose.
    """
    found = set()
    for match in re.finditer(r'([^\s\]"]*[/\\]sqlite3\.c\.o)(?![)])', map_text):
        found.add(match.group(1))
    return sorted(found)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command, log, environment=None):
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                            errors='replace', env=environment)
    Path(log).write_text('$ ' + ' '.join(map(str, command)) + '\nexit=' + str(result.returncode) +
                         '\n--- stdout\n' + result.stdout + '\n--- stderr\n' + result.stderr, encoding='utf-8')
    print(result.stdout[-4000:])
    print(result.stderr[-4000:])
    return result


def judged(report_path, required, label, problems):
    if not Path(report_path).is_file():
        problems.append(label + ' wrote no report')
        return {'checks': [], 'failures': 1}
    report = json.loads(Path(report_path).read_text(encoding='utf-8'))
    if not isinstance(report.get('checks'), list):
        problems.append(label + ' reported no check list')
        return {'checks': [], 'failures': 1}
    names = [item['name'] for item in report['checks']]
    duplicated = sorted({name for name in names if names.count(name) > 1})
    if duplicated:
        problems.append(label + ' reported duplicate items: ' + ', '.join(duplicated))
    failed = [item['name'] for item in report.get('checks', []) if not item.get('pass')]
    if failed:
        problems.append(label + ' failed items: ' + ', '.join(failed))
    if report.get('failures'):
        problems.append(label + ' reported %s failures' % report['failures'])
    missing = [name for name in required if name not in names]
    if missing:
        problems.append(label + ' is missing items: ' + ', '.join(missing))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--c-consumer', type=Path, required=True)
    parser.add_argument('--cxx-consumer', type=Path, required=True)
    parser.add_argument('--relocated-c-consumer', type=Path, required=True)
    parser.add_argument('--relocated-cxx-consumer', type=Path, required=True)
    parser.add_argument('--link-map', type=Path, required=True)
    parser.add_argument('--c-link-map', type=Path, required=True)
    parser.add_argument('--prefix', type=Path, required=True)
    parser.add_argument('--relocated-prefix', type=Path, required=True)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--interface', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'composition gate is cloud only'
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    problems = []
    audits = []

    def audit(ok, name, detail=''):
        audits.append({'name': name, 'pass': bool(ok), 'detail': detail})
        if not ok:
            problems.append(name + (' ' + detail if detail else ''))
        return ok

    fixtures = args.fixtures.resolve()
    text_sha = sha(fixtures / 'sample.txt')
    epub_sha = sha(fixtures / 'layout.epub')
    audit((args.prefix.resolve() != args.relocated_prefix.resolve()),
          'the relocated consumer uses a different prefix path',
          str(args.relocated_prefix.resolve()))

    # 1. The C11 consumer, no network at all.
    c_work = out / 'c-work'
    c_work.mkdir()
    c_run = run([str(args.c_consumer.resolve()), '--fixtures', str(fixtures), '--work', str(c_work),
                 '--report', str(out / 'composition-c.json'), '--sha', 'txt=' + text_sha], out / 'c.log')
    audit(c_run.returncode == 0, 'the C11 consumer exits zero', str(c_run.returncode))
    c_report = judged(out / 'composition-c.json', REQUIRED_C, 'the C11 consumer', problems)

    # 2. Real TLS WebDAV, two independent roots for the two prefixes.
    with WebDAVFixture(out / 'certificates', roots=('/dav/', '/dav-relocated/')) as fixture:
        environment = dict(os.environ, READER_TEST_AUTH=fixture.authorization)
        run1 = out / 'run1'
        run1.mkdir()
        first = run([str(args.cxx_consumer.resolve()), '--fixtures', str(fixtures), '--work', str(run1),
                     '--report', str(out / 'composition-run1.json'), '--webdav-root', fixture.root_url(0),
                     '--sha', 'txt=' + text_sha, '--sha', 'epub=' + epub_sha],
                    out / 'run1.log', environment)
        audit(first.returncode == 0, 'the composed C++ consumer exits zero', str(first.returncode))
        run1_report = judged(out / 'composition-run1.json', REQUIRED_CXX, 'the composed consumer', problems)

        run2 = out / 'run2'
        run2.mkdir()
        relocated = run([str(args.relocated_cxx_consumer.resolve()), '--fixtures', str(fixtures),
                         '--work', str(run2), '--report', str(out / 'composition-run2.json'),
                         '--webdav-root', fixture.root_url(1),
                         '--sha', 'txt=' + text_sha, '--sha', 'epub=' + epub_sha],
                        out / 'run2.log', environment)
        audit(relocated.returncode == 0, 'the relocated consumer exits zero', str(relocated.returncode))
        relocated_report = judged(out / 'composition-run2.json', REQUIRED_CXX, 'the relocated consumer', problems)
        relocated_c_work = out / 'c-work-relocated'
        relocated_c_work.mkdir()
        relocated_c = run([str(args.relocated_c_consumer.resolve()), '--fixtures', str(fixtures),
                           '--work', str(relocated_c_work), '--report', str(out / 'composition-c-relocated.json'),
                           '--sha', 'txt=' + text_sha], out / 'c-relocated.log')
        audit(relocated_c.returncode == 0, 'the relocated C11 consumer exits zero', str(relocated_c.returncode))
        judged(out / 'composition-c-relocated.json', REQUIRED_C, 'the relocated C11 consumer', problems)

        # Server-side evidence: the bytes really travelled, under one identity.
        objects = fixture.objects()
        revisions = fixture.revisions()
        audit(len(objects) == len(fixture.roots),
              'each prefix root received exactly one immutable original', str(len(objects)))
        for path, body in objects.items():
            digest = hashlib.sha256(body).hexdigest()
            audit(digest == text_sha and path.endswith('/objects/' + text_sha[:2] + '/' + text_sha + '.txt'),
                  'the stored original carries the source identity', path)
            audit(len(body) == (fixtures / 'sample.txt').stat().st_size,
                  'the stored original keeps its exact length', str(len(body)))
        published = (run1_report.get('network_pushed', 0) + run1_report.get('session_pushed', 0) +
                     relocated_report.get('network_pushed', 0) + relocated_report.get('session_pushed', 0))
        audit(len(revisions) == published,
              'the store holds exactly the revisions both runs acknowledged',
              '%d stored / %d acknowledged' % (len(revisions), published))
        for path, body in revisions.items():
            leaf = path.rsplit('/', 1)[1]
            value = json.loads(body)
            audit(re.fullmatch('[0-9a-f]{32}-[0-9a-f]{64}\.json', leaf) is not None and
                  leaf == value['id'] + '-' + hashlib.sha256(body).hexdigest() + '.json',
                  'every published revision leaf matches its own bytes', leaf)
        journal = fixture.requests
        audit(len(journal) > 0, 'the fixture served the composition', str(len(journal)))
        audit(all(entry['authenticated'] for entry in journal),
              'every request carried the session authorization')
        audit(all(entry['if_none_match'] == '*' for entry in journal if entry['method'] == 'PUT'),
              'every PUT was conditional and immutable')
        audit(all(entry['depth'] == '1' for entry in journal if entry['method'] == 'PROPFIND'),
              'every PROPFIND stayed bounded to depth one')
        roots = {entry['root'] for entry in journal}
        audit(roots == {'/dav/', '/dav-relocated/'}, 'both prefixes used their own root', ','.join(sorted(roots)))
        audit(fixture.port > 0, 'the fixture used a real ephemeral port', str(fixture.port))
        counts = {'requests': len(journal), 'objects': len(objects), 'revisions': len(revisions),
                  'puts': sum(1 for entry in journal if entry['method'] == 'PUT'),
                  'gets': sum(1 for entry in journal if entry['method'] == 'GET'),
                  'propfinds': sum(1 for entry in journal if entry['method'] == 'PROPFIND'),
                  'mkcols': sum(1 for entry in journal if entry['method'] == 'MKCOL')}
        (out / 'native-requests.json').write_text(json.dumps(journal, indent=1) + '\n', encoding='utf-8')
        fixture.assert_secret_free(out)

    # 3. The final link graph: exactly one product SQLite provider.
    map_text = args.link_map.read_text(encoding='utf-8', errors='replace')
    providers = archive_providers(map_text)
    direct = direct_providers(map_text)
    audit(len(providers) == 1 and 'reader_catalog_sqlite' in providers[0],
          'the composed link graph has exactly one product SQLite provider', ','.join(providers))
    audit(not direct, 'no second SQLite amalgamation object is linked directly', ','.join(direct))
    c_map = args.c_link_map.read_text(encoding='utf-8', errors='replace')
    c_providers = archive_providers(c_map)
    c_direct = direct_providers(c_map)
    audit(len(c_providers) == 1 and 'reader_catalog_sqlite' in c_providers[0],
          'the C11 link graph has exactly one product SQLite provider', ','.join(c_providers))
    audit(not c_direct, 'the C11 link graph links no second amalgamation object', ','.join(c_direct))

    # 4. Consumer identity and the items the consumers themselves report.
    audit(first.returncode == 0 and run1_report.get('failures') == 0 and
          run1_report.get('native_webdav') is True and run1_report.get('resolved_state') == 'FOUND',
          'the composed consumer reports a real FOUND resolve on the second SDK',
          str(run1_report.get('resolved_state')))
    audit(relocated_report.get('failures') == 0 and relocated_report.get('resolved_state') == 'FOUND',
          'the relocated consumer reproduces the same FOUND resolve',
          str(relocated_report.get('resolved_state')))
    audit(c_report.get('failures') == 0, 'the C11 consumer reports no failure', str(c_report.get('failures')))
    audit(run1_report.get('session_sweeps', 0) >= 1, 'the session completed a sweep',
          str(run1_report.get('session_sweeps')))
    audit(run1_report.get('network_pushed', 0) >= 3 and run1_report.get('network_pulled', 0) >= 3,
          'the transfer counters record both directions',
          '%s/%s' % (run1_report.get('network_pushed'), run1_report.get('network_pulled')))

    summary = {
        'accepted': not problems,
        'source_sha': os.environ.get('GITHUB_SHA'),
        'run_id': os.environ.get('GITHUB_RUN_ID'),
        'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
        'platform': sys.platform,
        'runner_os': os.environ.get('RUNNER_OS'),
        'prefix': str(args.prefix.resolve()),
        'relocated_prefix': str(args.relocated_prefix.resolve()),
        'resolved_state': run1_report.get('resolved_state'),
        'relocated_resolved_state': relocated_report.get('resolved_state'),
        'session_sweeps': run1_report.get('session_sweeps'),
        'network_pushed': run1_report.get('network_pushed'),
        'network_pulled': run1_report.get('network_pulled'),
        'sqlite_providers': providers,
        'direct_providers': direct,
        'c_sqlite_providers': c_providers,
        'webdav': counts,
        'consumers': {
            'composition-c': {'sha256': sha(args.c_consumer), 'items': len(c_report.get('checks', []))},
            'composition-cxx': {'sha256': sha(args.cxx_consumer),
                                'items': len(run1_report.get('checks', []))},
            'composition-c-relocated': {'sha256': sha(args.relocated_c_consumer)},
            'composition-cxx-relocated': {'sha256': sha(args.relocated_cxx_consumer),
                                          'items': len(relocated_report.get('checks', []))},
        },
        'link_map_sha256': sha(args.link_map),
        'interface_sha256': sha(args.interface) if args.interface and args.interface.is_file() else None,
        'install_manifest_sha256': sha(args.manifest) if args.manifest and args.manifest.is_file() else None,
        'items': audits,
        'failures': problems,
        'default_reading_build_without_modules': True,
        'host_ui_accepted': False,
        'android_accepted': False,
        'ios_accepted': False,
        'complete_product': False,
    }
    (out / 'result.json').write_text(json.dumps(summary, indent=1) + '\n', encoding='utf-8')
    for item in audits:
        print(('PASS ' if item['pass'] else 'FAIL ') + item['name'] + (' :: ' + item['detail'] if item['detail'] else ''))
    print(json.dumps({k: summary[k] for k in ('accepted', 'platform', 'sqlite_providers', 'webdav')}))
    return 0 if summary['accepted'] else 1


if __name__ == '__main__':
    sys.exit(main())
