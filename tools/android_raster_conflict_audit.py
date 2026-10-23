#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read the pinned cloud ABBA raw JSON without changing its rejected statistics."""
from collections import Counter
import json
from pathlib import Path
import sys
import zipfile

from android_raster_ab_diagnostic import cloud, sha, zip_members
from check_parallel_integration import download_artifact_zip, fetch, pages, require

PIN = {'run_id': 39999124836, 'attempt': 1,
       'source_sha': 'd5ff8180e50d4fa86b098feab077ad7989ab4fe6',
       'artifact_id': 12520669801, 'bytes': 452973647,
       'digest': 'd0fb4576e93f3d184472495d0deceaf513ee2d2ede63abf243f56979af2f8300'}
NAME = 'android-raster-ab-diagnostic-39999124836-1'
OUT = Path('build/android-raster-conflict-audit')
LABELS = ('A1', 'B1', 'B2', 'A2')
CRITICAL = ('Flags', 'IntendedVsync', 'FrameCompleted')


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def classify(conflicts):
    fields, combinations, by_field = Counter(), Counter(), {}
    keys, critical_keys, examples = set(), {field: set() for field in CRITICAL}, []
    for conflict in conflicts:
        key = tuple(conflict['key'])
        require(len(key) == 3 and type(key[0]) is int and isinstance(key[1], str)
                and type(key[2]) is int, 'Malformed conflict identity')
        left, right = conflict['first'], conflict['conflicting']
        for frame in (left, right):
            require((frame['pid'], frame['window'], frame['intended_vsync_ns']) == key,
                    'Raw conflict does not match its declared identity')
            require(isinstance(frame['raw'], dict), 'Raw frame dictionary missing')
        changed = tuple(sorted(field for field in left['raw'].keys() | right['raw'].keys()
                               if left['raw'].get(field) != right['raw'].get(field)))
        require(changed, 'An unchanged raw frame was registered as conflicting')
        keys.add(key)
        fields.update(changed)
        combinations[changed] += 1
        for field in changed:
            by_field.setdefault(field, set()).add(key)
            if field in CRITICAL:
                critical_keys[field].add(key)
        if len(examples) < 8:
            examples.append({'key': list(key), 'observed_slot': conflict['slot'],
                             'changed': {field: {'first': left['raw'].get(field),
                                                'conflicting': right['raw'].get(field)}
                                         for field in changed}})
    return {'conflict_observations': len(conflicts), 'distinct_conflicting_keys': len(keys),
            'changed_fields_observations': dict(sorted(fields.items())),
            'changed_fields_distinct_keys': {field: len(values) for field, values in sorted(by_field.items())},
            'changed_field_combinations': [{'fields': list(fields), 'observations': count}
                                           for fields, count in sorted(combinations.items())],
            'critical_changed_observations': {field: fields[field] for field in CRITICAL},
            'critical_changed_distinct_keys': {field: len(critical_keys[field]) for field in CRITICAL},
            'examples': examples}


def selfcheck():
    frame = {'pid': 17, 'window': 'reader', 'intended_vsync_ns': 100,
             'raw': {'Flags': 0, 'IntendedVsync': 100, 'FrameCompleted': 200, 'GpuCompleted': 0}}
    changed = dict(frame, raw=dict(frame['raw'], GpuCompleted=220))
    critical = dict(frame, raw=dict(frame['raw'], FrameCompleted=210))
    rows = [{'key': [17, 'reader', 100], 'slot': index, 'first': frame, 'conflicting': value}
            for index, value in enumerate((changed, changed, critical))]
    result = classify(rows)
    require(result['distinct_conflicting_keys'] == 1 and result['conflict_observations'] == 3
            and result['changed_fields_observations'] == {'FrameCompleted': 1, 'GpuCompleted': 2}
            and result['critical_changed_observations'] == {'Flags': 0, 'IntendedVsync': 0, 'FrameCompleted': 1},
            'Conflict classification check failed')
    try:
        classify([dict(rows[0], key=[18, 'reader', 100])])
    except ValueError:
        return
    raise ValueError('Cross-PID conflict identity was accepted')


