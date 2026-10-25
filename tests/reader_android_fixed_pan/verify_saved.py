"""Actions-only source-bound Pan evidence verification; reusable by host integration."""
import ast
import hashlib
import io
import json
import os
from pathlib import Path
from PIL import Image

assert os.environ.get('GITHUB_ACTIONS') == 'true'
Image.MAX_IMAGE_PIXELS = 16_000_000

def verify_saved(read, source, run, attempt=1):
    """read(suffix, byte_limit) must return one authenticated ZIP member."""
    def document(suffix):
        return json.loads(read(suffix, 8 * 1024**2))
    def bound(value):
        assert value['source_sha'] == source and str(value['run_id']) == str(run) and str(value['attempt']) == str(attempt)
        return value
    def image(data):
        with Image.open(io.BytesIO(data)) as check:
            assert check.format == 'PNG' and check.width * check.height <= Image.MAX_IMAGE_PIXELS
            check.verify()
        with Image.open(io.BytesIO(data)) as check:
            return check.convert('RGB')
    expected = next(ast.literal_eval(node.value) for node in ast.parse(Path(__file__).with_name('run_ui.py').read_text()).body
                    if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'expected' for target in node.targets))
    base = 'android-fixed-pan/'
    result = bound(document(base + 'ui/result.json'))
    assert result['accepted'] is True and result['checks'] == 8 and result['fixed_page_pan_accepted'] is True
    for name in ('physical_device', 'page_colors_accepted', 'performance_accepted', 'complete_product', 'talkback_speech_accepted'):
        assert result[name] is False
    assert result['api'] == 34 and result['abi'] == 'x86_64'
    assert [row['phase'] for row in result['phases']] == ['first', 'reopen']
    assert [row['count'] for row in result['phases']] == [7, 1] and len({row['pid'] for row in result['phases']}) == 2
    manifest = document(base + 'fixtures/manifest.json')
    books = {row['file']: row for row in manifest['books']}
    roles = {row['role']: row for row in manifest['books']}
    assert len(books) == len(roles) == 11 and all('crop' + str(angle) in roles for angle in (0, 90, 180, 270))
    originals = {}
    for name, row in books.items():
        data = read(base + 'fixtures/' + name, 32 * 1024**2)
        assert len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256']
        originals[name] = data
    assert len(result['sources']) == 22 and {(row['phase'], row['file']) for row in result['sources']} == {(phase, name) for phase in expected for name in books}
    for row in result['sources']:
        assert row['bytes'] == books[row['file']]['bytes'] and row['sha256'] == books[row['file']]['sha256']
    plan = manifest['pan_expected']
    assert plan['plan_precedes_sdk_read'] is True and plan['width'] == 600 and plan['height'] == 800
    assert plan['rgb'] == [[200, 40, 40], [40, 180, 60], [40, 70, 200], [210, 180, 30]]
    assert plan['points'] == [[30, 30], [570, 30], [30, 770], [570, 770]]
    import zipfile
    with zipfile.ZipFile(io.BytesIO(originals[roles['cbz']['file']])) as comic:
        assert comic.namelist() == ['001.png', '002.png', '003.png']
        for name in comic.namelist():
            assert comic.getinfo(name).file_size <= 4 * 1024**2
            decoded = image(comic.read(name)); assert decoded.size == (600, 800)
            for corner, rgb in enumerate(plan['rgb']):
                x = (corner % 2) * 300; y = (corner // 2) * 400
                assert decoded.crop((x, y, x + 300, y + 400)).getextrema() == tuple((c, c) for c in rgb)
    observations = {}; phases = {}
    for row in result['phases']:
        bound(row); phase = row['phase']; phases[phase] = row
        assert row['passed'] is True and [check['name'] for check in row['checks']] == expected[phase] and all(check['pass'] is True for check in row['checks'])
        assert row == document(base + 'ui/' + phase + '-report.json')
        instrument = read(base + 'ui/' + phase + '-instrumentation.txt', 1024**2).decode()
        assert 'FIXED_PAN_UI_PASS ' + phase in instrument and 'INSTRUMENTATION_CODE: -1' in instrument
        assert all(name in instrument for name in expected[phase])
        for item in row['observations']:
            key = (phase, item['name']); assert key not in observations; observations[key] = item
    names = ['cbz-corner-' + str(i) for i in range(4)] + ['pdf-corner-' + str(i) for i in range(4)]
    names += ['crop' + str(angle) + suffix for angle in (0, 90, 180, 270) for suffix in ('-panned-selection', '-longpress-selection')]
    names += ['pdf-panned-selection', 'pdf-semantic-edge', 'pdf-cancelled-touch', 'pdf-axis-page-turn', 'txt-original-turn', 'cbz-rotation-reset']
    required_captures = {('first', name) for name in names} | {('reopen', 'cbz-reopened-pan')}
    assert set(observations) == required_captures and len(result['captures']) == len(required_captures) == 23
    screenshots = {}
    for row in result['captures']:
        key = (row['phase'], row['name']); assert key in observations and key not in screenshots
        data = read(base + 'ui/captures/' + row['phase'] + '-' + row['name'] + '.png', 16 * 1024**2)
        assert len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256'] and row['nodes'] == observations[key]['nodes']
        screenshots[key] = image(data)
    pixels = []
    for phase, report in phases.items():
        for point in report['display_pixels']:
            corner = point['corner']; assert 0 <= corner < 4
            role = point['role']; assert role in ('cbz', 'pdf', 'cbz-reopen')
            name = 'cbz-reopened-pan' if role == 'cbz-reopen' else role + '-corner-' + str(corner)
            rgb = plan['rgb'][corner]; expected_argb = 0xff000000 | (rgb[0] << 16) | (rgb[1] << 8) | rgb[2]
            assert point['argb'] == point['expected_argb'] == expected_argb
            assert [point['source_x'], point['source_y']] == plan['points'][corner]
            assert screenshots[(phase, name)].getpixel((point['screen_x'], point['screen_y'])) == tuple(rgb)
            pixels.append((phase, role, corner))
    assert len(pixels) == 9 and set(pixels) == {('first', role, corner) for role in ('cbz', 'pdf') for corner in range(4)} | {('reopen', 'cbz-reopen', 0)}
    expected_markers = {'crop0': 'BRA', 'crop90': 'TRA', 'crop180': 'TLA', 'crop270': 'BLA'}
    gestures = phases['first']['selection_gestures']; assert len(gestures) == 8 and phases['reopen']['selection_gestures'] == []
    seen = set()
    fields = ('viewport_width', 'viewport_height', 'offset_x', 'offset_y', 'accepted_token')
    for gesture in gestures:
        role = gesture['role']; press = gesture['long_press']; key = (role, press)
        assert role in expected_markers and isinstance(press, bool) and key not in seen; seen.add(key)
        assert gesture['expected'] == gesture['selected'] == roles[role]['visible_marker'] == expected_markers[role]
        assert gesture['held_ms'] == (650 if press else 60)
        before = gesture['before_mode']
        for stage in ('before_down', 'held', 'after'):
            frame = gesture[stage]
            assert all(frame[field] == before[field] for field in fields)
            assert frame['source_key'] == 'pdf:' + roles[role]['sha256'] and frame['index'] == 0
            assert abs(frame['bitmap_width'] / frame['render_scale'] - roles[role]['viewport_width']) < 1
            assert abs(frame['bitmap_height'] / frame['render_scale'] - roles[role]['viewport_height']) < 1
        # Before-gesture accessibility extras may retain the previous mode bit.
        # The original contract gates the entered held/after state and unchanged
        # actual viewport, rather than this additional cached precondition.
        assert gesture['held']['selection_mode'] is True and gesture['after']['selection_mode'] is True
        assert gesture['held']['selection_end'] > gesture['held']['selection_start']
    assert seen == {(role, press) for role in expected_markers for press in (False, True)}
    assert len(result['process_stops']) == 2
    for stop, report in zip(result['process_stops'], result['phases']):
        assert stop['phase'] == report['phase'] and stop['instrumentation_pid'] == report['pid'] and stop['requested'] is True and not stop['pid_after_stop']
    inherited = {}
    for suffix, count in [('host-session-android/ui/result.json', 16), ('android-search/ui/result.json', 15), ('android-navigation/ui/result.json', 18), ('android-reading/ui/result.json', 16), ('android-preferences/ui/result.json', 17), ('android-cbz-reading/ui/result.json', 10)]:
        value = bound(document(suffix)); assert value['accepted'] is True and value['checks'] == count; inherited[suffix] = count
    assert document('android-preferences/ui/result.json')['page_colors_accepted'] is False
    native = bound(document('android-cbz-reading/native/result.json'))
    assert native['accepted'] is True and native['single_original_shared_sdk'] is True and native['no_new_product_sqlite_or_sdk'] is True
    export = bound(document('session-android/export/device-report.json')); assert export['ok'] is True
    roundtrip = bound(document('session-android/roundtrip/result.json')); assert roundtrip['accepted'] is True and len(roundtrip['checks']) == 12 and all(row['passed'] for row in roundtrip['checks'])
    return {'pan_checks': 8, 'retained_ui_checks': sum(inherited.values()), 'combined_ui_checks': 100, 'screenshots': 23, 'independently_decoded_corner_samples': 9, 'original_reads': 22, 'selection_gestures': 8,
            'phases': [{'phase': row['phase'], 'pid': row['pid'], 'checks': row['count']} for row in result['phases']], 'inherited': inherited}
