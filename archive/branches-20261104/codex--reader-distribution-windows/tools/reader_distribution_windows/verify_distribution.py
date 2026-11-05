#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Strict named-result gate for one sealed Windows distribution.

Inputs are the reports the cloud job produced from the same source revision.
Nothing here trusts a claim it can recompute: the archive is re-read, the stage
is re-scanned, sanitization is re-inverted, and every consumer/smoke/dependency
report is bound to the same SHA, run and attempt.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import distlib
import reduce_archives

REQUIRED_RESULTS = (
    'source-identity-bound', 'archive-matches-stage', 'archive-tamper-evident',
    'archive-content-scanned-clean', 'stage-scanned-clean',
    'headers-config-licenses-hashed', 'sanitization-audited', 'resource-objects-removed',
    'relocation-prefix-distinct', 'relocated-consumers-pass', 'nine-format-smoke-complete',
    'installed-identity-matches-headers', 'dependency-closure-system-only',
    'probe-prefix-bound', 'debug-sections-carry-no-build-root', 'no-absolute-drective',
    'archive-member-names-relative', 'deterministic-seal', 'pkgconfig-metadata-relocatable',
    'pkgconfig-consumer-links-installed-library',
)
REQUIRED_NEGATIVES = (
    'negative-probe-rejects-foreign-prefix', 'negative-consumer-rejects-missing-book',
    'negative-scan-blocks-leaking-control', 'negative-scan-blocks-absolute-drective',
)
SYSTEM_IMPORT_ALLOW = frozenset({
    'kernel32.dll', 'user32.dll', 'gdi32.dll', 'advapi32.dll', 'shell32.dll', 'ole32.dll',
    'oleaut32.dll', 'comdlg32.dll', 'shlwapi.dll', 'ws2_32.dll', 'bcrypt.dll', 'crypt32.dll',
    'secur32.dll', 'winmm.dll', 'version.dll', 'userenv.dll', 'ntdll.dll', 'psapi.dll',
    'msvcrt.dll', 'ucrtbase.dll', 'vcruntime140.dll', 'vcruntime140_1.dll', 'msvcp140.dll',
    'api-ms-win-crt-runtime-l1-1-0.dll', 'api-ms-win-crt-stdio-l1-1-0.dll',
    'api-ms-win-crt-heap-l1-1-0.dll', 'api-ms-win-crt-string-l1-1-0.dll',
    'api-ms-win-crt-convert-l1-1-0.dll', 'api-ms-win-crt-math-l1-1-0.dll',
    'api-ms-win-crt-locale-l1-1-0.dll', 'api-ms-win-crt-filesystem-l1-1-0.dll',
    'api-ms-win-crt-environment-l1-1-0.dll', 'api-ms-win-crt-time-l1-1-0.dll',
    'api-ms-win-crt-utility-l1-1-0.dll', 'api-ms-win-crt-private-l1-1-0.dll',
    'api-ms-win-core-synch-l1-2-0.dll', 'api-ms-win-core-file-l1-1-0.dll',
})


