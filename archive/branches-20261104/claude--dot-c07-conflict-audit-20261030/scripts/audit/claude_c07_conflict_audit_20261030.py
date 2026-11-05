#!/usr/bin/env python3
"""Independent C07 verifier for the F05-remaining native GTK Receive / delete-versus-update evidence.

Deliberately shares no code with the producer or the C03 author validator.  It (1) authenticates the
original GitHub Actions artifact ZIP (run, attempt, head SHA, size, digest, job/step conclusions), (2) re-derives
every verdict from the raw preserved files, and (3) proves the verifier itself with an identity control and
negative controls on synthetic evidence.  The synthetic controls validate this script only; they are never
product evidence.  Runs in GitHub Actions only.  Standard library plus the preinstalled gh CLI.
"""
import argparse
import copy
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

CHECKS = [
    'native_receive_projects_received_group_into_peerB_collections',
    'native_delete_and_rename_create_distinct_siblings_of_exact_common_head',
    'native_delete_versus_update_converges_without_automatic_winner',
    'synthetic_credentials_absent_from_preserved_evidence',
]
# restore8 = source 73ac5ca9 profile: the four checks above plus real book delete, restart restore and the 4096-character boundary
CHECKS8 = CHECKS[:3] + [
    'over_4096_characters_is_rejected_without_new_revision',
    'native_book_delete_retains_tombstone_and_revision_history',
    'native_removed_books_restore_after_restart_preserves_delete_parent',
    'restore_preserves_4096_multibyte_fields_and_distinct_sort_exactly',
    CHECKS[3],
]
PROFILES = {'receive4': CHECKS, 'restore8': CHECKS8}
METADATA_RESULT = 'f05-metadata-regression-evidence/result.json'
SHA40 = re.compile(r'^[0-9a-f]{40}$')
SHA64 = re.compile(r'^[0-9a-f]{64}$')
PEM = re.compile(rb'-----BEGIN [A-Z ]*PRIVATE KEY-----')
BASIC = re.compile(rb'(?i)authorization["\s:=]+basic\s+[A-Za-z0-9+/=]{8,}')
MAX_ENTRIES, MAX_BYTES = 500, 256 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Ledger:
    def __init__(self):
        self.rows = []

    def add(self, name, ok, detail='', gating=True):
        self.rows.append({'name': name, 'ok': bool(ok), 'gating': gating, 'detail': str(detail)[:300]})

    def guard(self, name, fn, gating=True):
        try:
            res = fn()
            ok, detail = res if isinstance(res, tuple) else (res, '')
        except Exception as error:  # malformed evidence is a rejection, never a crash
            ok, detail = False, '%s: %s' % (type(error).__name__, error)
        self.add(name, ok, detail, gating)

    def failed(self):
        return [r['name'] for r in self.rows if r['gating'] and not r['ok']]


def pick(files, suffix):
    hits = [n for n in files if n == suffix or n.endswith('/' + suffix)]
    if len(hits) != 1:
        raise ValueError('expected exactly one %s, found %d' % (suffix, len(hits)))
    return files[hits[0]]


def build_evidence(files, profile='receive4'):
    """Raises ValueError when any required file is absent: missing evidence is refused, never assumed."""
    ev = {'result': json.loads(pick(files, 'f05-host-live-evidence/result.json')),
          'requests': json.loads(pick(files, 'f05-host-live-evidence/requests.json')),
          'wire': json.loads(pick(files, 'f05-host-live-evidence/wire.json')),
          'build_bytes': pick(files, 'f05-package/build.json'),
          'consumer_bytes': pick(files, 'f05-revision-consumer/revision-consumer'),
          'files': files}
    if profile == 'restore8':
        ev['metadata'] = json.loads(pick(files, METADATA_RESULT))
    return ev


def extract(zip_bytes):
    out, total = {}, 0
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        infos = z.infolist()
        if len(infos) > MAX_ENTRIES:
            raise ValueError('too many entries')
        for info in infos:
            p = PurePosixPath(info.filename)
            if p.is_absolute() or '..' in p.parts or '\\' in info.filename:
                raise ValueError('unsafe member ' + info.filename)
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('symlink member ' + info.filename)
            if info.is_dir():
                continue
            total += info.file_size
            if total > MAX_BYTES:
                raise ValueError('archive too large')
            out[info.filename] = z.read(info)
    return out


