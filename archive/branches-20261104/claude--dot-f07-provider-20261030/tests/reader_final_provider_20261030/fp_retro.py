"""Retrospective authentication of the original 47-finding artifact (Actions only).

Two runs are authenticated and analysed *separately*: the original failing run (source A) and a
later passing run (source B). Nothing here merges them into a same-source claim.
"""
import io
import json
from pathlib import Path
import stat
import sys
import zipfile

import fp_core as C
import fp_maps as M

WORKFLOW_PATH = C.WORKFLOW
PINS = dict(
    original=dict(run=41027746036, attempt=1, source='05960b2601d2a8c6f2a77ed16f9c41cc3d612464',
                  artifact=dict(id=12965055092, name='f07-provider-linux-41027746036-1', size=726598,
                                digest='sha256:6630b046d339027b0ae30d3d2ffa9ad8f3068972dc7090744c7d1e12222c8098')),
    later=dict(run=41029510656, attempt=1, source='eb7efb91064a57c704181742ccb99bba634f95be',
               artifact=dict(id=12965591977, name='f07-provider-linux-41029510656-1', size=727121,
                             digest='sha256:63058fde2b07ec47ef09024cb03165516306f6294e66f0f58aa276003e7c38a6')),
)
EXPECTED_ORIGINAL_FINDINGS = 47
ORIGINAL_KIND = 'sdk_entry_without_selected_sdk_owner'


def verify_identity(run, meta, raw, pin):
    """Run + artifact metadata + actual downloaded bytes must all equal the pin and each other."""
    C.require(run['id'] == pin['run'] and run['run_attempt'] == pin['attempt'], 'run/attempt differs from pin')
    C.require(run['head_sha'] == pin['source'], 'run source differs from pin')
    C.require(run['path'] == WORKFLOW_PATH and run['head_branch'] == C.BRANCH and run['status'] == 'completed',
              'run workflow/branch/status differs')
    art = pin['artifact']
    C.require(meta['id'] == art['id'] and meta['name'] == art['name'] and not meta['expired'], 'artifact id/name/expiry')
    C.require(meta['size_in_bytes'] == art['size'] and meta['digest'] == art['digest'], 'artifact metadata size/digest')
    C.require(meta['workflow_run']['id'] == pin['run'] and meta['workflow_run']['head_sha'] == pin['source'],
              'artifact belongs to a different run/source')
    C.require(len(raw) == art['size'], 'downloaded byte count differs from pin')
    C.require('sha256:' + C.sha(raw) == art['digest'], 'downloaded bytes digest differs from pin')
    return True


def safe_unpack(raw):
    """In-memory safe read of the artifact ZIP: {member: bytes}. Rejects unsafe/duplicate/special members."""
    files, total = {}, 0
    with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
        for info in bundle.infolist():
            name = info.filename[:-1] if info.is_dir() else info.filename
            C.safe_name(name)
            mode = (info.external_attr >> 16) & 0o170000
            C.require(mode in (0, stat.S_IFREG, stat.S_IFDIR), 'special archive member: ' + name)
            C.require(not (info.flag_bits & 1), 'encrypted member')
            if info.is_dir():
                continue
            C.require(name not in files, 'duplicate member: ' + name)
            total += info.file_size
            C.require(info.file_size <= 512 * 1024**2 and total <= 2 * 1024**3, 'excessive archive')
            files[name] = bundle.read(info)
    return files


def unique(files, suffix):
    found = [n for n in files if n == suffix or n.endswith('/' + suffix)]
    C.require(len(found) == 1, 'expected exactly one %s, found %d' % (suffix, len(found)))
    return found[0]


def sets_of(evidence):
    archives = {a: {m: {k: set(v) for k, v in row.items()} for m, row in t.items()}
                for a, t in evidence['archives'].items()}
    return archives, {tuple(x) for x in evidence['selected']}


def classify_original(finding, evidence):
    """Classify one preserved finding from the same artifact's own map selection and native tables."""
    base = dict(finding=finding)
    if finding.get('kind') != ORIGINAL_KIND or not str(finding.get('symbol', '')).startswith('sqlite3'):
        return dict(base, status='pending', reason='finding kind/symbol outside the evidence-backed sqlite class')
    try:
        archives, selected = sets_of(evidence)
        roles = evidence['roles']
        consumer = tuple(finding['consumer'])
        symbol = finding['symbol']
        owned = set(evidence['product_catalog_archives'])
    except KeyError as error:
        return dict(base, status='pending', reason='evidence field absent: %s' % error)
    if consumer not in selected:
        return dict(base, status='pending', reason='consumer not in the final map selection')
    defining = [(a, m) for a, t in archives.items() for m, row in t.items() if symbol in row['defined']]
    chosen = [d for d in defining if d in selected]
    unselected = [d for d in defining if d not in selected]
    detail = dict(selected_definers=[list(d) for d in chosen], unselected_candidates=[list(d) for d in unselected])
    if not chosen:
        return dict(base, status='GENUINE_PROBLEM', reason='no selected definer for the referenced symbol', **detail)
    if len(chosen) > 1 or any(M.classify(a, roles) != 'product' or a.rsplit('/', 1)[-1] not in owned for a, _ in chosen):
        return dict(base, status='GENUINE_PROBLEM', reason='selected provider is not the single ProductCatalog owner', **detail)
    if not unselected:
        return dict(base, status='pending', reason='no installed alternative recorded; cannot show why the rule fired', **detail)
    return dict(base, status='rule_defect_resolved_by_selected_product',
                reason='single selected ProductCatalog definer; installed alternative(s) not selected', **detail)


