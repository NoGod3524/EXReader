# SPDX-License-Identifier: MIT
"""Judge the installed S16 consumers and the raw report in Actions only.

Two modes:
  raw      the explicit EXReaderJumpHistory 0.2.0 install: the C consumer plus
           the C++ raw probe with real public-SDK captures.
  default  the default EXReaderJumpHistory 0.1.0 install: only the C consumer,
           which must still see the unchanged legacy surface and no raw symbol.
Nothing here runs on a developer machine: the caller supplies binaries that the
same job built from installed packages.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REQUIRED = [
    'the installed package is the explicit raw candidate 0.2.0',
    'the raw adapter and raw revision family are installed',
    'the installed SDK is the approved exact build',
    'the stores and the SDK library start empty',
    'the public PDF page text contains NUL',
    'the real PDF point capture has an allocated empty quote and a NUL suffix',
    'the legacy entry refuses the real PDF NUL capture',
    'a refused legacy NUL capture leaves the legacy history empty',
    'the raw entry stores the real PDF NUL point as ADDED',
    'the stored raw wire is anchor version 3',
    'the stored raw wire keeps the NUL suffix bytes exactly',
    'the stored raw wire keeps the allocated empty quote',
    'the stored raw wire keeps the page ID and page number',
    'the host resolves the stored NUL point FOUND through the public v3 resolver',
    'the legacy fixed resolver refuses an anchor v3 record',
    'the public SDK recaptures the same nullable selector bytes',
    'a raw FOUND resolve alone does not move the cursor',
    'the same raw landing again is UNCHANGED',
    'UNCHANGED keeps the raw entry id and the single entry',
    'a second real PDF point in the same book coalesces',
    'coalescing keeps one PDF entry and replaces its wire',
    'the coalesced entry holds the second point',
    'the installed validator refuses a raw progress range',
    'a refused raw range leaves the history untouched',
    'the raw encoder accepts a host NULL selector expression as transport',
    'the raw entry refuses a NULL selector instead of emptying it',
    'a NULL selector leaves the history untouched',
    'a real CBZ textless page is stored by the raw entry',
    'the textless raw point keeps an allocated empty quote and zero context lengths',
    'the textless raw point keeps the page ID and page number',
    'the textless raw target resolves FOUND',
    'the retained v1 TXT range encodes on the legacy store',
    'the raw entry stores a retained v1 range wire',
    'the stored v1 wire keeps anchor version 1 and its non-empty range',
    'the stored v1 wire is byte-identical to the encoded wire',
    'the host resolves the stored v1 range FOUND',
    'the retained v2 TXT point encodes on the legacy store',
    'the raw entry stores a retained v2 point wire',
    'the stored v2 wire keeps anchor version 2 and the empty point',
    'the host resolves the stored v2 point FOUND',
    'the retained v2 EPUB chapter wire encodes',
    'the raw entry stores a retained v2 EPUB wire',
    'the stored v2 EPUB wire keeps the spine index and path',
    'the host resolves the stored v2 EPUB target FOUND',
    'the retained v1 EPUB path wire encodes',
    'the raw entry stores a retained v1 EPUB wire',
    'the stored v1 EPUB wire keeps anchor version 1 and its path',
    'the host resolves the stored v1 EPUB part from its path',
    'the four location routes are all present in one history',
    'a point whose suffix continues after NUL is ADDED',
    'a point that differs only after that NUL is a different place',
    'the second stored wire keeps the bytes after the embedded NUL',
    'the first stored wire keeps its own bytes after the embedded NUL',
    'a NULL context is stored as its own place',
    'an allocated empty context is not the same place as NULL',
    'the stored wires keep NULL and allocated empty apart',
    'both nullable wires keep their own context bytes',
    'the first move landing is ADDED',
    'the second move landing is ADDED',
    'the third move landing is ADDED',
    'a raw peek back does not move the cursor',
    'the host resolves the previous CBZ point FOUND',
    'complete moves back after FOUND',
    'a raw landing behind the cursor is ADDED',
    'a raw landing truncates the forward entries',
    'the truncation is accounted',
    'complete moves back a second time',
    'a raw peek forward names the entry that was left behind',
    'the host resolves the next PDF point FOUND',
    'complete moves forward after FOUND',
    'nothing is ahead of the newest entry',
    'a cancelled raw jump leaves the cursor and generation alone',
    'complete refuses a raw item the history has moved past',
    'a stale raw complete moves nothing',
    'a foreign raw history ticket is STALE',
    'a foreign raw ticket leaves the state unchanged',
    'the own raw history ticket stays valid',
    'the raw entry cap keeps exactly three entries',
    'the raw entry cap dropped the two oldest',
    'the newest raw entry is current after eviction',
    'item_at reads the oldest kept raw entry',
    'the kept raw entry still decodes',
    'the raw byte budget is never exceeded',
    'the raw byte budget evicts the oldest entries',
    'the raw byte budget keeps the newest entry current',
    'the raw family keeps the byte floor',
    'the raw entry refuses a legacy store',
    'the raw wire entry refuses a legacy store',
    'the legacy wire entry refuses an anchor v3 wire',
    'every cross-family landing left the legacy history empty',
    'the legacy entry refuses a raw store',
    'the legacy wire entry refuses a raw store',
    'the raw entry refuses a non-fixed capture',
    'the raw wire entry refuses a truncated v3 wire',
    'the raw wire entry keeps the per-entry byte cap',
    'every cross-family landing left the raw history untouched',
    'a foreign thread cannot commit a raw entry',
    'a foreign thread cannot commit a raw wire',
    'a foreign thread cannot peek a raw history',
    'a foreign thread cannot close a raw history',
    'adopt_thread hands the raw history to the caller',
    'the previous owner is refused after adoption',
    'adopt_thread returns the raw history',
    'the owner can peek the raw history again',
    'the lifetime raw landing is ADDED',
    'the raw item carries the wire and its book key',
    'clear drops the raw entry',
    'clear empties the raw history',
    'an item outlives the closed raw history',
    'a closed-raw-history item still decodes through the raw validator',
    'release zeroes the raw item',
    'no product revision and no outbox row was created by raw landings',
    'no revision was inserted into the raw store',
    'no SDK progress record was written',
    'no SDK note was written',
    'the library and revision databases are byte-identical after the whole run',
    'the control position encodes',
    'the control product and SDK writes commit',
    'the same measurement detects real product and SDK writes',
]
CASE_MODES = {
    'pdf-nul-point': ('fixed_page', 3),
    'cbz-textless-raw': ('fixed_page', 3),
    'txt-v1-range': ('reflow_global', 1),
    'txt-v2-point': ('reflow_global', 2),
    'epub-v2-chapter': ('epub_chapter', 2),
    'epub-v1-path': ('epub_chapter', 1),
}
MOVE_STEPS = ['back-cbz', 'back-cbz-again', 'forward-pdf']
STABLE_NO_WRITE = ('revision_rows', 'outbox_rows', 'raw_revision_rows', 'raw_outbox_rows', 'sdk_progress_records',
                   'sdk_notes', 'sdk_fixed_notes', 'sdk_epub_notes', 'databases_unchanged', 'control_write_changed')
SEMANTICS = ('nul_suffix_preserved', 'null_vs_allocated_empty_preserved', 'retained_v1_v2_replayed', 'anchor3_stored',
             'selector_lengths_used_not_strlen', 'raw_store_only_for_raw_entry', 'legacy_entry_refuses_anchor3')
UNCOVERED = [
    'hosts: the four production reader hosts are not wired to this component; root owns the wiring and the shared-source revalidation',
    'gui: no desktop, GTK, Android or Apple jump/back/forward control, menu, shortcut or dialog is claimed here',
    'persistence: the stack is in memory only; no restart, cross-device or sync entity is claimed',
    'adoption: the raw candidate is an explicit module capability and is not an accepted SDK or product default',
    'progress: the component stores positions but writes no reading progress, SDK note or product revision by design',
    'performance: no latency or CPU budget is claimed; only the documented entry and byte caps are enforced',
    'scale: real captures cover one public PDF original and three generated originals; no real user library is used',
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command, log):
    result = subprocess.run([str(x) for x in command], capture_output=True, text=True, encoding='utf-8', errors='replace')
    Path(log).write_text('$ ' + ' '.join(map(str, command)) + '\nexit=' + str(result.returncode)
                         + '\n--- stdout\n' + result.stdout + '\n--- stderr\n' + result.stderr, encoding='utf-8')
    return result


def named_checks(text):
    checks = []
    for line in text.splitlines():
        if line.startswith('PASS '):
            checks.append({'name': line[5:].strip(), 'pass': True})
        elif line.startswith('FAIL '):
            checks.append({'name': line[5:].strip(), 'pass': False})
    return checks


def package_version(installed, package):
    version_file = Path(installed) / 'lib' / 'cmake' / package / (package + 'ConfigVersion.cmake')
    if not version_file.exists():
        return None
    for line in version_file.read_text(encoding='utf-8', errors='replace').splitlines():
        line = line.strip()
        if line.startswith('set(PACKAGE_VERSION'):
            return line.split('"')[1]
    return None


def jump_history_archive(installed):
    libraries = sorted(p for p in (Path(installed) / 'lib').glob('*') if 'jump_history' in p.name)
    return libraries


def main():
    parser = argparse.ArgumentParser()
    for name in ('mode', 'consumer', 'fixtures', 'installed', 'platform', 'output'):
        parser.add_argument('--' + name, required=True)
    for name in ('font', 'pdf', 'pdf-sha', 'probe'):
        parser.add_argument('--' + name)
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    work = out / 'work'
    work.mkdir()
    raw = args.mode == 'raw'
    family = 'raw-candidate' if raw else 'default'
    problems = []

    def need(ok, message):
        if not ok:
            problems.append(message)

    manifest = json.loads((Path(args.fixtures) / 'manifest.json').read_text(encoding='utf-8'))
    pdf_sha = args.pdf_sha
    if raw:
        need(args.pdf is not None and args.font is not None, 'the raw mode requires --pdf and --font')
        pdf = Path(args.pdf)
        need(pdf.exists() and len(pdf.read_bytes()) == 8845 and sha(pdf) == pdf_sha,
             'the public PDF original is not the expected 8845-byte original')

    c_run = run([args.consumer, work, family], out / 'c-consumer.log')
    need(c_run.returncode == 0, 'C consumer exit ' + str(c_run.returncode))
    c_checks = named_checks(c_run.stdout)
    need(len(c_checks) >= 18, 'only ' + str(len(c_checks)) + ' C consumer checks ran')
    need(all(c['pass'] for c in c_checks), 'C consumer checks failed: '
         + repr([c['name'] for c in c_checks if not c['pass']]))

    report = {}
    probe_checks = []
    if raw:
        need(args.probe is not None and Path(args.probe).exists(), 'the raw mode requires the built raw probe')
        probe_work = work / 'probe'
        probe_work.mkdir()
        command = [args.probe, '--fixtures', args.fixtures,
                   '--font', args.font, '--pdf', args.pdf, '--pdf-sha', pdf_sha, '--work', str(probe_work),
                   '--report', str(out / 'report.json')]
        for role, item in sorted(manifest.items()):
            command += ['--sha', role + '=' + item['sha256']]
        probe = run(command, out / 'probe.log')
        need(probe.returncode == 0, 'raw probe exit ' + str(probe.returncode))
        report_path = out / 'report.json'
        if not report_path.exists():
            problems.append('the raw probe wrote no report')
        else:
            report = json.loads(report_path.read_text(encoding='utf-8'))
            probe_checks = report.get('checks', [])
            names = [c.get('name') for c in probe_checks]
            need(len(names) == len(set(names)), 'raw check names are not unique')
            need(set(REQUIRED).issubset(names),
                 'required raw checks missing: ' + repr(sorted(set(REQUIRED) - set(names))))
            need(all(c.get('pass') is True for c in probe_checks),
                 'raw checks failed: ' + repr([c.get('name') for c in probe_checks if c.get('pass') is not True]))
            need(report.get('failures') == 0, 'the raw probe reported failures ' + repr(report.get('failures')))
            need(report.get('checks_total') == len(probe_checks), 'the raw check count is inconsistent')
            need(report.get('install_version') == '0.2.0', 'the raw install version is ' + repr(report.get('install_version')))
            need(report.get('jump_history_version') == '0.1.0', 'the legacy ABI version moved')
            need(report.get('reading_state_version') == '0.2.0', 'the raw adapter version is ' + repr(report.get('reading_state_version')))
            need(report.get('revisions_version') == '0.4.0', 'the raw revision family is ' + repr(report.get('revisions_version')))
            need(report.get('sdk_version') == '3.41.0', 'the SDK version is ' + repr(report.get('sdk_version')))
            need(report.get('pdf_sha256') == pdf_sha, 'the report PDF identity differs')
            cases = {c['id']: c for c in report.get('cases', [])}
            for case_id, (mode, version) in CASE_MODES.items():
                case = cases.get(case_id)
                if case is None:
                    problems.append('missing stored-wire case ' + case_id)
                    continue
                need(case.get('mode') == mode, case_id + ': mode is ' + repr(case.get('mode')))
                need(int(case.get('anchor_version', 0)) == version, case_id + ': anchor version is ' + repr(case.get('anchor_version')))
                need(int(case.get('stored_wire_bytes', 0)) > 0, case_id + ': stored wire is empty')
                need(int(case.get('accounted_bytes', 0)) >= int(case.get('stored_wire_bytes', 0)), case_id + ': accounting is short')
                need(case.get('operation') == 'put' and case.get('entity_kind') == 'progress',
                     case_id + ': stored wire is not a progress put')
                need(case.get('outcome') in ('ADDED', 'COALESCED'), case_id + ': outcome is ' + repr(case.get('outcome')))
            point = cases.get('pdf-nul-point', {})
            need(point.get('exact_present') == 1 and point.get('exact_bytes') == 0,
                 'the real PDF point must store an allocated empty quote')
            need(point.get('suffix_has_nul') is True and int(point.get('suffix_bytes', 0)) > 0,
                 'the real PDF point must store a NUL context')
            need(point.get('page') == 0 and point.get('page_id') == 'page-1',
                 'the real PDF point must keep its page identity')
            textless = cases.get('cbz-textless-raw', {})
            need(textless.get('exact_bytes') == 0 and textless.get('prefix_bytes') == 0 and textless.get('suffix_bytes') == 0,
                 'the textless CBZ point must store empty lengths')
            need(textless.get('page') == 1, 'the textless CBZ point must keep its page number')
            need(cases.get('txt-v1-range', {}).get('exact_bytes') == 3, 'the v1 range keeps three quote bytes')
            need(cases.get('epub-v2-chapter', {}).get('part') is not None and cases.get('epub-v2-chapter', {}).get('part_path'),
                 'the v2 EPUB case keeps its spine index and path')
            need(cases.get('epub-v1-path', {}).get('part_path'), 'the v1 EPUB case keeps its path')
            routes = {case.get('mode') + '/' + str(case.get('anchor_version')) for case in cases.values()}
            need({'reflow_global/1', 'reflow_global/2', 'epub_chapter/2', 'fixed_page/3'}.issubset(routes),
                 'the stored routes are ' + repr(sorted(routes)))
            for role in ('txt', 'epub', 'cbz'):
                case = next((c for c in cases.values() if c.get('book') == role), None)
                need(case is not None and case.get('book_key', '').endswith(':' + manifest[role]['sha256']),
                     role + ': stored book_key is not the generated original SHA-256')
            steps = {s['step']: s for s in report.get('lifecycle', [])}
            for step in MOVE_STEPS:
                need(step in steps, 'missing move ' + step)
            back = steps.get('back-cbz', {})
            need(int(back.get('from_cursor', -1)) > int(back.get('to_cursor', -1)), 'back-cbz did not move the cursor back')
            forward = steps.get('forward-pdf', {})
            need(int(forward.get('to_cursor', -1)) > int(forward.get('from_cursor', -1)), 'forward-pdf did not move the cursor forward')
            need(int(report.get('moves', 0)) >= len(MOVE_STEPS), 'fewer moves than expected')
            no_write = report.get('no_write', {})
            need(no_write.get('databases_unchanged') is True and no_write.get('control_write_changed') is True,
                 'the no-write measurement is not sensitive or the databases changed')
            for key in ('revision_rows', 'outbox_rows', 'raw_revision_rows', 'raw_outbox_rows', 'sdk_progress_records',
                        'sdk_notes', 'sdk_fixed_notes', 'sdk_epub_notes'):
                need(no_write.get(key) == 0, key + ' is ' + repr(no_write.get(key)))
            semantics = report.get('raw_semantics', {})
            for key in SEMANTICS:
                need(semantics.get(key) is True, 'raw semantic flag ' + key + ' is ' + repr(semantics.get(key)))
            need(report.get('host_wiring_accepted') is False and report.get('gui_accepted') is False,
                 'the raw report must not accept host wiring or a GUI')

    installed = Path(args.installed)
    header = installed / 'include' / 'reader_jump_history.h'
    need(header.exists(), 'the installed package has no reader_jump_history.h')
    header_text = header.read_text(encoding='utf-8', errors='replace') if header.exists() else ''
    archives = jump_history_archive(installed)
    need(len(archives) == 1, 'the installed package must carry one jump-history library')
    archive_bytes = archives[0].read_bytes() if len(archives) == 1 else b''
    need(package_version(installed, 'EXReaderJumpHistory') == ('0.2.0' if raw else '0.1.0'),
         'the installed jump-history package version is ' + repr(package_version(installed, 'EXReaderJumpHistory')))
    need(package_version(installed, 'EXReaderReadingState') == ('0.2.0' if raw else '0.1.0'),
         'the installed reading-state version is ' + repr(package_version(installed, 'EXReaderReadingState')))
    need(package_version(installed, 'EXReaderRevisions') == ('0.4.0' if raw else '0.3.0'),
         'the installed revisions version is ' + repr(package_version(installed, 'EXReaderRevisions')))
    if raw:
        for symbol in ('reader_jh_commit_fixed_v3', 'reader_jh_commit_wire_raw_v3'):
            need(symbol in header_text, 'the raw installed header lacks ' + symbol)
            need(symbol.encode() in archive_bytes, 'the raw installed archive lacks ' + symbol)
        need('#define READER_JH_INSTALL_VERSION "0.2.0"' in header_text, 'the raw installed header lacks its family macro')
        need('#define READER_JH_VERSION "0.1.0"' in header_text, 'the raw installed header moved the ABI version')
    else:
        for symbol in ('reader_jh_commit_fixed_v3', 'reader_jh_commit_wire_raw_v3'):
            need(symbol not in header_text, 'the default installed header exposes ' + symbol)
            need(symbol.encode() not in archive_bytes, 'the default installed archive carries ' + symbol)
        need('#define READER_JH_INSTALL_VERSION "0.1.0"' in header_text, 'the default header lacks its family macro')

    summary = {
        'identity': {key: os.environ.get(key) for key in
                     ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_JOB', 'RUNNER_OS', 'GITHUB_REF_NAME')},
        'platform': args.platform,
        'mode': args.mode,
        'family': family,
        'originals': manifest,
        'pdf_sha256': pdf_sha,
        'pdf_bytes': 8845 if raw else None,
        'installed': {
            'header_sha256': sha(header) if header.exists() else None,
            'library_sha256': sha(archives[0]) if len(archives) == 1 else None,
            'library': archives[0].name if len(archives) == 1 else None,
            'jump_history_version': package_version(installed, 'EXReaderJumpHistory'),
            'reading_state_version': package_version(installed, 'EXReaderReadingState'),
            'revisions_version': package_version(installed, 'EXReaderRevisions'),
        },
        'c_checks': c_checks,
        'probe_checks': probe_checks,
        'probe_sha256': sha(args.probe) if args.probe and Path(args.probe).exists() else None,
        'report_sha256': sha(out / 'report.json') if (out / 'report.json').exists() else None,
        'checks_total': len(probe_checks) + len(c_checks),
        'checks_failed': len([c for c in probe_checks + c_checks if not c.get('pass')]),
        'cases_total': report.get('cases_total'),
        'moves': report.get('moves'),
        'cases': report.get('cases', []),
        'lifecycle': report.get('lifecycle', []),
        'no_write': report.get('no_write', {}),
        'raw_semantics': report.get('raw_semantics', {}),
        'versions': {'install': report.get('install_version'), 'jump_history': report.get('jump_history_version'),
                     'reading_state': report.get('reading_state_version'), 'revisions': report.get('revisions_version'),
                     'sdk': report.get('sdk_version')},
        'problems': problems,
        'accepted': not problems,
        'host_wiring_accepted': False,
        'gui_accepted': False,
        'adopted': False,
        'uncovered': UNCOVERED,
    }
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ('platform', 'mode', 'checks_total', 'checks_failed', 'cases_total',
                                              'moves', 'accepted', 'problems')}, indent=1))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