def authenticate(meta, zip_bytes, expect, profile='receive4'):
    """meta = {'run': .., 'jobs': .., 'artifact': ..} straight from the GitHub API."""
    L = Ledger()
    run, art = meta['run'], meta['artifact']
    name = 'f05-remaining-%s-%s' % (expect['run_id'], expect['attempt'])
    L.guard('api.run_completed_success', lambda: (run['status'] == 'completed' and run['conclusion'] == 'success',
                                                  '%s/%s' % (run.get('status'), run.get('conclusion'))))
    L.guard('api.run_identity', lambda: (str(run['id']) == str(expect['run_id']) and
                                         str(run['run_attempt']) == str(expect['attempt']) and
                                         run['head_sha'] == expect['sha'], run.get('head_sha')))
    L.guard('api.artifact_identity', lambda: (str(art['id']) == str(expect['artifact_id']) and art['name'] == name and
                                              not art['expired'] and
                                              str(art['workflow_run']['id']) == str(expect['run_id']) and
                                              art['workflow_run']['head_sha'] == expect['sha'], art.get('name')))
    L.guard('api.artifact_size', lambda: (art['size_in_bytes'] == len(zip_bytes), '%s vs %d' % (art['size_in_bytes'], len(zip_bytes))))
    L.guard('api.artifact_digest', lambda: (art['digest'] == 'sha256:' + sha(zip_bytes), art.get('digest')))
    jobs = meta['jobs']['jobs']
    L.guard('api.host_job_all_steps_success', lambda: (
        len([j for j in jobs if j['name'].startswith('actual GTK host')]) == 1 and
        all(j['conclusion'] == 'success' and all(s['conclusion'] in ('success', 'skipped') for s in j['steps'])
            for j in jobs if j['name'].startswith('actual GTK host')) and
        any(s['name'].startswith('Native Receive projects group') and s['conclusion'] == 'success'
            for j in jobs for s in j['steps']), [j['name'] for j in jobs]))
    if profile == 'restore8':
        L.guard('api.metadata_regression_step_success', lambda: any(
            s['name'].startswith('Preserve unchanged installed metadata regression') and s['conclusion'] == 'success'
            for j in jobs for s in j['steps']))
    try:
        extract(zip_bytes)
        L.add('zip.safe_members', True)
    except Exception as error:
        L.add('zip.safe_members', False, error)
    return L