def cross_check(finding, later_rows):
    """Evidence from a DIFFERENT source; reported separately, never merged."""
    key = (tuple(finding['consumer']), finding['symbol'])
    row = later_rows.get(key)
    if row is None:
        return dict(same_source=False, status='pending', reason='no corresponding reference row in later artifact')
    return dict(same_source=False, status=row['status'], selected_definers=row['selected_definers'],
                unselected_candidates=row['unselected_candidates'])


def analyse(original_files, later_files):
    result = json.loads(original_files[unique(original_files, 'final-provider/linux/result.json')])
    evidence = json.loads(original_files[unique(original_files, 'final-provider/linux/evidence.json')])
    findings = result['findings']
    C.require(len(findings) == EXPECTED_ORIGINAL_FINDINGS and result['passed'] is False,
              'original artifact does not contain the preserved 47 findings')
    later = json.loads(later_files[unique(later_files, 'final-provider/linux/result.json')])
    rows = {(tuple(r['consumer']), r['symbol']): r for r in later['sqlite_references']}
    table = []
    for finding in findings:
        entry = classify_original(finding, evidence)
        entry['later_source_cross_check'] = cross_check(finding, rows)
        table.append(entry)
    counts = {}
    for entry in table:
        counts[entry['status']] = counts.get(entry['status'], 0) + 1
    return dict(findings=table, original_status_counts=counts,
                later_status_counts={k: sum(1 for e in table if e['later_source_cross_check']['status'] == k)
                                     for k in sorted({e['later_source_cross_check']['status'] for e in table})},
                original_passed=result['passed'], later_passed=later['passed'])


def tamper_checks(run, meta, raw, pin):
    """Live negative controls: every mutation of identity or bytes must be rejected."""
    import copy
    verify_identity(run, meta, raw, pin)  # untampered baseline must pass, or rejections prove nothing
    rejected = []

    def expect(label, change):
        r, m, p, holder = copy.deepcopy(run), copy.deepcopy(meta), copy.deepcopy(pin), [bytes(raw)]
        change(r, m, holder, p)
        try:
            verify_identity(r, m, holder[0], p)
        except ValueError:
            rejected.append(label)
            return
        raise AssertionError('tampered identity accepted: ' + label)

    def flip(r, m, b, p): b[0] = b[0][:100] + bytes([b[0][100] ^ 1]) + b[0][101:]
    def trunc(r, m, b, p): b[0] = b[0][:-1]
    def digest(r, m, b, p): p['artifact']['digest'] = 'sha256:' + '0' * 64
    def size(r, m, b, p): p['artifact']['size'] += 1
    def aid(r, m, b, p): m['id'] += 1
    def name(r, m, b, p): m['name'] = m['name'] + 'x'
    def source(r, m, b, p): r['head_sha'] = '0' * 40
    def run_id(r, m, b, p): m['workflow_run']['id'] += 1
    def attempt(r, m, b, p): r['run_attempt'] = 2
    def expired(r, m, b, p): m['expired'] = True
    for label, change in (('flipped_byte', flip), ('truncated', trunc), ('pin_digest', digest), ('pin_size', size),
                          ('artifact_id', aid), ('artifact_name', name), ('run_source', source),
                          ('artifact_run', run_id), ('attempt', attempt), ('expired', expired)):
        expect(label, change)
    return rejected


def main():
    C.actions_only()
    sys.path.insert(0, str(C.ROOT / 'tools'))
    from check_parallel_integration import download_artifact_zip, fetch
    out = C.OUT / 'retro'
    out.mkdir(parents=True, exist_ok=True)
    report = dict(C.identity('linux', '3.42.0'), f07_accepted=False, full_six_platform_f07_accepted=False,
                  same_source_claim=False, pins=PINS)
    try:
        files = {}
        for label, pin in PINS.items():
            run = fetch('actions/runs/%d/attempts/%d' % (pin['run'], pin['attempt']))
            meta = fetch('actions/artifacts/%d' % pin['artifact']['id'])
            path = out / (label + '-artifact.zip')
            with path.open('w+b') as stream:
                download_artifact_zip(pin['artifact']['id'], output=stream)
            raw = path.read_bytes()
            verify_identity(run, meta, raw, pin)
            report[label] = dict(run_id=run['id'], attempt=run['run_attempt'], source=run['head_sha'],
                                 artifact=dict(id=meta['id'], name=meta['name'], size=len(raw), sha256=C.sha(raw)),
                                 conclusion=run['conclusion'])
            report[label + '_tamper_rejected'] = tamper_checks(run, meta, raw, pin)
            files[label] = safe_unpack(raw)
        analysis = analyse(files['original'], files['later'])
        report['analysis'] = analysis
        C.require(not any(e['status'] == 'GENUINE_PROBLEM' for e in analysis['findings']),
                  'genuine provider problem classified in the original 47')
    except Exception as error:
        report['failure'] = str(error)
        raise
    finally:
        C.save(out / 'retro-result.json', report)
        if 'analysis' in report:
            print('original status counts:', json.dumps(report['analysis']['original_status_counts']))
            print('later-source cross-check counts:', json.dumps(report['analysis']['later_status_counts']))
        for label in PINS:
            if label in report:
                print(label, json.dumps(report[label], sort_keys=True))
