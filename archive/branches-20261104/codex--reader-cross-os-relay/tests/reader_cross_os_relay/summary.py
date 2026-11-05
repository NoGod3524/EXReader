# SPDX-License-Identifier: MIT
"""Actions-only strict same-source summary of the cross-OS relay. Never run locally."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from relaylib import DIRECTIONS, ROLES  # noqa: E402

OSES = ('Linux', 'Windows', 'macOS')
COMPONENT_CHECKS = {'sha256_vector_empty', 'sha256_vector_abc', 'sha256_vector_million', 'inventory_counts_files_and_directories', 'inventory_is_deterministic',
                    'inventory_keeps_nfc_nfd_russian_emoji_names_unmodified', 'verify_accepts_the_unmodified_tree', 'verify_rejects_altered_byte_same_length',
                    'verify_rejects_truncated_file', 'verify_rejects_extra_file', 'verify_rejects_missing_file', 'verify_rejects_missing_directory',
                    'verify_rejects_renamed_file', 'verify_rejects_truncated_inventory', 'verify_rejects_noncanonical_inventory', 'verify_rejects_foreign_document',
                    'verify_rejects_forged_digest', 'limit_max_files_rejects_whole_tree_not_truncates', 'limit_max_depth', 'limit_max_file_bytes',
                    'limit_max_total_bytes', 'limit_above_ceiling_refused', 'limit_struct_too_short_refused', 'sha256_file_limit', 'cancel_before_first_directory',
                    'cancel_in_the_middle_of_a_file', 'null_root_refused', 'missing_root_is_io', 'file_root_is_io', 'free_null_is_noop', 'version_constant'}
OPTIONAL_SKIPS = {'inventory_refuses_symlink', 'inventory_refuses_quote_in_name'}
STAGE_OS = {'send': 0, 'receive': 1, 'confirm': 0}


def problems_for(identity, results):
    """Pure verification of already authenticated reports; also run on tampered copies as a self-test."""
    problems = []

    def bad(message):
        problems.append(message)

    def ident_ok(record, label):
        for key in ('source_sha', 'run_id', 'attempt'):
            if str(record.get(key)) != str(identity[key]):
                bad('%s %s differs from this run' % (label, key))
        if record.get('accepted') is not True:
            bad('%s not accepted' % label)

    plan = results.get('plan')
    if not plan:
        bad('plan missing')
    else:
        ident_ok(plan, 'plan')
        if plan.get('pinned') is not True:
            bad('originals not pinned')
    builds = results.get('build', {})
    for os_name in OSES:
        b = builds.get(os_name)
        if not b:
            bad('build %s missing' % os_name)
            continue
        ident_ok(b, 'build ' + os_name)
        if b.get('os') != os_name:
            bad('build %s ran on %s' % (os_name, b.get('os')))
        names = {c['name']: c['status'] for c in b.get('component_checks', [])}
        if not COMPONENT_CHECKS <= set(names):
            bad('build %s lacks component checks %s' % (os_name, sorted(COMPONENT_CHECKS - set(names))))
        if any(s == 'fail' for s in names.values()) or any(s == 'skip' and n not in OPTIONAL_SKIPS for n, s in names.items()):
            bad('build %s component check failed/skipped' % os_name)
        if b.get('c_consumer_exit') != 0 or not b.get('probe_sha256') or not b.get('tool_sha256'):
            bad('build %s consumer evidence incomplete' % os_name)
    for direction, (sender, receiver) in DIRECTIONS.items():
        chain = {}
        for stage in ('send', 'receive', 'confirm'):
            r = results.get(stage, {}).get(direction)
            if not r:
                bad('%s %s missing' % (direction, stage))
                continue
            chain[stage] = r
            ident_ok(r, '%s %s' % (direction, stage))
            if r.get('direction') != direction or r.get('stage') != stage:
                bad('%s %s identity mislabelled' % (direction, stage))
            want_os = (sender, receiver)[STAGE_OS[stage]]
            if r.get('os') != want_os:
                bad('%s %s ran on %s not %s' % (direction, stage, r.get('os'), want_os))
            if not r.get('checks') or not all(c.get('pass') is True for c in r['checks']):
                bad('%s %s has failing or no checks' % (direction, stage))
            if any(r.get(k) is not False for k in ('sdk_changed', 'schema_changed', 'host_ui_accepted', 'real_device_accepted', 'live_six_device_cloud')):
                bad('%s %s overclaims scope' % (direction, stage))
            b = builds.get(r.get('os'), {})
            if r.get('probe_sha256') != b.get('probe_sha256'):
                bad('%s %s ran a probe that is not the built one' % (direction, stage))
        ids = {s: results.get('identity', {}).get(s, {}).get(direction, {}) for s in ('send', 'receive')}
        if ids['send'] and ids['receive'] and chain.get('receive', {}).get('parent_inventory_digest') != ids['send'].get('inventory_digest'):
            bad('%s receive consumed a tree other than the sent one' % direction)
        if ids['receive'] and chain.get('confirm', {}).get('parent_inventory_digest') != ids['receive'].get('inventory_digest'):
            bad('%s confirm read a tree other than the returned one' % direction)
        if not ids['send'].get('inventory_digest') or ids['send'].get('inventory_digest') == ids['receive'].get('inventory_digest'):
            bad('%s return leg did not change the tree' % direction)
        cases = chain.get('receive', {}).get('cases', [])
        if len(cases) != 18 or sum(c.get('state') == 'FOUND' for c in cases) != 17 or [c['state'] for c in cases].count('AMBIGUOUS') != 1:
            bad('%s receive capture outcomes differ' % direction)
    pairs = {frozenset(v) for v in DIRECTIONS.values()}
    for pair in pairs:
        both = [d for d, v in DIRECTIONS.items() if frozenset(v) == pair]
        if len(both) != 2 or any(not results.get('confirm', {}).get(d) for d in both):
            bad('pair %s lacks a direction' % sorted(pair))
    return problems


def selftest(identity):
    good = {'plan': dict(identity, accepted=True, pinned=True), 'build': {}, 'send': {}, 'receive': {}, 'confirm': {}, 'identity': {'send': {}, 'receive': {}}}
    for os_name in OSES:
        good['build'][os_name] = dict(identity, accepted=True, os=os_name, probe_sha256='p' + os_name, tool_sha256='t', c_consumer_exit=0,
                                      component_checks=[{'name': n, 'status': 'pass'} for n in COMPONENT_CHECKS])
    for d, (s, r) in DIRECTIONS.items():
        for stage in ('send', 'receive', 'confirm'):
            os_name = (s, r)[STAGE_OS[stage]]
            res = dict(identity, accepted=True, direction=d, stage=stage, os=os_name, checks=[{'name': 'x', 'pass': True}], probe_sha256='p' + os_name,
                       sdk_changed=False, schema_changed=False, host_ui_accepted=False, real_device_accepted=False, live_six_device_cloud=False)
            if stage == 'receive':
                res['parent_inventory_digest'] = 'S' + d
                res['cases'] = [{'state': 'FOUND'}] * 17 + [{'state': 'AMBIGUOUS'}]
            if stage == 'confirm':
                res['parent_inventory_digest'] = 'R' + d
            good[stage][d] = res
        good['identity']['send'][d] = {'inventory_digest': 'S' + d}
        good['identity']['receive'][d] = {'inventory_digest': 'R' + d}
    base = problems_for(identity, good)
    if base:
        raise SystemExit('selftest: the synthetic good run was refused: %s' % base)

    def mutated(name, change):
        value = copy.deepcopy(good)
        change(value)
        if not problems_for(identity, value):
            raise SystemExit('selftest: %s was NOT rejected' % name)
        print('selftest rejected:', name)
    mutated('missing direction', lambda v: v['confirm'].pop('windows-to-linux'))
    mutated('missing send stage', lambda v: v['send'].pop('linux-to-macos'))
    mutated('other run id', lambda v: v['receive']['linux-to-windows'].update(run_id='1'))
    mutated('other attempt', lambda v: v['send']['macos-to-linux'].update(attempt='9'))
    mutated('other source', lambda v: v['confirm']['linux-to-macos'].update(source_sha='0' * 40))
    mutated('wrong OS for a stage', lambda v: v['receive']['linux-to-windows'].update(os='Linux'))
    mutated('failed check', lambda v: v['send']['windows-to-linux']['checks'].append({'name': 'y', 'pass': False}))
    mutated('foreign tree', lambda v: v['receive']['linux-to-macos'].update(parent_inventory_digest='x'))
    mutated('unchanged return tree', lambda v: v['identity']['receive']['linux-to-macos'].update(inventory_digest='Slinux-to-macos'))
    mutated('missing mislocation evidence', lambda v: v['receive']['macos-to-linux'].update(cases=[]))
    mutated('probe not built here', lambda v: v['send']['linux-to-windows'].update(probe_sha256='other'))
    mutated('component negative case missing', lambda v: v['build']['Windows']['component_checks'].pop())
    mutated('scope overclaim', lambda v: v['confirm']['linux-to-windows'].update(host_ui_accepted=True))


def main():
    from check_parallel_integration import download_artifact_zip, fetch, pages, require
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'cloud only')
    run_id, attempt, source = int(os.environ['GITHUB_RUN_ID']), int(os.environ['GITHUB_RUN_ATTEMPT']), os.environ['GITHUB_SHA']
    identity = {'source_sha': source, 'run_id': str(run_id), 'attempt': str(attempt)}
    out = Path(sys.argv[1])
    out.mkdir(parents=True)
    summary = {'accepted': False, 'source_sha': source, 'run_id': run_id, 'attempt': attempt, 'artifacts': [], 'problems': [],
               'scope': 'artifact-relayed cross-OS compatibility (Windows<->Linux, macOS<->Linux); not a live six-device user cloud; no host UI or device'}
    try:
        selftest(identity)
        run = fetch('actions/runs/%d' % run_id)
        require(run['head_sha'] == source and run['run_attempt'] == attempt and run['path'] == '.github/workflows/reader-cross-os-relay.yml', 'run identity differs')
        jobs = pages('actions/runs/%d/attempts/%d/jobs' % (run_id, attempt), 'jobs')
        artifacts = pages('actions/runs/%d/artifacts' % run_id, 'artifacts')
        suffix = '-%d-%d' % (run_id, attempt)
        wanted = [('plan', None, 'relay-plan' + suffix, 'plan')]
        wanted += [('build', o, 'relay-build-%s%s' % (o, suffix), 'build (%s)' % o) for o in OSES]
        for d in DIRECTIONS:
            wanted += [(stage, d, 'relay-%s-%s%s' % (stage, d, suffix), '%s %s' % (stage, d)) for stage in ('send', 'receive', 'confirm')]
        results = {'plan': None, 'build': {}, 'send': {}, 'receive': {}, 'confirm': {}, 'identity': {'send': {}, 'receive': {}}}
        for stage, key, name, job_name in wanted:
            matches = [a for a in artifacts if a['name'] == name]
            require(len(matches) == 1, 'missing/duplicate artifact ' + name)
            artifact = matches[0]
            matches = [j for j in jobs if j['name'] == job_name]
            require(len(matches) == 1, 'missing/duplicate job ' + job_name)
            require(matches[0]['head_sha'] == source and matches[0]['run_attempt'] == attempt and matches[0]['conclusion'] == 'success', 'job %s did not succeed on this source' % job_name)
            require(not artifact['expired'] and artifact['size_in_bytes'] > 0 and artifact['workflow_run']['head_sha'] == source, 'artifact identity differs ' + name)
            with tempfile.TemporaryFile() as stream:
                download_artifact_zip(artifact['id'], stream)
                stream.seek(0)
                data = stream.read()
            require(len(data) == artifact['size_in_bytes'] and 'sha256:' + hashlib.sha256(data).hexdigest() == artifact['digest'], 'ZIP bytes/digest differ ' + name)
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                result = json.loads(archive.read('result.json'))
                if stage in ('send', 'receive'):
                    results['identity'][stage][key] = json.loads(archive.read('identity.json'))
                    inventory = archive.read('inventory.json')
                    require(hashlib.sha256(inventory).hexdigest() == results['identity'][stage][key]['inventory_sha256'], 'inventory bytes differ from identity ' + name)
                    files = {i.filename for i in archive.infolist()}
                    require(any(f.startswith('tree/') for f in files) and not any(f.endswith('.key') or f.endswith('.sqlite') for f in files), 'package carries a key or database ' + name)
                if stage == 'build':
                    for exe_name, key_name in (('relay-probe', 'probe_sha256'), ('relay-tool', 'tool_sha256')):
                        suffix_exe = '.exe' if key == 'Windows' else ''
                        require(hashlib.sha256(archive.read('bin/' + exe_name + suffix_exe)).hexdigest() == result[key_name], 'binary hash differs ' + name)
                    result['component_checks'] = json.loads(archive.read('component-consumer.json'))['checks']
            if stage == 'plan':
                results['plan'] = result
            elif stage == 'build':
                results['build'][key] = result
            else:
                results[stage][key] = result
            summary['artifacts'].append({k: artifact[k] for k in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
        summary['problems'] = problems_for(identity, results)
        summary['accepted'] = not summary['problems']
        summary['directions'] = sorted(DIRECTIONS)
    except Exception as error:
        summary['problems'].append(str(error))
    (out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary), flush=True)
    raise SystemExit(0 if summary['accepted'] else 1)


if __name__ == '__main__':
    main()