def audit(ev, expect, profile='receive4'):
    L = Ledger()
    r = ev['result']
    names = PROFILES[profile]
    obs = lambda i: r['observations'][CHECKS[i]]
    ids = lambda: (obs(1)['delete_revision'], obs(1)['update_revision'], obs(1)['common'])
    g = L.guard

    g('identity.accepted_true', lambda: r['accepted'] is True)
    g('identity.source_sha', lambda: (r['source_sha'] == expect['sha'] and SHA40.match(r['source_sha']) is not None, r['source_sha']))
    g('identity.run_and_attempt', lambda: (str(r['run_id']) == str(expect['run_id']) and
                                           str(r['attempt']) == str(expect['attempt']), '%s/%s' % (r['run_id'], r['attempt'])))
    g('identity.linux_runner', lambda: r['runner_os'] == 'Linux')
    g('scope.no_overclaim', lambda: all(r[k] is False for k in ('database_planting', 'six_platform_claim',
                                                                  'complete_product', 'complete_f05')) and
      r['book_delete_restore']['accepted'] is (profile == 'restore8'))
    g('scope.host_is_actual_gtk', lambda: 'GTK' in r['host'] and 'exreader-linux' in r['host'] and 'two' in r['host'])
    g('checks.exact_four_with_observations', lambda: r['checks'] == names and r['count'] == len(names) and
      all(c in r['observations'] for c in names[:-1]))
    g('hash.build_json_rehash', lambda: r['build_json_sha256'] == sha(ev['build_bytes']))
    g('hash.revision_consumer_rehash', lambda: r['revision_consumer_sha256'] == sha(ev['consumer_bytes']))
    g('hash.program_sha_well_formed', lambda: SHA64.match(r['program_sha256']) is not None)
    g('hash.program_sha_listed_in_build_json', lambda: r['program_sha256'].encode() in ev['build_bytes'], gating=False)
    g('ui.gtk_build_log_present', lambda: b'gtk' in pick(ev['files'], 'f05-logs/host-build.log').lower())

    def receive():
        o = obs(0)
        listed = o['after_group_ids'].split(',')
        ok = (o['before_projected'] is False and o['group_key'] in listed and int(o['account']['receive_seen']) > 0)
        return ok, 'receive_seen=%s' % o['account'].get('receive_seen')
    g('receive.real_click_projects_group_after_absence', receive)

    def siblings():
        d, u, c = ids()
        vals = [d, u, *c]
        return (isinstance(c, list) and len(c) > 0 and d != u and not ({d, u} & set(c)) and
                all(isinstance(v, str) and v for v in vals)), '%s %s' % (d, u)
    g('conflict.distinct_siblings_of_common_head', siblings)

    def unsafe_heads():
        d, u, c = ids()
        o = obs(2)
        dumped = json.dumps(o['heads'])
        safe = o['graph']['projection_safe']
        return (o['graph']['heads'] == 2 and not safe and safe is not None and len(o['heads']) == 2 and
                d in dumped and u in dumped and not any(x in dumped for x in c)), dumped
    g('conflict.two_peer_unsafe_two_heads_no_winner', unsafe_heads)

    def wire_history():
        d, u, _ = ids()
        w = obs(2)['wire']
        paths = {k: (w[k][0] if isinstance(w[k], (list, tuple)) else w[k]) for k in (d, u)}
        pd, pu = paths[d], paths[u]
        in_wire = pd != pu and all(p in ev['wire'] and SHA64.match(ev['wire'][p]) for p in (pd, pu))

        def hit(peer, method, path):
            for q in ev['requests']:
                if (q.get('peer') == peer and q.get('method') == method and str(q.get('path', '')).startswith(path)
                        and q.get('status', 200) < 400):
                    return True
            return False
        flow = (hit('peerA', 'PUT', pd) and hit('peerB', 'PUT', pu) and
                hit('peerB', 'GET', pd) and hit('peerA', 'GET', pu))
        return in_wire and flow, 'wire_known=%s flow=%s' % (in_wire, flow)
    g('wire.both_siblings_put_by_author_and_fetched_by_other_peer', wire_history)

    def secrets():
        bad = [n for n, data in ev['files'].items() if n.endswith('.key') or PEM.search(data) or BASIC.search(data)]
        return not bad and r['credential_leak_hits'] == 0, bad
    g('secrets.no_key_material_or_basic_auth_in_artifact', secrets)

    if profile == 'restore8':
        o = lambda i: r['observations'][CHECKS8[i]]

        def delete_restore():
            bd, rest = r['book_delete_restore'], o(5)
            dele, back = o(4)['revision'], rest['restore_revision']
            return (bd['restart'] is True and bd['delete_revision'] == dele == rest['deleted_revision'] and
                    bd['restore_revision'] == back and dele != back and
                    all(isinstance(v, str) and v for v in (dele, back)) and
                    'native book delete and restart restore' in r['scope'] and 'Linux' in r['scope']), '%s -> %s' % (dele, back)
        g('restore.real_delete_then_restart_restore_with_distinct_parent_link', delete_restore)
        g('multibyte.5000_characters_refused_without_new_revision', lambda: o(3)['rejected_characters'] > 4096)
        g('multibyte.4096_boundary_bytes_and_no_sql_setup', lambda: (
            o(6)['title_bytes'] == 4096 * 3 and o(6)['author_bytes'] == 4096 * 3 and 'no SQL mutation' in o(6)['setup']))
        m = ev['metadata'] if 'metadata' in ev else None
        g('metadata.regression_same_source_run_attempt', lambda: (
            m['accepted'] is True and m['source_sha'] == expect['sha'] and str(m['run_id']) == str(expect['run_id']) and
            str(m['attempt']) == str(expect['attempt']) and str(m['platform']).startswith('linux')))
        g('metadata.regression_29_unique_checks_unchanged', lambda: (
            m['count'] == 29 and len(m['checks']) == 29 and len(set(m['checks'])) == 29))
        g('metadata.regression_not_a_ui_claim', lambda: m['native_adapter_only'] is True and m['desktop_ui_accepted'] is False)
        L.add('limit.restart_and_sort_exactness_are_producer_assertions', True,
              'artifact holds no process or SQL record; deletion, restart, restore and sort equality rest on the producer assertions '
              'plus consistent observations', gating=False)
    return L