def audit(report):
    run = fetch('actions/runs/' + str(PIN['run_id']) + '/attempts/' + str(PIN['attempt']))
    require(run['id'] == PIN['run_id'] and run['run_attempt'] == PIN['attempt']
            and run['head_sha'] == PIN['source_sha'] and run['event'] == 'workflow_dispatch'
            and run['path'].split('@')[0] == '.github/workflows/reading-input-diagnostic.yml'
            and run['status'] == 'completed' and run['conclusion'] == 'success', 'Pinned ABBA run differs')
    jobs = pages('actions/runs/' + str(PIN['run_id']) + '/attempts/1/jobs', 'jobs')
    require(len(jobs) == 1 and jobs[0]['name'] == 'viewport-abba'
            and jobs[0]['head_sha'] == PIN['source_sha'] and jobs[0]['run_attempt'] == PIN['attempt']
            and jobs[0]['status'] == 'completed' and jobs[0]['conclusion'] == 'success',
            'Pinned ABBA job differs')
    artifacts = pages('actions/runs/' + str(PIN['run_id']) + '/artifacts', 'artifacts')
    require(len(artifacts) == 1, 'Pinned ABBA artifact set differs')
    artifact = artifacts[0]
    require(artifact['id'] == PIN['artifact_id'] and artifact['name'] == NAME
            and artifact['size_in_bytes'] == PIN['bytes'] and artifact['expired'] is False
            and artifact['digest'] == 'sha256:' + PIN['digest']
            and artifact['workflow_run']['id'] == PIN['run_id']
            and artifact['workflow_run']['head_sha'] == PIN['source_sha'], 'Pinned ABBA artifact differs')
    save(OUT / 'source-api.json', {'run': run, 'jobs': jobs, 'artifacts': artifacts})
    # The pinned archive is retained upstream; this audit keeps only byte-exact selected raw JSON.
    archive_path = OUT.parent / 'android-raster-conflict-audit-original.zip'
    with archive_path.open('w+b') as output:
        download_artifact_zip(PIN['artifact_id'], output)
    observed = {'bytes': archive_path.stat().st_size, 'sha256': sha(archive_path)}
    save(OUT / 'archive-receipt.json', {'pin': PIN, 'observed': observed})
    require(observed == {'bytes': PIN['bytes'], 'sha256': PIN['digest']}, 'Pinned ZIP bytes/digest differ')
    with zipfile.ZipFile(archive_path) as archive:
        names = zip_members(archive)
        raw = OUT / 'raw'
        raw.mkdir()

        def read(name):
            require(name in names, 'Required ABBA JSON missing: ' + name)
            entry = archive.getinfo(name)
            require(not entry.is_dir() and entry.file_size <= 8 * 1024 * 1024, 'ABBA JSON exceeds bound')
            data = archive.read(entry)
            target = raw / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            return json.loads(data)

        prepared, plan, original = read('prepared.json'), read('plan.json'), read('diagnostic.json')
        for value in (prepared, original):
            require(value['run_id'] == str(PIN['run_id']) and value['attempt'] == str(PIN['attempt'])
                    and value['source_sha'] == PIN['source_sha'] and value['diagnostic_only'] is True
                    and value['accepted'] is False, 'Retained JSON provenance/acceptance differs')
        require(prepared['prepared'] is True and not prepared['errors'], 'Retained preparation failed')
        require(plan['sequence'] == [['A1', 'A'], ['B1', 'B'], ['B2', 'B'], ['A2', 'A']]
                and plan['accepted'] is False and plan['frame_key'] == ['actual_dump_pid', 'window', 'IntendedVsync'],
                'Predeclared ABBA plan differs')
        require(original['diagnostic_completed'] is True and original['single_factor_interpretation_allowed'] is False
                and original['paired_differences'] is None
                and [item['label'] for item in original['phases']] == list(LABELS), 'Retained rejection differs')
        report['font_native_identity'] = {variant: prepared[variant]['registry'] for variant in ('A', 'B')}
        report['font_native_confounds'] = prepared['confounds']
        report['original_report'] = {key: original[key] for key in
                                     ('diagnostic_completed', 'accepted', 'single_factor_interpretation_allowed',
                                      'inconclusive_reasons', 'paired_differences')}
        for index, label in enumerate(LABELS):
            phase = read(label + '/phase.json')
            require(phase == original['phases'][index], 'Phase does not match untouched original report')
            conflicts = read(label + '/conflicting-frames.json')
            result = classify(conflicts)
            require(result['distinct_conflicting_keys'] == phase['measurements']['conflicting_completed_keys'],
                    'Retained conflicting-key count differs')
            report['phases'].append({'label': label, 'variant': phase['variant'],
                                     'original_measurements_unchanged': phase['measurements'], 'conflicts': result})
        report['audit_completed'] = True


def main():
    identity = cloud()
    OUT.mkdir(parents=True, exist_ok=False)
    report = {**identity, 'diagnostic_only': True, 'accepted': False, 'audit_completed': False,
              'original_pin': PIN, 'quantitative_rules_changed': False, 'phases': [], 'errors': []}
    try:
        selfcheck()
        audit(report)
    except Exception as error:
        report['errors'].append(type(error).__name__ + ': ' + str(error))
    finally:
        save(OUT / 'audit.json', report)
        print(json.dumps(report), flush=True)
    return 0 if report['audit_completed'] and not report['errors'] else 1


if __name__ == '__main__':
    sys.exit(main())
