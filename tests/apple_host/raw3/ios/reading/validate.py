"""Independent verification of readonly observations of real mobile UI actions."""
import base64
import hashlib
import json


def unpack(value):
    return base64.b64decode(value, validate=True)


def observations(root, phase):
    folder = root / ('profile-' + phase)
    return [json.loads(path.read_bytes()) for path in folder.rglob('raw3-review/*.json')]


def validate_observations(root, peer):
    all_rows = []
    for phase in ('raw-ui', 'raw-kill-before', 'raw-kill-after', 'raw-native-HTTPS', 'legacy-v1-failure', 'raw-retries-original-v1'):
        values = observations(root, phase)
        assert values, 'missing actual owner observations: ' + phase
        for value in values:
            assert value['sdk_version'] == '3.41.0' and len(value['source_sha']) == 40 and len(value['sdk_images']) == 1
            assert value['sdk_state_before'] == value['sdk_state_after'], 'readonly observer/resolver changed SDK state'
            if value['event'] == 'actual-public-resolution':
                assert value['found'] and value['original'] == value['fresh']
                assert hashlib.sha256(unpack(value['wire_base64'])).hexdigest() == value['wire_sha256']
                continue
            ids = {row['id'] for row in value['revisions']}
            assert len(ids) == len(value['revisions'])
            for row in value['revisions']:
                wire = unpack(row['wire_base64'])
                assert len(wire) == row['bytes'] and hashlib.sha256(wire).hexdigest() == row['sha256']
                original = json.loads(wire)
                assert original['version'] == 1 and original['id'] == row['id'] and set(original['parents']) <= ids
            for typed in value['typed_rows']:
                if typed['quote_bytes_base64'] is not None:
                    assert unpack(typed['quote_bytes_base64']) == unpack(typed['quote_utf8_base64'])
            if value['pending_base64']:
                pending = json.loads(unpack(value['pending_base64']))
                assert pending['version'] in (1, 2)
                if pending['version'] == 2: assert pending['anchor_version'] in (1, 2, 3)
        all_rows += values
    full = observations(root, 'raw-ui')
    submits = [row for row in full if row['event'] == 'actual-submit']
    assert len(submits) >= 6 and all(row['raw_enabled'] for row in full)
    points, ranges = [], []
    for row in submits:
        request = row['submission']
        assert request['version'] == 2 and request['anchor_version'] == 3
        if request['operation'] != 0 or request['kind'] == 4: continue
        capture = request['capture']['fixed']
        assert capture['fields'][1] is not None
        exact = unpack(capture['fields'][1])
        if request['kind'] in (1, 2):
            assert capture['start'] == capture['end'] == 0 and not exact and b'\0' in unpack(capture['fields'][3])
            points.append(request['revision'])
        elif request['kind'] == 3:
            assert capture['end'] > capture['start'] and exact and b'\0' in exact
            ranges.append(request['revision'])
    assert len(points) == 2 and len(ranges) == 1
    found = [row for row in full if row['event'] == 'actual-public-resolution']
    assert len(found) >= 2
    typed_range = [typed for row in full if row['event'] != 'actual-public-resolution' for typed in row['typed_rows']
                   if typed['revision'] in ranges and typed['has_location'] and typed['quote_bytes_base64'] is not None]
    assert typed_range and all(b'\0' in unpack(row['quote_bytes_base64']) for row in typed_range)
    boundaries = {}
    for phase, event, expected in [('raw-kill-before', 'private-save', 1), ('raw-kill-after', 'post-commit', 0)]:
        values = observations(root, phase)
        held = [row for row in values if row['event'] == event]
        replay = [row for row in values if row['event'] == 'actual-replay']
        assert len(held) == len(replay) == 1
        original_bytes = unpack(held[0]['pending_base64'])
        pending = json.loads(original_bytes)
        assert pending['version'] == 2 and pending['anchor_version'] == 3 and pending['mode'] == 3
        assert replay[0]['created'] == expected and replay[0]['submission'] == pending
        assert unpack(replay[0]['pending_base64']) == original_bytes
        boundaries[phase] = {'revision': pending['revision'], 'pending_sha256': hashlib.sha256(original_bytes).hexdigest(),
                             'created': expected, 'pids': sorted({row['pid'] for row in values})}
        assert len(boundaries[phase]['pids']) >= 2
    legacy = observations(root, 'legacy-v1-failure')
    raw_legacy = observations(root, 'raw-retries-original-v1')
    old = [row for row in legacy if row['event'] == 'action-failed']
    new = [row for row in raw_legacy if row['event'] == 'action-failed' and row['raw_enabled']]
    assert len(old) == len(new) == 1 and old[0]['pending_base64'] == new[0]['pending_base64']
    pending = json.loads(unpack(old[0]['pending_base64']))
    assert pending['version'] == 1 and pending.get('anchor_version') in (None, 2) and pending['mode'] == 3
    assert {row['id']: row['sha256'] for row in old[0]['revisions']} == {row['id']: row['sha256'] for row in new[0]['revisions']}
    assert old[0]['sdk_state_after'] == new[0]['sdk_state_after']
    received = observations(root, 'raw-native-HTTPS')
    snapshots = [row for row in received if row['event'] != 'actual-public-resolution']
    original_map = peer['wire_sha256']
    assert any(all({entry['id']: entry['sha256'] for entry in row['revisions']}.get(key) == sha for key, sha in original_map.items()) for row in snapshots)
    null_typed = [typed for row in snapshots for typed in row['typed_rows'] if typed['revision'] in peer['null_revision_ids']]
    assert null_typed and all(typed['safe'] and not typed['has_location'] and typed['quote_bytes_base64'] is None for typed in null_typed)
    edits = [row for row in snapshots if row['event'] == 'actual-submit' and row['submission']['kind'] == 4]
    restores = [row for row in snapshots if row['event'] == 'actual-submit' and row['submission']['operation'] == 2]
    assert {row['submission']['anchor_version'] for row in edits} == {1, 2}
    assert {row['submission']['anchor_version'] for row in restores} == {1, 2}
    for row in edits + restores:
        request = row['submission']
        retained = next(entry for entry in row['revisions'] if entry['id'] == request['revision'])
        assert retained['anchor_version'] == request['anchor_version']
    assert len({row['pid'] for row in received}) >= 2
    return {'real_pdf_point_records': len(points), 'real_pdf_NUL_range_records': len(ranges),
            'actual_public_FOUND_observations': len(found), 'kill_replay': boundaries,
            'old_pending_sha256': hashlib.sha256(unpack(old[0]['pending_base64'])).hexdigest(),
            'old_pending_revision': pending['revision'], 'real_received_NULL_typed_rows': len(null_typed),
            'source_versions_edited_and_restored': [1, 2], 'original_peer_wires_unchanged': len(original_map),
            'owner_observations': len(all_rows)}