def make_good(expect, profile='receive4'):
    d, u, c = 'rev-delete-' + 'd' * 8, 'rev-update-' + 'e' * 8, ['rev-common-' + 'c' * 8]
    pd, pu = '/dav/revisions/%s.json' % d, '/dav/revisions/%s.json' % u
    build = b'{"binary":"exreader-linux","program_sha256":"' + b'7' * 64 + b'","gtk":true}'
    consumer = b'\x7fELF synthetic consumer'
    result = {
        'accepted': True, 'source_sha': expect['sha'], 'run_id': str(expect['run_id']), 'attempt': str(expect['attempt']),
        'runner_os': 'Linux', 'program_sha256': '7' * 64, 'build_json_sha256': sha(build),
        'revision_consumer_sha256': sha(consumer), 'host': 'actual GTK exreader-linux, two independent profiles',
        'checks': list(CHECKS), 'count': 4, 'database_planting': False, 'six_platform_claim': False,
        'complete_product': False, 'complete_f05': False, 'book_delete_restore': {'accepted': False},
        'credential_leak_hits': 0,
        'observations': {
            CHECKS[0]: {'before_projected': False, 'after_group_ids': 'g-other,g-1', 'group_key': 'g-1',
                        'account': {'receive_seen': '3'}},
            CHECKS[1]: {'delete_revision': d, 'update_revision': u, 'common': c},
            CHECKS[2]: {'graph': {'heads': 2, 'projection_safe': False},
                        'heads': [{'id': d}, {'id': u}], 'wire': {d: [pd, 1], u: [pu, 1]}}}}
    requests = [{'peer': 'peerA', 'method': 'PUT', 'path': pd, 'status': 201},
                {'peer': 'peerB', 'method': 'GET', 'path': pd, 'status': 200},
                {'peer': 'peerB', 'method': 'PUT', 'path': pu, 'status': 201},
                {'peer': 'peerA', 'method': 'GET', 'path': pu, 'status': 200}]
    files = {'f05-host-live-evidence/result.json': json.dumps(result).encode(),
             'f05-host-live-evidence/requests.json': json.dumps(requests).encode(),
             'f05-host-live-evidence/wire.json': json.dumps({pd: 'a' * 64, pu: 'b' * 64}).encode(),
             'f05-package/build.json': build, 'f05-revision-consumer/revision-consumer': consumer,
             'f05-logs/host-build.log': b'cc -o gtk-host/exreader-linux main.o -lgtk-3'}
    if profile == 'restore8':
        delete_rev, restore_rev = 'rev-bookdel-' + '1' * 8, 'rev-restore-' + '2' * 8
        result.update(checks=list(CHECKS8), count=8,
                      scope='native Receive and group delete versus update; native book delete and restart restore; Linux only',
                      book_delete_restore={'accepted': True, 'delete_revision': delete_rev,
                                           'restore_revision': restore_rev, 'restart': True})
        result['observations'].update({
            CHECKS8[3]: {'rejected_characters': 5000},
            CHECKS8[4]: {'revision': delete_rev},
            CHECKS8[5]: {'restore_revision': restore_rev, 'deleted_revision': delete_rev},
            CHECKS8[6]: {'title_bytes': 12288, 'author_bytes': 12288,
                         'setup': 'installed public typed command; no SQL mutation'}})
        files['f05-host-live-evidence/result.json'] = json.dumps(result).encode()
        files[METADATA_RESULT] = json.dumps({
            'accepted': True, 'source_sha': expect['sha'], 'run_id': str(expect['run_id']), 'attempt': int(expect['attempt']),
            'platform': 'linux', 'count': 29, 'checks': ['m%d' % i for i in range(29)],
            'native_adapter_only': True, 'desktop_ui_accepted': False}).encode()
    return files