def parse_header(path):
    text = Path(path).read_text(encoding='utf-8')
    sdk = re.search(r'^#define EXR_VERSION "([0-9]+\.[0-9]+\.[0-9]+)"$', text, re.M)
    abi = re.search(r'^#define EXR_ABI_VERSION ([0-9]+)u?$', text, re.M)
    distlib.require(sdk and abi, 'installed headers lost their version/ABI declaration')
    return sdk[1], int(abi[1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--distribution', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--scan', type=Path, required=True)
    parser.add_argument('--sanitize', type=Path, required=True)
    parser.add_argument('--identity', type=Path, required=True)
    parser.add_argument('--relocation', type=Path, required=True)
    parser.add_argument('--smoke', type=Path, required=True)
    parser.add_argument('--dependencies', type=Path, required=True)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--negatives', type=Path, required=True)
    parser.add_argument('--pkgconfig', type=Path, required=True,
                        help='pkg-config metadata and consumer report')
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    results = []
    distribution = distlib.load_json(args.distribution)
    scan = distlib.load_json(args.scan)
    sanitize = distlib.load_json(args.sanitize)
    identity = distlib.load_json(args.identity)
    relocation = distlib.load_json(args.relocation)
    smoke = distlib.load_json(args.smoke)
    dependencies = distlib.load_json(args.dependencies)
    probe = distlib.load_json(args.probe)
    negatives = distlib.load_json(args.negatives)
    pkgconfig = distlib.load_json(args.pkgconfig)
    needles = {key: value.encode('utf-8') for key, value in scan['patterns'].items()}

    ci = distribution.get('ci', {})
    source_sha_ok = (distribution.get('source_sha') == args.source_sha and
                     ci.get('GITHUB_RUN_ID') == os.environ.get('GITHUB_RUN_ID') and
                     ci.get('GITHUB_RUN_ATTEMPT') == os.environ.get('GITHUB_RUN_ATTEMPT'))
    distlib.named(results, 'source-identity-bound', source_sha_ok,
                  {'source_sha': args.source_sha, 'run': ci.get('GITHUB_RUN_ID'),
                   'attempt': ci.get('GITHUB_RUN_ATTEMPT')})

    entries = distlib.inventory(args.stage)
    expected = {item['path']: (item['bytes'], item['sha256']) for item in entries}
    claimed = {item['path']: (item['bytes'], item['sha256']) for item in distribution['entries']}
    packed = distlib.read_zip(args.archive)
    actual = {item['path']: (item['bytes'], item['sha256']) for item in packed}
    distlib.named(results, 'archive-matches-stage', expected == claimed == actual,
                  {'stage_files': len(expected), 'claimed': len(claimed), 'packed': len(actual)})

    recomputed = distlib.digest(args.archive)
    distlib.named(results, 'archive-tamper-evident',
                  recomputed == distribution['archive']['sha256'] and
                  args.archive.stat().st_size == distribution['archive']['bytes'],
                  {'recomputed': recomputed, 'claimed': distribution['archive']['sha256']})

    packed_hits = []
    import zipfile
    with zipfile.ZipFile(args.archive) as archive:
        for info in archive.infolist():
            payload = archive.read(info)
            packed_hits.extend(distlib.find_hits(info.filename, payload, needles))
    distlib.named(results, 'archive-content-scanned-clean', not packed_hits,
                  {'hits': len(packed_hits), 'sample': packed_hits[:3]})

    stage_records = distlib.scan_tree(args.stage, needles)
    stage_hits = [hit for item in stage_records for hit in item['hits']]
    drective = [item for item in stage_records for _ in item.get('drective_absolute', [])]
    distlib.named(results, 'stage-scanned-clean', not stage_hits and not drective,
                  {'hits': len(stage_hits), 'drective': len(drective), 'sample': stage_hits[:3]})

    categories = distlib.category_digests(entries)
    hashed = all(categories[name]['files'] > 0 and categories[name]['sha256']
                 for name in ('header', 'config', 'license', 'library', 'doc'))
    detail = {name: categories[name]['files'] for name in distlib.CATEGORY_ORDER}
    distlib.named(results, 'headers-config-licenses-hashed',
                  hashed and categories == distribution['categories'], detail)

    audit_ok, audit_detail = True, []
    for record in sanitize.get('rewritten', []):
        path = args.stage / record['path']
        if not path.is_file() or distlib.digest(path) != record['sha256_after']:
            audit_ok = False
            audit_detail.append({'path': record['path'], 'problem': 'sanitized file changed'})
            continue
        occurrences = record.get('occurrences') or []
        if not occurrences:
            audit_ok = False
            audit_detail.append({'path': record['path'], 'problem': 'no recorded occurrences'})
            continue
        try:
            restored = distlib.restore_occurrences(path.read_bytes(), occurrences)
        except ValueError as error:
            audit_ok = False
            audit_detail.append({'path': record['path'], 'problem': str(error)})
            continue
        if distlib.digest_bytes(restored) != record['sha256_before']:
            audit_ok = False
            audit_detail.append({'path': record['path'], 'problem': 'rewrite is not invertible'})
    accepted_sanitize = (sanitize.get('accepted') is True and not sanitize.get('refused') and
                         sanitize.get('residual', {}).get('text_hits') == 0 and
                         sanitize.get('residual', {}).get('binary_hits') == 0)
    pcfiledir_ok, pcfiledir_detail = True, []
    for record in sanitize.get('rewritten', []):
        if record.get('mode') != 'pcfiledir':
            continue
        expression = record.get('expression') or ''
        expected = '$' + '{pcfiledir}'
        occurrences = record.get('occurrences') or []
        if not expression.startswith(expected) or record.get('prefix_variable') is not True:
            pcfiledir_ok = False
            pcfiledir_detail.append({'path': record['path'], 'problem': 'no pcfiledir expression'})
            continue
        if any(item.get('replacement') != expression for item in occurrences):
            pcfiledir_ok = False
            pcfiledir_detail.append({'path': record['path'], 'problem': 'mixed replacement values'})
    distlib.named(results, 'sanitization-audited', audit_ok and accepted_sanitize and pcfiledir_ok,
                  {'rewritten': len(sanitize.get('rewritten', [])), 'problems':
                   (audit_detail + pcfiledir_detail)[:4],
                   'pcfiledir_files': sum(1 for item in sanitize.get('rewritten', [])
                                          if item.get('mode') == 'pcfiledir')})

    reduction_ok, reduction_detail = True, []
    for record in sanitize.get('reduced', []):
        path = Path(record['path'])
        if not path.is_file() or distlib.digest(path) != record['sha256_after']:
            reduction_ok = False
            reduction_detail.append({'path': str(path), 'problem': 'reduced library changed'})
            continue
        try:
            keep, drop = reduce_archives.plan(path.read_bytes())
        except ValueError as error:
            reduction_ok = False
            reduction_detail.append({'path': str(path), 'problem': str(error)})
            continue
        if drop:
            reduction_ok = False
            reduction_detail.append({'path': str(path), 'problem': 'resource objects remain'})
    distlib.named(results, 'resource-objects-removed', reduction_ok,
                  {'libraries': len(sanitize.get('reduced', [])), 'problems': reduction_detail[:4]})

    prefix = Path(relocation.get('prefix', '')).as_posix().rstrip('/')
    stage_path = Path(args.stage).resolve().as_posix().rstrip('/')
    workspace = ci.get('GITHUB_WORKSPACE', '').replace('\\', '/').rstrip('/')
    distinct = (bool(prefix) and prefix != stage_path and
                not (workspace and prefix.startswith(workspace + '/')))
    distlib.named(results, 'relocation-prefix-distinct', distinct,
                  {'prefix': prefix, 'stage': stage_path, 'workspace': workspace})

    consumers = relocation.get('consumers', {})
    consumer_ok = all(consumers.get(name, {}).get('passed') is True
                      for name in ('c11', 'cpp17', 'document', 'identity')) and \
        relocation.get('extracted_elsewhere') is True
    distlib.named(results, 'relocated-consumers-pass', consumer_ok,
                  {name: consumers.get(name, {}).get('status') for name in
                   ('c11', 'cpp17', 'document', 'identity')})

    smoke_results = smoke.get('results', [])
    def observed(item):
        return item.get('observed') or {}
    smoke_ok = (smoke.get('accepted') is True and len(smoke_results) == 9 and
                all(item.get('classification') == 'passed' and observed(item).get('status') == 0 and
                    observed(item).get('complete') is True for item in smoke_results) and
                smoke.get('source_sha') == args.source_sha and smoke.get('source_dirty') is False)
    distlib.named(results, 'nine-format-smoke-complete', smoke_ok,
                  {'entries': len(smoke_results),
                   'formats': sorted({Path(str(item.get('path'))).suffix.lstrip('.').lower()
                                      for item in smoke_results}),
                   'failures': [item.get('path') for item in smoke_results
                                if item.get('classification') != 'passed'][:6]})

    sdk_version, abi = parse_header(args.stage / 'include/exr/base.h')
    identity_ok = (identity.get('sdk_version') == sdk_version and identity.get('abi') == abi and
                   str(identity.get('abi')) in ('1',) and identity.get('probe') is True)
    distlib.named(results, 'installed-identity-matches-headers', identity_ok,
                  {'headers': [sdk_version, abi], 'reported': [identity.get('sdk_version'), identity.get('abi')]})

    imports = {name.lower() for name in dependencies.get('imports', [])}
    unexpected = sorted(name for name in imports if name not in SYSTEM_IMPORT_ALLOW and
                        not name.startswith(('api-ms-win-', 'ext-ms-win-')))
    vendor = dependencies.get('vendor_closure', {})
    closure_ok = (not dependencies.get('absolute_imports') and not unexpected and
                  dependencies.get('checked_pe_files', 0) >= 3 and
                  not vendor.get('missing') and int(vendor.get('declared') or 0) > 0 and
                  int(vendor.get('installed') or 0) >= int(vendor.get('declared') or 0))
    distlib.named(results, 'dependency-closure-system-only', closure_ok,
                  {'imports': len(imports), 'unexpected': unexpected[:6],
                   'absolute': dependencies.get('absolute_imports', [])[:4],
                   'vendor': vendor})

    probe_ok = (probe.get('passed') is True and
                Path(probe.get('module_path', '')).as_posix().startswith(prefix + '/') and
                probe.get('external_modules') == [] and probe.get('sdk_version') == sdk_version and
                probe.get('abi') == abi and probe.get('document_parts', 0) >= 1)
    distlib.named(results, 'probe-prefix-bound', probe_ok,
                  {'module_path': probe.get('module_path'), 'external': probe.get('external_modules'),
                   'version': probe.get('sdk_version')})

    distlib.named(results, 'pkgconfig-metadata-relocatable',
                  pkgconfig.get('accepted') is True and int(pkgconfig.get('packages') or 0) >= 1 and
                  pkgconfig.get('resolved_inside_prefix') is True and
                  not pkgconfig.get('outside_paths') and not pkgconfig.get('failed'),
                  {'packages': pkgconfig.get('packages'),
                   'outside': (pkgconfig.get('outside_paths') or [])[:4],
                   'failed': (pkgconfig.get('failed') or [])[:4]})
    distlib.named(results, 'pkgconfig-consumer-links-installed-library',
                  (pkgconfig.get('consumer') or {}).get('linked') is True and
                  (pkgconfig.get('consumer') or {}).get('ran') is True,
                  pkgconfig.get('consumer'))

    debug_records = [item for item in stage_records if item.get('debug_section_count')]
    distlib.named(results, 'debug-sections-carry-no-build-root',
                  all(not item['hits'] for item in debug_records),
                  {'archives_with_debug_info': len(debug_records),
                   'debug_sections': sum(item['debug_section_count'] for item in debug_records),
                   'leaking': [item['path'] for item in debug_records if item['hits']][:6]})
    distlib.named(results, 'no-absolute-drective', not drective, {'count': len(drective)})
    separated = sum(len(item.get('member_names_with_separator', [])) for item in stage_records)
    escaping = sum(len(item.get('member_names_escaping') or []) for item in stage_records)
    distlib.named(results, 'archive-member-names-relative', escaping == 0,
                  {'escaping': escaping, 'relative_with_separator': separated})
    distlib.named(results, 'deterministic-seal',
                  (distribution.get('reproducibility') or {}).get('identical') is True,
                  distribution.get('reproducibility'))

    distlib.require_named_pass(results, REQUIRED_RESULTS)
    reported = [entry.get('name') for entry in negatives.get('results', [])]
    distlib.require(len(reported) == len(set(reported)),
                    'duplicate negative case in the report: ' + ', '.join(sorted(reported)))
    distlib.require(set(reported) == set(REQUIRED_NEGATIVES),
                    'negative cases differ from the fixed list (missing %s, unexpected %s)' % (
                        sorted(set(REQUIRED_NEGATIVES) - set(reported)),
                        sorted(set(reported) - set(REQUIRED_NEGATIVES))))
    for entry in negatives.get('results', []):
        distlib.require(isinstance(entry, dict) and entry.get('name') and
                        entry.get('status') in ('pass', 'fail'),
                        'negative case report is malformed')
        results.append({'name': entry['name'], 'status': entry['status'],
                        'detail': entry.get('detail')})
    distlib.require_named_pass(results, list(REQUIRED_NEGATIVES))
    summary = {'schema': 'reader-distribution-windows-summary-v1', 'accepted': True,
               'source_sha': args.source_sha, 'ci': ci,
               'distribution': {'archive': distribution['archive']['archive'],
                                'bytes': distribution['archive']['bytes'],
                                'sha256': distribution['archive']['sha256'],
                                'entries': distribution['archive']['entries'],
                                'stage_digest': distribution['stage']['digest'],
                                'categories': categories},
               'relocation': {'prefix': prefix,
                              'consumers': {name: consumers.get(name, {}).get('status')
                                            for name in ('c11', 'cpp17', 'document', 'identity')}},
               'smoke': {'entries': len(smoke_results), 'accepted': smoke.get('accepted')},
               'dependencies': {'imports': sorted(imports), 'vendor': vendor},
               'pkgconfig': {'packages': pkgconfig.get('packages'),
                             'consumer': pkgconfig.get('consumer'),
                             'outside_paths': pkgconfig.get('outside_paths')},
               'negative_cases': [entry['name'] for entry in negatives.get('results', [])],
               'results': results}
    distlib.write_json(args.output, summary)
    print(json.dumps({'accepted': True, 'results': len(results)}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
