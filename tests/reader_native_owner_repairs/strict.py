"""Authenticate this attempt's original producer ZIPs; preserve original judges."""
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback
import zipfile

import guard
from reuse import D09, D12, source

ROOT = guard.ROOT
sys.path.insert(0, str(ROOT / 'tests/reader_hosts_integration'))
from final import Bundle, fetch, identity, pages, require


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def load_functions(path, names, namespace):
    """Use exact AST bodies; imports/old source gate entry points are not executed."""
    raw = (ROOT / path).read_text(encoding='utf-8')
    nodes = [n for n in ast.parse(raw).body if
             isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names
             or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
    found = {n.name for n in nodes if isinstance(n, ast.FunctionDef)} | {
        t.id for n in nodes if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
    require(found == set(names), 'exact original judge declarations missing: ' + path)
    namespace.update(__builtins__=__builtins__)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), path + ' [unaltered judge bodies]', 'exec'), namespace)
    return hashlib.sha256(raw.encode()).hexdigest()


def current_producer(run, args):
    require(args.source == os.environ['GITHUB_SHA'] and args.run == int(os.environ['GITHUB_RUN_ID']), 'actual current source/run required')
    attempt = int(os.environ['GITHUB_RUN_ATTEMPT'])
    require(run['head_sha'] == args.source and run['run_attempt'] == attempt
            and run['path'].split('@')[0] == guard.WORKFLOW
            and run['status'] == 'in_progress' and run['conclusion'] is None, 'actual workflow source/state differs')
    rows = pages('actions/runs/%d/attempts/%d/jobs' % (args.run, attempt), 'jobs')
    require(len(rows) == 3 and {r['name'] for r in rows} == {'windows', 'gtk', 'authenticate'}, 'exact three-job topology required')
    for row in rows:
        require(row['head_sha'] == args.source and row['run_attempt'] == attempt, 'foreign job source/attempt')
        if row['name'] == 'authenticate':
            require(row['status'] == 'in_progress' and os.environ['GITHUB_JOB'] == 'authenticate', 'not the actual executing strict job')
        else:
            require(row['conclusion'] == 'success' and row['status'] == 'completed', 'native producer failed: ' + row['name'])
            require(all(s['conclusion'] in ('success', 'skipped') for s in row['steps']), 'hidden failed native step')
    return attempt, next(row for row in rows if row['name'] == 'windows')


def inventory(value, read, prefix):
    require(bool(value['files']), 'empty native inventory')
    for path, meta in value['files'].items():
        require(not path.startswith('/') and '\\' not in path and '..' not in path.split('/'), 'unsafe native inventory path')
        data = read(prefix + path, 256 * 1024**2)
        require(len(data) == meta['bytes'] and hashlib.sha256(data).hexdigest() == meta['sha256'], 'native bytes differ: ' + prefix + path)