def reencode(files, edit, profile='receive4'):
    ev = build_evidence(files, profile)
    edit(ev)
    files = dict(files)
    for key, name in (('result', 'f05-host-live-evidence/result.json'), ('requests', 'f05-host-live-evidence/requests.json'),
                      ('wire', 'f05-host-live-evidence/wire.json'), ('metadata', METADATA_RESULT)):
        if key in ev:
            files[name] = json.dumps(ev[key]).encode()
    return files


def selftest(expect):
    """Controls for both profiles; the receive4 controls preserve every earlier finding unchanged."""
    return [dict(row, control='%s:%s' % (p, row['control'])) for p in PROFILES for row in controls(expect, p)]


def refuses(files, profile):
    try:
        build_evidence(files, profile)
    except (ValueError, KeyError):
        return True
    return False


def controls(expect, profile):
    """Identity control must pass; every negative control must fail the specific named check."""
    rows, good = [], make_good(expect, profile)
    L = audit(build_evidence(good, profile), expect, profile)
    rows.append({'control': 'identity', 'expect': 'all gating checks pass', 'ok': not L.failed(), 'failed': L.failed()})

    def res(ev):
        return ev['result']
    obs = lambda ev, i: ev['result']['observations'][CHECKS[i]]
    cases = [
        ('not_accepted', 'identity.accepted_true', lambda e: res(e).update(accepted=False)),
        ('wrong_sha', 'identity.source_sha', lambda e: res(e).update(source_sha='0' * 40)),
        ('wrong_run', 'identity.run_and_attempt', lambda e: res(e).update(run_id='2')),
        ('wrong_attempt', 'identity.run_and_attempt', lambda e: res(e).update(attempt='2')),
        ('non_linux', 'identity.linux_runner', lambda e: res(e).update(runner_os='macOS')),
        ('database_planting', 'scope.no_overclaim', lambda e: res(e).update(database_planting=True)),
        ('overclaim_complete', 'scope.no_overclaim', lambda e: res(e).update(complete_f05=True)),
        ('not_gtk', 'scope.host_is_actual_gtk', lambda e: res(e).update(host='python fixture driver')),
        ('missing_check', 'checks.exact_four_with_observations', lambda e: res(e)['checks'].pop(2)),
        ('stale_build_hash', 'hash.build_json_rehash', lambda e: res(e).update(build_json_sha256='1' * 64)),
        ('stale_consumer_hash', 'hash.revision_consumer_rehash', lambda e: res(e).update(revision_consumer_sha256='2' * 64)),
        ('receive_never_clicked', 'receive.real_click_projects_group_after_absence',
         lambda e: obs(e, 0)['account'].update(receive_seen='0')),
        ('group_already_projected', 'receive.real_click_projects_group_after_absence',
         lambda e: obs(e, 0).update(before_projected=True)),
        ('group_missing_after_receive', 'receive.real_click_projects_group_after_absence',
         lambda e: obs(e, 0).update(after_group_ids='g-other')),
        ('same_revision_both_sides', 'conflict.distinct_siblings_of_common_head',
         lambda e: obs(e, 1).update(update_revision=obs(e, 1)['delete_revision'])),
        ('sibling_is_common_head', 'conflict.distinct_siblings_of_common_head',
         lambda e: obs(e, 1).update(common=[obs(e, 1)['delete_revision']])),
        ('single_head', 'conflict.two_peer_unsafe_two_heads_no_winner',
         lambda e: (obs(e, 2)['graph'].update(heads=1), obs(e, 2).update(heads=obs(e, 2)['heads'][:1]))),
        ('projection_safe', 'conflict.two_peer_unsafe_two_heads_no_winner',
         lambda e: obs(e, 2)['graph'].update(projection_safe=True)),
        ('missing_projection_flag', 'conflict.two_peer_unsafe_two_heads_no_winner',
         lambda e: obs(e, 2)['graph'].update(projection_safe=None)),
        ('wire_path_unhashed', 'wire.both_siblings_put_by_author_and_fetched_by_other_peer',
         lambda e: e['wire'].clear()),
        ('no_peer_fetch', 'wire.both_siblings_put_by_author_and_fetched_by_other_peer',
         lambda e: e.update(requests=[q for q in e['requests'] if q['method'] != 'GET'])),
        ('failed_status', 'wire.both_siblings_put_by_author_and_fetched_by_other_peer',
         lambda e: e['requests'][0].update(status=500)),
        ('credential_hits', 'secrets.no_key_material_or_basic_auth_in_artifact',
         lambda e: res(e).update(credential_leak_hits=1)),
    ]
    for label, want, edit in cases:
        try:
            ev = build_evidence(reencode(good, edit, profile), profile)
            L = audit(ev, expect, profile)
            failed = L.failed()
        except Exception as error:  # a crash in the control harness is a failed control
            failed = ['harness crash %s' % error]
        rows.append({'control': label, 'expect': want, 'ok': want in failed, 'failed': failed})

    for label, want, mutate in (
            ('basic_auth_in_log', 'secrets.no_key_material_or_basic_auth_in_artifact',
             lambda f: f.update({'f05-logs/x.log': b'Authorization: Basic dXNlcjpwYXNzd29yZA=='})),
            ('private_key_file', 'secrets.no_key_material_or_basic_auth_in_artifact',
             lambda f: f.update({'f05-host-live-evidence/ca.key': b'k'})),
            ('no_gtk_build_log', 'ui.gtk_build_log_present',
             lambda f: f.update({'f05-logs/host-build.log': b'python3 fixture.py'}))):
        files = dict(good)
        mutate(files)
        failed = audit(build_evidence(files, profile), expect, profile).failed()
        rows.append({'control': label, 'expect': want, 'ok': want in failed, 'failed': failed})

    if profile == 'restore8':
        bd = lambda e: e['result']['book_delete_restore']
        o8 = lambda e, i: e['result']['observations'][CHECKS8[i]]
        extra = [
            ('book_delete_restore_not_accepted', 'scope.no_overclaim', lambda e: bd(e).update(accepted=False)),
            ('no_restart_recorded', 'restore.real_delete_then_restart_restore_with_distinct_parent_link',
             lambda e: bd(e).update(restart=False)),
            ('restore_revision_equals_delete', 'restore.real_delete_then_restart_restore_with_distinct_parent_link',
             lambda e: o8(e, 5).update(restore_revision=o8(e, 4)['revision'])),
            ('result_delete_revision_differs', 'restore.real_delete_then_restart_restore_with_distinct_parent_link',
             lambda e: bd(e).update(delete_revision='other')),
            ('restore_observation_missing_parent', 'restore.real_delete_then_restart_restore_with_distinct_parent_link',
             lambda e: o8(e, 5).pop('deleted_revision')),
            ('restore_check_missing', 'checks.exact_four_with_observations', lambda e: e['result']['checks'].pop(5)),
            ('oversize_not_actually_oversize', 'multibyte.5000_characters_refused_without_new_revision',
             lambda e: o8(e, 3).update(rejected_characters=4096)),
            ('boundary_title_truncated', 'multibyte.4096_boundary_bytes_and_no_sql_setup',
             lambda e: o8(e, 6).update(title_bytes=4096)),
            ('boundary_set_by_sql', 'multibyte.4096_boundary_bytes_and_no_sql_setup',
             lambda e: o8(e, 6).update(setup='direct SQL update')),
            ('metadata_regression_failed', 'metadata.regression_same_source_run_attempt',
             lambda e: e['metadata'].update(accepted=False)),
            ('metadata_regression_other_source', 'metadata.regression_same_source_run_attempt',
             lambda e: e['metadata'].update(source_sha='0' * 40)),
            ('metadata_regression_28_checks', 'metadata.regression_29_unique_checks_unchanged',
             lambda e: (e['metadata'].update(count=28), e['metadata']['checks'].pop())),
            ('metadata_regression_duplicate_check', 'metadata.regression_29_unique_checks_unchanged',
             lambda e: e['metadata']['checks'].__setitem__(1, e['metadata']['checks'][0])),
            ('metadata_claims_desktop_ui', 'metadata.regression_not_a_ui_claim',
             lambda e: e['metadata'].update(desktop_ui_accepted=True)),
        ]
        for label, want, edit in extra:
            try:
                failed = audit(build_evidence(reencode(good, edit, profile), profile), expect, profile).failed()
            except Exception as error:
                failed = ['harness crash %s' % error]
            rows.append({'control': label, 'expect': want, 'ok': want in failed, 'failed': failed})
        missing = {k: v for k, v in good.items() if not k.endswith(METADATA_RESULT)}
        rows.append({'control': 'missing_metadata_evidence_refused', 'expect': 'ValueError',
                     'ok': refuses(missing, 'restore8'), 'failed': []})
        no_result = {k: v for k, v in good.items() if not k.endswith('f05-host-live-evidence/result.json')}
        rows.append({'control': 'missing_host_result_refused', 'expect': 'ValueError',
                     'ok': refuses(no_result, 'restore8'), 'failed': []})
        # the older four-check artifact must not be accepted under the restore profile, and vice versa
        old = make_good(expect, 'receive4')
        rows.append({'control': 'old_four_check_artifact_refused_as_restore8', 'expect': 'ValueError',
                     'ok': refuses(old, 'restore8'), 'failed': []})
        rows.append({'control': 'restore8_artifact_rejected_as_receive4',
                     'expect': 'checks.exact_four_with_observations',
                     'ok': 'checks.exact_four_with_observations' in audit(build_evidence(good, 'receive4'), expect, 'receive4').failed(),
                     'failed': []})

    # artifact authentication controls
    z = io.BytesIO()
    with zipfile.ZipFile(z, 'w') as w:
        for n, data in good.items():
            w.writestr(n, data)
    zb = z.getvalue()
    name = 'f05-remaining-%s-%s' % (expect['run_id'], expect['attempt'])
    meta = {'run': {'id': expect['run_id'], 'run_attempt': expect['attempt'], 'status': 'completed',
                    'conclusion': 'success', 'head_sha': expect['sha']},
            'artifact': {'id': expect['artifact_id'], 'name': name, 'expired': False, 'size_in_bytes': len(zb),
                         'digest': 'sha256:' + sha(zb), 'workflow_run': {'id': expect['run_id'], 'head_sha': expect['sha']}},
            'jobs': {'jobs': [{'name': 'actual GTK host two-peer', 'conclusion': 'success',
                               'steps': [{'name': 'Native Receive projects group', 'conclusion': 'success'},
                                         {'name': 'Preserve unchanged installed metadata regression assertions',
                                          'conclusion': 'success'}]}]}}
    L = authenticate(meta, zb, expect, profile)
    rows.append({'control': 'api_identity', 'expect': 'all pass', 'ok': not L.failed(), 'failed': L.failed()})

    def with_(path, value):
        m = copy.deepcopy(meta)
        node = m
        for k in path[:-1]:
            node = node[k]
        node[path[-1]] = value
        return m
    for label, want, m, data in (
            ('run_in_progress', 'api.run_completed_success', with_(('run', 'status'), 'in_progress'), zb),
            ('run_failed', 'api.run_completed_success', with_(('run', 'conclusion'), 'failure'), zb),
            ('head_sha_differs', 'api.run_identity', with_(('run', 'head_sha'), '0' * 40), zb),
            ('artifact_id_differs', 'api.artifact_identity', with_(('artifact', 'id'), 987654321), zb),
            ('artifact_expired', 'api.artifact_identity', with_(('artifact', 'expired'), True), zb),
            ('size_differs', 'api.artifact_size', with_(('artifact', 'size_in_bytes'), 1), zb),
            ('digest_differs', 'api.artifact_digest', meta, zb + b'x'),
            ('host_job_failed', 'api.host_job_all_steps_success',
             with_(('jobs', 'jobs'), [{'name': 'actual GTK host two-peer', 'conclusion': 'failure', 'steps': []}]), zb)):
        failed = authenticate(m, data, expect, profile).failed()
        rows.append({'control': label, 'expect': want, 'ok': want in failed, 'failed': failed})
    if profile == 'restore8':
        failed = authenticate(with_(('jobs', 'jobs'), [{'name': 'actual GTK host two-peer', 'conclusion': 'success', 'steps': [
            {'name': 'Native Receive projects group', 'conclusion': 'success'}]}]), zb, expect, profile).failed()
        rows.append({'control': 'metadata_step_absent', 'expect': 'api.metadata_regression_step_success',
                     'ok': 'api.metadata_regression_step_success' in failed, 'failed': failed})
    for label, member in (('zip_traversal', '../escape.txt'), ('zip_absolute', '/abs.txt'), ('zip_backslash', 'a\\b.txt')):
        z2 = io.BytesIO()
        with zipfile.ZipFile(z2, 'w') as w:
            w.writestr(member, b'x')
        failed = authenticate(meta, z2.getvalue(), expect, profile).failed()
        rows.append({'control': label, 'expect': 'zip.safe_members', 'ok': 'zip.safe_members' in failed, 'failed': failed})
    return rows


