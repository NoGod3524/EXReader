#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read the pinned cloud ABBA raw JSON without changing its rejected statistics."""
from collections import Counter
import json
from pathlib import Path
import re
import sys
import zipfile

from android_raster_ab_diagnostic import cloud, parse_frames, sha, zip_members
from check_parallel_integration import download_artifact_zip, fetch, pages, require

PIN = {'run_id': 39999124836, 'attempt': 1,
       'source_sha': 'd5ff8180e50d4fa86b098feab077ad7989ab4fe6',
       'artifact_id': 12520669801, 'bytes': 452973647,
       'digest': 'd0fb4576e93f3d184472495d0deceaf513ee2d2ede63abf243f56979af2f8300'}
NAME = 'android-raster-ab-diagnostic-39999124836-1'
OUT = Path('build/android-raster-conflict-audit')
LABELS = ('A1', 'B1', 'B2', 'A2')
CRITICAL = ('Flags', 'IntendedVsync', 'FrameCompleted')


def identity_readback(frames):
    old, timeline, availability, headers = {}, {}, Counter(), set()
    id_values, raw_examples = Counter(), []
    for frame in frames:
        row = frame['raw']
        headers.add(tuple(sorted(row)))
        key = (frame['pid'], frame['window'], frame['intended_vsync_ns'])
        item = old.setdefault(key, {'ids': set(), 'vsyncs': set(), 'completed': set()})
        item['completed'].add(row['FrameCompleted'])
        if 'Vsync' in row:
            availability['Vsync_present'] += 1
            item['vsyncs'].add(row['Vsync'])
        else:
            availability['Vsync_missing'] += 1
        if 'FrameTimelineVsyncId' not in row:
            availability['FrameTimelineVsyncId_missing'] += 1
            continue
        value = row['FrameTimelineVsyncId']
        availability['FrameTimelineVsyncId_present'] += 1
        id_values[value] += 1
        item['ids'].add(value)
        if value <= 0:
            availability['FrameTimelineVsyncId_nonpositive'] += 1
            continue
        if value == 2**63 - 1:
            availability['FrameTimelineVsyncId_sentinel'] += 1
            continue
        availability['FrameTimelineVsyncId_positive_nonsentinel'] += 1
        newkey = (frame['pid'], frame['window'], value)
        target = timeline.setdefault(newkey, {'old_keys': set(), 'critical': {field: set() for field in CRITICAL},
                                              'Vsync': set()})
        target['old_keys'].add(key)
        for field in CRITICAL:
            target['critical'][field].add(row[field])
        if 'Vsync' in row:
            target['Vsync'].add(row['Vsync'])
        if len(raw_examples) < 3:
            raw_examples.append({'pid': frame['pid'], 'window': frame['window'], 'raw': row})
    old_completed = {key: item for key, item in old.items() if len(item['completed']) > 1}
    collisions = {key: item for key, item in old.items() if len(item['ids']) > 1}
    new_conflicts = {key: item for key, item in timeline.items()
                     if any(len(values) > 1 for values in item['critical'].values())}
    return {'scope': 'All ordinary PID-matching observations under the unchanged original frame filter',
            'availability_observations': dict(sorted(availability.items())),
            'ordinary_observations': sum(id_values.values()) + availability['FrameTimelineVsyncId_missing'],
            'unique_old_keys': len(old), 'old_keys_with_multiple_FrameTimelineVsyncId': len(collisions),
            'old_keys_with_multiple_Vsync': sum(len(item['vsyncs']) > 1 for item in old.values()),
            'old_keys_with_multiple_FrameCompleted': len(old_completed),
            'old_FrameCompleted_conflicts_with_multiple_FrameTimelineVsyncId':
                sum(len(item['ids']) > 1 for item in old_completed.values()),
            'old_FrameCompleted_conflicts_with_multiple_Vsync':
                sum(len(item['vsyncs']) > 1 for item in old_completed.values()),
            'FrameTimelineVsyncId_distinct_values': len(id_values),
            'FrameTimelineVsyncId_min': min(id_values, default=None),
            'FrameTimelineVsyncId_max': max(id_values, default=None),
            'FrameTimelineVsyncId_top_counts': id_values.most_common(5),
            'positive_nonsentinel_timeline_keys': len(timeline),
            'timeline_keys_with_multiple_old_keys': sum(len(item['old_keys']) > 1 for item in timeline.values()),
            'timeline_keys_with_critical_conflicts': len(new_conflicts),
            'timeline_key_critical_conflict_counts':
                {field: sum(len(item['critical'][field]) > 1 for item in timeline.values()) for field in CRITICAL},
            'timeline_conflict_examples':
                [{'key': list(key), 'old_keys': [list(value) for value in sorted(item['old_keys'])],
                  'critical_values': {field: sorted(values) for field, values in item['critical'].items()},
                  'Vsync_values': sorted(item['Vsync'])} for key, item in list(new_conflicts.items())[:8]],
            'raw_field_headers': [list(header) for header in sorted(headers)], 'first_raw_examples': raw_examples}


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
    identity_frames = [dict(frame, raw=dict(frame['raw'], FrameTimelineVsyncId=value, Vsync=100,
                                           FrameCompleted=completed))
                       for value, completed in ((1, 200), (2, 210), (2, 220))]
    identity_result = identity_readback(identity_frames)
    require(identity_result['old_keys_with_multiple_FrameTimelineVsyncId'] == 1
            and identity_result['positive_nonsentinel_timeline_keys'] == 2
            and identity_result['timeline_key_critical_conflict_counts'] ==
                {'Flags': 0, 'IntendedVsync': 0, 'FrameCompleted': 1}, 'Frame identity classification failed')
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

        def read_bytes(name, limit=8 * 1024 * 1024):
            require(name in names, 'Required ABBA JSON missing: ' + name)
            entry = archive.getinfo(name)
            require(not entry.is_dir() and entry.file_size <= limit, 'ABBA source member exceeds bound')
            data = archive.read(entry)
            target = raw / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            return data

        def read(name):
            return json.loads(read_bytes(name))

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
            sampling = read(label + '/sampling.json')
            frames, raw_dump_count, pid_mismatch_observations = [], 0, 0
            for sample in sampling['samples']:
                record = sample['commands'].get('gfxinfo')
                if not record or record['exit_code'] != 0:
                    continue
                filename = record['stdout']
                require(re.fullmatch('[0-9]{5}\\.stdout\\.txt', filename), 'Unexpected gfxinfo raw filename')
                data = read_bytes(label + '/commands/' + filename, 32 * 1024 * 1024)
                require(len(data) == record['stdout_bytes'], 'Raw gfxinfo size differs')
                parsed, unused = parse_frames(data.decode('utf-8', errors='replace'))
                raw_dump_count += 1
                for frame in parsed:
                    if frame['pid'] == sample.get('pid'):
                        frames.append(frame)
                    else:
                        pid_mismatch_observations += 1
            identity = identity_readback(frames)
            require(identity['unique_old_keys'] == phase['measurements']['frames']['count'] + result['distinct_conflicting_keys'],
                    'Full raw readback does not reproduce the original old-key set')
            identity.update(raw_dump_count=raw_dump_count, pid_mismatch_observations=pid_mismatch_observations)
            report['phases'].append({'label': label, 'variant': phase['variant'],
                                     'original_measurements_unchanged': phase['measurements'], 'conflicts': result,
                                     'frame_identity_readback': identity})
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