def native_windows(value, read, source_sha, run, attempt):
    identity(value, source_sha, run, attempt)
    require(value['accepted'] is True and value['guard_kind'] == 'native-owner-repairs'
            and value['complete_product'] is False and value['screen_reader_accepted'] is False
            and value['original_d12_acceptance_reused'] is False, 'native Windows scope/state differs')
    require(value['historical_primitive_source'] == D12
            and value['historical_primitive_sha256'] == hashlib.sha256(source(D12, 'tests/reader_dot_wave2/d12/check.py')).hexdigest(), 'exact D12 primitive source differs')
    require(len(value['focus']) == 2 and {r['profile'] for r in value['focus']} == {'legacy', 'raw'}, 'both Windows selector profiles required')
    expected_focus = {'initial-default', 'initial-small'} | {view + '-' + title for view in ('reading', 'shelf') for title in ('search', 'navigation', 'records', 'preferences')}
    for result in value['focus']:
        require(result['accepted'] is True and len(result['observations']) == len(expected_focus)
                and {r['name'] for r in result['observations']} == expected_focus, 'full native focus/bounds set missing')
        program = read('windows-raw3-host/' + result['profile'] + '-host/EXReaderProduct.exe', 128 * 1024**2)
        require(result['program_sha256'] == hashlib.sha256(program).hexdigest(), 'focus observed a different real program')
        for row in result['observations']:
            if row['name'].startswith('initial-'):
                area, box = row['actual_work_area'], row['outer']
                require(area[0] <= box[0] < box[2] <= area[2] and area[1] <= box[1] < box[3] <= area[3], 'outer bounds exceed actual work area')
                resized = row['minimum_resize_outer']
                require(resized[2] - resized[0] <= area[2] - area[0] and resized[3] - resized[1] <= area[3] - area[1], 'effective minimum exceeds work area')
            else:
                require(row['actual_transport'] == 'sendinput' and len(row['modal_focus']) == 3
                        and all(all(s[k] is True for k in ('descendant', 'visible', 'enabled')) for s in row['modal_focus'] + [row['after']]), 'native modal focus rejected')
    manifest = json.loads(read('native-owner-windows/evidence/original-manifest.json', 2 * 1024**2))
    expected_ids = {r['revision_id'] for r in manifest['reading_records']}
    require(len(expected_ids) == 11 and len(value['positive']) == 2 and len(value['null']) == 2, 'complete two-process received cases absent')
    require(len({r['pid'] for r in value['positive'] + value['null']}) == 4, 'four genuine GUI processes required')
    require(value['positive_receive']['accepted'] and value['null_receive']['accepted'], 'actual native HTTPS receives missing')
    for result in value['positive']:
        require(result['accepted'] is True and result['history_unchanged'] is True
                and result['public_sdk_unchanged'] is True and len(result['records']) == 11
                and {r['revision_id'] for r in result['records']} == expected_ids, 'complete actual GUI records not granted')
        for row in result['records']:
            require(row['accepted'] is True and row['exact_jump_verified'] is True, 'unverified actual jump')
            original = next(r for r in manifest['reading_records'] if r['revision_id'] == row['revision_id'])
            oracle = row['independent_oracle']
            require(all(oracle[k] is True for k in ('found', 'fresh_capture_equal', 'retained_manifest_capture_equal')), 'independent public FOUND absent')
            mode, unit, start, end = map(int, original['capture']['numbers'])
            frame = row['after']
            if mode == 3:
                require(frame['fixed'] == 1 and frame['page'] == unit, 'native fixed target differs')
            else:
                require(frame['fixed'] == 0 and frame['frame_start'] <= start <= frame['frame_end'], 'native reflow frame misses independent point')
                if mode == 2:
                    require(frame['part'] == unit, 'actual EPUB part differs')
            if end > start:
                require(frame['selection_active'] == 1 and frame['selection_start'] == start
                        and frame['selection_end'] == end and frame['selection_bytes'] == end - start, 'native highlight not actually selected')
    null_id = '2a490dc51d514032a2815e802c8b3f48'
    null_bytes = read('native-owner-windows/evidence/original-null-wires/' + null_id + '.json', 1024**2)
    require(len(null_bytes) == 1017 and hashlib.sha256(null_bytes).hexdigest() == 'a4d655ded931966dc268f01ab4ffb2717e7c31fb98b3823ad277ef4c2d0c1dbc'
            and json.loads(null_bytes)['payload']['location']['selector']['exact']['base64'] is None, 'genuine Mac NULL wire changed')
    for result in value['null']:
        require(result['accepted'] is True and result['target_revision'] == null_id
                and result['unsafe_actions_disabled'] is True and result['navigation_attempted'] is False
                and result['history_unchanged'] is True and result['history_after_reopen_actions_unchanged'] is True
                and result['public_sdk_and_all_product_rows_unchanged'] is True
                and all(c['enabled'] is False for c in result['controls'].values()), 'NULL action or read-only state regression')
    inventory(value, read, 'native-owner-windows/')


def source_provenance(archive, source_sha, run, attempt, root, network_verified, peer_verified):
    require(network_verified is True and peer_verified is True, 'all original owner network/peer assertions required')
    require([p['original_compact_ui_checks'] for p in root['profiles']] == [22, 22]
            and [p['bulk_original_checks'] for p in root['profiles']] == [21, 21], 'original full compact22/bulk21 changed')
    with zipfile.ZipFile(archive) as packed:
        def read(path, limit=1024**2):
            matches = [r for r in packed.infolist() if r.filename == path or r.filename.endswith('/' + path)]
            require(len(matches) == 1 and matches[0].file_size <= limit and (matches[0].external_attr >> 16) & 0o170000 != 0o120000, 'unique bounded regular ZIP member required: ' + path)
            return packed.read(matches[0])
        stored = json.loads(read('native-owner-preflight/windows.json'))
        expected = guard.inspect_source()
        require(all(stored[k] == v for k, v in expected.items()), 'fresh explicit changed-owner proof differs')
        require(len(stored['negative_controls']) == 8 and all(r['rejected'] is True for r in stored['negative_controls']), 'source-policy refusal controls missing')
        value = json.loads(read('native-owner-windows/report.json', 16 * 1024**2))
        native_windows(value, read, source_sha, run, attempt)
        mutations = [dict(accepted=False), dict(positive=[]), dict(null=[]), dict(focus=[]), dict(source_sha='foreign')]
        for mutation in mutations:
            bad = copy.deepcopy(value)
            bad.update(mutation)
            try:
                native_windows(bad, read, source_sha, run, attempt)
            except (ValueError, KeyError, AssertionError):
                continue
            raise RuntimeError('native Windows judge admitted missing/foreign scope')
    return dict(guard_kind='native-owner-repairs', source_sha=source_sha, actual_owner_changed=True,
                legacy_guard_executed=False, original_auth_body_preserved=True, native_gui_accepted=True,
                native_negative_controls=len(mutations), off_f3_atomic13_rerun=False)