def gh_api(path, binary=False):
    proc = subprocess.run(['gh', 'api', path], capture_output=True, check=True, timeout=300)
    return proc.stdout if binary else json.loads(proc.stdout)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--expect-sha', required=True)
    ap.add_argument('--run-id', default='')
    ap.add_argument('--attempt', default='1')
    ap.add_argument('--artifact-id', default='')
    ap.add_argument('--profile', choices=sorted(PROFILES), default='receive4')
    args = ap.parse_args()
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    args.output.mkdir(parents=True, exist_ok=True)
    expect = {'sha': args.expect_sha, 'run_id': args.run_id, 'attempt': args.attempt, 'artifact_id': args.artifact_id}
    synth = dict(expect, run_id=args.run_id or '1', attempt=args.attempt or '1', artifact_id=args.artifact_id or '1')
    controls = selftest(synth)
    report = {'verifier': 'C07 independent', 'profile': args.profile, 'controls': controls,
              'controls_all_ok': all(c['ok'] for c in controls),
              'workflow_run': os.environ.get('GITHUB_RUN_ID'), 'workflow_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
              'verifier_source_sha': os.environ.get('GITHUB_SHA'),
              'producer_audited': False, 'producer_rows': [], 'verdict': 'controls only; no producer evidence audited'}
    exit_code = 0 if report['controls_all_ok'] else 1
    if args.run_id:
        if not (args.artifact_id and SHA40.match(args.expect_sha)):
            report['verdict'] = 'REJECTED: run id supplied without artifact id and 40-hex SHA'
            exit_code = 1
        else:
            base = 'repos/%s/actions' % os.environ['GITHUB_REPOSITORY']
            meta = {'run': gh_api('%s/runs/%s/attempts/%s' % (base, args.run_id, args.attempt)),
                    'jobs': gh_api('%s/runs/%s/attempts/%s/jobs?per_page=100' % (base, args.run_id, args.attempt)),
                    'artifact': gh_api('%s/artifacts/%s' % (base, args.artifact_id))}
            zb = gh_api('%s/artifacts/%s/zip' % (base, args.artifact_id), binary=True)
            (args.output / 'original-artifact.sha256').write_text(sha(zb) + '\n')
            report['original_zip'] = {'bytes': len(zb), 'sha256': sha(zb), 'run_status': meta['run'].get('status'),
                                      'run_conclusion': meta['run'].get('conclusion')}
            L = authenticate(meta, zb, expect, args.profile)
            if not L.failed():
                try:
                    L.rows += audit(build_evidence(extract(zb), args.profile), expect, args.profile).rows
                except (ValueError, KeyError) as error:  # explicit refusal on missing or unparseable evidence
                    L.add('evidence.complete_and_parseable', False, error)
            report['producer_audited'] = True
            report['producer_rows'] = L.rows
            if L.failed():
                report['verdict'] = 'REJECTED: ' + ', '.join(L.failed())
                exit_code = 1
            elif exit_code == 0:
                report['verdict'] = 'ACCEPTED: producer artifact independently re-derived (Linux GTK scope only)'
    (args.output / 'c07_report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({'verdict': report['verdict'], 'controls': len(controls),
                      'controls_all_ok': report['controls_all_ok'], 'failed_controls': [c['control'] for c in controls if not c['ok']]}))
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
