"""Authenticate original same-attempt ZIP using D14; then require D19 receipts."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import traceback
import zipfile
from reuse import ROOT, source
from contract import write

# Exact historical ZIP/member/program/expiry/action/dwell judge; only naming
# points to this workflow's actual GTK producer. No old result is imported.
raw = source('authenticate.py').decode()
changes = [("f'd14-{platform}-", "f'd19-{platform}-"), ("'D14_AUTH '", "'D19_ORIGINAL_JUDGE '")]
adapted = raw
for before, after in changes:
    assert adapted.count(before) == 1
    adapted = adapted.replace(before, after)
reversed_source = adapted
for before, after in reversed(changes):
    reversed_source = reversed_source.replace(after, before)
assert reversed_source == raw
namespace = dict(globals(), __name__='__main__')
judge_error = None
try:
    exec(compile(adapted, 'D19-naming-only/immutable-D14-authenticate.py', 'exec'), namespace)
except BaseException:
    judge_error = traceback.format_exc()
report = namespace.get('report', dict(accepted=False, failures=[judge_error]))
report['d19_receipts_accepted'] = False
report['identity_projection'] = dict(original='93c2f583c7e54eb2aebcba13a18b532bd0a967f5',
    immutable_authenticate_sha256=hashlib.sha256(raw.encode()).hexdigest(), naming_substitutions=changes,
    reverse_projection_exact=True, reused_old_acceptance=False)

def check(timeline, before, after, identity):
    def one(event):
        rows = [r for r in timeline if r['event'] == event]
        assert len(rows) == 1, (event, len(rows))
        return rows[0]
    live = [r for r in timeline if r['event'] == 'host-live']
    assert len(live) == 2 and [r['stage'] for r in live] == [1, 2]
    assert len({r['host_pid'] for r in live}) == 2
    assert all(r['host_alive'] and r['controller_alive'] and r['detail']['program_sha256'] == identity['program_sha256'] for r in live)
    assert all(any(t['name'] == 'reading' for t in r['threads']) for r in live), 'real worker task receipt absent'
    assert not live[1]['detail']['previous_host_alive'] and live[1]['detail']['previous_host_pid'] == live[0]['host_pid']
    events = ['original-processing-txt-imported', 'phase-monitor-armed', 'processing-live', 'native-close-request', 'native-close-sent', 'processing-host-exited', 'reopen-no-replay']
    rows = [one(e) for e in events]
    assert [r['monotonic_seconds'] for r in rows] == sorted(r['monotonic_seconds'] for r in rows)
    for row in rows[:4]:
        assert row['host_alive'] and row['controller_alive'] and row['host_pid'] == live[0]['host_pid']
    for value in (one('processing-live')['detail']['search'], one('native-close-request')['detail']['close_precondition']):
        assert value['phase'] == '2' and value['running'] == '1' and int(value['polls']) > 0
    assert one('processing-host-exited')['exit_code'] == 0 and not one('processing-host-exited')['host_alive']
    assert one('reopen-no-replay')['host_pid'] == live[1]['host_pid'] and one('reopen-no-replay')['host_alive']
    for value in (before, after):
        assert value['count'] == 6 and all(b['catalog_matched'] for b in value['books'])
        assert value['host_exit_code'] == 0 and value['program_sha256'] == identity['catalog_program_sha256']
        assert value['source_sha'] == identity['harness'] and all(value[k] == identity[k] for k in ('run', 'attempt'))
        assert sorted(value['expected_originals'].values()) == sorted(b['sha256'] for b in value['books'])
    keys = lambda value: sorted((b['id'], b['format'], b['bytes'], b['sha256']) for b in value['books'])
    assert keys(before) == keys(after), 'real SDK/catalog originals changed across reopening'
    return True

try:
    assert judge_error is None, judge_error
    assert namespace['run']['path'].split('@')[0] == '.github/workflows/reader-wave3-d19.yml'
    assert all(j['head_sha'] == report['harness'] and str(j['run_attempt']) == report['attempt'] for j in report['jobs'])
    record = report['platforms']['gtk']
    # Independently read the same original ZIP again in Actions, not local tooling.
    raw_zip = namespace['download_artifact_zip'](record['artifact_id'])
    assert hashlib.sha256(raw_zip).hexdigest() == record['sha256'] and len(raw_zip) == record['bytes']
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as archive:
        load = lambda name: json.loads(archive.read(name))
        identity = load('build-identity.json')
        timeline, before, after = load('pid-phase-timeline.json'), load('before-reopen-catalog.json'), load('after-final-close-catalog.json')
        assert hashlib.sha256(archive.read('d19-catalog')).hexdigest() == identity['catalog_program_sha256']
        check(timeline, before, after, identity)
        refused = []
        for name in ('missing-second-host', 'no-live-phase', 'missing-worker', 'catalog-source-mismatch'):
            broken_timeline, broken_after = copy.deepcopy(timeline), copy.deepcopy(after)
            if name == 'missing-second-host':
                broken_timeline = [r for r in broken_timeline if not (r['event'] == 'host-live' and r['stage'] == 2)]
            elif name == 'no-live-phase':
                next(r for r in broken_timeline if r['event'] == 'processing-live')['detail']['search']['phase'] = '3'
            elif name == 'missing-worker':
                next(r for r in broken_timeline if r['event'] == 'host-live')['threads'] = []
            else:
                broken_after['books'][0]['sha256'] = '0'*64
            try:
                check(broken_timeline, before, broken_after, identity)
            except AssertionError:
                refused.append(name)
            else:
                raise AssertionError('D19 negative accepted: '+name)
        report.update(d19_receipts_accepted=True, d19_negative_controls=refused,
                      host_pids=[r['host_pid'] for r in timeline if r['event']=='host-live'],
                      catalog_originals=after['books'], catalog_program_sha256=identity['catalog_program_sha256'],
                      phase_receipts=[r for r in timeline if r['event'] in ('processing-live','native-close-sent','processing-host-exited','reopen-no-replay')])
except BaseException:
    report['accepted'] = False
    report.setdefault('failures', []).append(traceback.format_exc())
finally:
    write(Path('authentication/authentication.json'), report)
    print('D19_FINAL_AUTH '+json.dumps(report), flush=True)
assert report.get('accepted') and report['d19_receipts_accepted'], 'D19 incomplete; failures and original ZIP retained'