def gtk_proof(run, attempt, source_sha):
    listing = pages('actions/runs/%d/artifacts' % run, 'artifacts')
    matches = [r for r in listing if r['name'] == 'native-owner-gtk-%d-%d' % (run, attempt)]
    require(len(matches) == 1, 'one original GTK producer ZIP required')
    meta = matches[0]
    require(meta['workflow_run']['head_sha'] == source_sha and meta['workflow_run']['id'] == run, 'foreign GTK ZIP')
    bundle = Bundle(meta)
    try:
        def read(path, limit=1024**2):
            return bundle.bytes(path, limit)
        value = bundle.report('gtk-raw3/result.json')
        space = dict(identity=identity, require=require)
        owner_judge = load_functions('tests/reader_gtk_raw3/collect.py', {'validate', 'selftest'}, space)
        space['validate'](value, source_sha, run, attempt)
        negatives = 0
        for key, replacement in space['selftest']():
            bad = copy.deepcopy(value)
            bad[key] = replacement
            try:
                space['validate'](bad, source_sha, run, attempt)
            except (ValueError, KeyError, TypeError):
                negatives += 1
                continue
            raise RuntimeError('original GTK business judge accepted mutation ' + key)
        inventory(value, read, 'gtk-raw3/')
        for row in value['phases']:
            report = bundle.report('gtk-raw3/' + row['report'])
            require(report['accepted'] and report['check_count'] == row['checks'] == len(report['checks'])
                    and all(x['passed'] is True for x in report['checks']), 'original GTK owner phase incomplete')
        program = hashlib.sha256(read('gtk-raw3/package/EXReader-Linux/bin/exreader-linux', 128 * 1024**2)).hexdigest()
        ui = bundle.report('gtk-raw3/raw-ui/report.json')
        space = dict(identity=identity, require=require, ROOT=ROOT, ast=ast, re=re)
        compact_judge = load_functions('tests/reader_gtk_compact/aggregate.py', {'SCREENS', 'DENIED', 'declaration', 'validate_ui'}, space)
        count = space['validate_ui'](ui, source_sha, run, attempt, program)
        require(count == 45, 'complete original compact45 required')
        for shot in ui['screenshots'].values():
            raw = read('gtk-raw3/raw-ui/' + shot['path'], 32 * 1024**2)
            require(raw.startswith(b'\x89PNG\r\n\x1a\n') and hashlib.sha256(raw).hexdigest() == shot['sha256'], 'original compact screenshot differs')
        # Original D09 mandatory names and modal/coordinate semantics are reused
        # byte-for-byte; only its target-source assignment changes explicitly.
        contract_raw = source(D09, 'tests/reader_dot_wave2/d09/contract.py')
        semantics = {}
        exec(compile(contract_raw, 'original D09 contract', 'exec'), semantics)
        projection = bundle.report('native-owner-reuse/d09/projection.json')
        require(projection['historical_source'] == D09 and projection['source_sha'] == source_sha
                and projection['reverse_projection_exact'] is True and projection['historical_acceptance_reused'] is False, 'D09 source projection differs')
        for config in ('normal', 'scale2', 'dark', 'large'):
            report = bundle.report('native-owner-d09-' + config + '/result.json')
            identity(dict(source_sha=report['harness_sha'], run_id=report['run_id'], attempt=report['attempt']), source_sha, run, attempt)
            require(report['target_sha'] == source_sha and report['program_sha256'] == program and report['audit_completed'] is True, 'D09 actual source/program incomplete')
            checks = {r['name']: r for r in report['checks']}
            require(len(checks) == len(report['checks']) == len(semantics['REQUIRED'])
                    and set(checks) == semantics['REQUIRED'] and all(r['passed'] is True for r in checks.values()), 'all original D09 mandatory cases required')
            require(semantics['coordinate_ok'](report['coordinate_calibration']), 'original D09 actual coordinates not verified')
            for title in ('search', 'directory', 'records', 'settings'):
                require(semantics['modal_focus_ok'](checks[title + '-dialog-focus']['actual']), 'D09 actual modal focus differs')
            inventory(report, read, 'native-owner-d09-' + config + '/')
        for profile in ('legacy', 'raw'):
            folder = 'native-owner-gtk-focus-' + profile + '/'
            report = bundle.report(folder + 'report.json')
            identity(report, source_sha, run, attempt)
            require(report['accepted'] is True and report['exit_code'] == 0 and report['profile'] == profile
                    and len(report['observations']) == 4 and {r['route'] for r in report['observations']} == {'shortcut', 'menu', 'shortcut-reopen', 'menu-reopen'}, 'both GTK native entry routes and reopen required')
            for row in report['observations']:
                require(row['passed'] is True and len(row['modal']) == 3
                        and all(semantics['modal_focus_ok'](v) for v in row['modal']), 'GTK modal focus rejected')
            inventory(report, read, folder)
        proof = dict(accepted=True, source_sha=source_sha, run_id=run, attempt=attempt,
                     guard_kind='native-owner-repairs', legacy_guard_executed=False,
                     original_owner_judge_sha256=owner_judge, original_compact_judge_sha256=compact_judge,
                     original_compact_checks=count, original_d09_configurations=4,
                     original_gtk_owner_protocol_refusals=negatives, raw_program_sha256=program,
                     original_off35_rerun=False, complete_product=False,
                     artifact={k: meta[k] for k in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
        save(ROOT / 'build/native-owner-authentication/gtk.json', proof)
    finally:
        bundle.close()


def main():
    guard.inspect_source()
    # Preserve every original owner/kill/compact/bulk/Mac assertion. Enumerate
    # only the actual current-run entry and added new-source/new-GUI proof.
    spec = importlib.util.spec_from_file_location('original_owner_entry_projection', ROOT / 'tests/reader_raw3_common_windows_owner/projection.py')
    projection = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(projection)
    original = guard.git('show', projection.ORIGINAL + ':' + projection.OLD_AUTH).decode()
    require((ROOT / projection.OLD_AUTH).read_text(encoding='utf-8') == original, 'original full Windows judge changed')
    changes = list(projection.AUTH_CHANGES)
    changes[-1] = (changes[-1][0], changes[-1][1].replace('guard_kind="common-windows-owner"', 'guard_kind="native-owner-repairs"'))
    adapted = original
    for before, after in changes:
        require(adapted.count(before) == 1, 'owner auth entry substitution count differs')
        adapted = adapted.replace(before, after, 1)
    reversed_source = adapted
    for before, after in reversed(changes):
        require(reversed_source.count(after) == 1, 'owner auth inverse substitution count differs')
        reversed_source = reversed_source.replace(after, before, 1)
    require(reversed_source == original, 'an original Windows business assertion changed')
    namespace = dict(__name__='native_owner_preserved_judge', __file__=str(ROOT / projection.OLD_AUTH),
                     common_current_producer=current_producer, common_source_provenance=source_provenance)
    exec(compile(adapted, projection.OLD_AUTH + ' [explicit native owner entry]', 'exec'), namespace)
    sys.path.insert(0, str(ROOT / 'tests/reader_windows_compact'))
    namespace['main']()
    gtk_proof(int(os.environ['GITHUB_RUN_ID']), int(os.environ['GITHUB_RUN_ATTEMPT']), os.environ['GITHUB_SHA'])
    save(ROOT / 'build/native-owner-authentication/result.json', dict(accepted=True, source_sha=os.environ['GITHUB_SHA'],
         run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'], complete_product=False,
         scope='native Windows focus/bounds/received selection/NULL refusal and GTK records focus, with enumerated original regression suites',
         original_off_gtk35_rerun=False, original_windows_off_f3_atomic13_rerun=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        save(ROOT / 'build/native-owner-authentication/failure.json', dict(accepted=False,
             source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
             attempt=os.environ['GITHUB_RUN_ATTEMPT'], failure=traceback.format_exc(), complete_product=False))
        raise
