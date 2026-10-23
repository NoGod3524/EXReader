#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Strict Android host evidence validation. Build and execution happen only in CI."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
SDK_BASE = '9854061be331fe603a1822d9b2b36ee357154927'
REVIEW_BASE = '9854061be331fe603a1822d9b2b36ee357154927'
WALKTHROUGH_IDS = '''cold_start_shelf picker_cancel import_epub open_epub page_next page_prev font_increase font_decrease touch_select copy_selection note_add notes_read note_edit note_navigate rotate_landscape rotate_portrait activity_rebuild background_resume process_restart_reflow notes_after_restart note_delete import_txt open_txt import_pdf open_pdf pdf_next pdf_prev pdf_zoom pdf_select_copy pdf_note_add pdf_process_restart pdf_note_delete import_bigchapter open_bigchapter bigchapter_next import_ambiguous ambiguous_restore corrupt_import retry_import duplicate_import too_large cancel_large_import book_switch accessibility_semantics native_metrics'''.split()
REVIEW_IDS = '''duplicate_cancel_keeps_original new_copy_cancel_cleans_file late_insert_cancel_rolls_back_new_book duplicate_late_cancel_keeps_original late_cancel_after_commit_reports_success failed_open_preserves_reader failed_progress_preserves_frame selection_invalidated_while_busy unicode_comment_round_trip destroyed_activity_releases_worker'''.split()
BOUNDED_IDS = '''bounded_source_delete_restore bounded_cross_chapter_font bounded_note_domain_restart bounded_duplicate_spine bounded_legacy_dedup bounded_schema6_upgrade bounded_progress_write_reject bounded_external_commit_reopen bounded_damaged_next_preserves_frame bounded_budget_limit_preserves_frame bounded_empty_next_explicit_error'''.split()
SUITES = {'walkthrough': ('HostWalkthroughTest', 'walkthrough', 'device', WALKTHROUGH_IDS),
          'review': ('HostReviewTest', 'review', 'review', REVIEW_IDS),
          'bounded': ('HostReviewTest', 'bounded', 'bounded', BOUNDED_IDS)}
PACKAGES = {'app-debug.apk': 'org.exreader.host', 'uitest-debug.apk': 'org.exreader.host.uitest',
            'uitest-debug-androidTest.apk': 'org.exreader.host.uitest.test'}
SOURCE_PATHS = ['CMakeLists.txt', 'src', 'include', 'cmake', 'bindings/jni', 'examples/android',
                'tools/build_android_host.py', 'tools/check_android_host.py', 'tools/android_host_evidence.py',
                'tools/run_android_host_evidence.py', 'tools/host_font.py', 'tests/android_host',
                '.github/workflows/wp13-android.yml']
SOURCE_PATHS += ['.github/workflows/r5-android-bounded-candidate.yml']


def ownership():
    command = ['git', '-C', str(ROOT)]
    tested = subprocess.check_output([*command, 'rev-parse', 'HEAD'], text=True).strip()
    candidate_base = os.environ.get('ANDROID_CANDIDATE_SDK_BASE')
    sdk_base = candidate_base or SDK_BASE
    review_base = candidate_base or REVIEW_BASE
    boundary = os.environ.get('ANDROID_OWNERSHIP_HEAD') or tested
    require(re.fullmatch(r'[0-9a-f]{40}', boundary), 'ownership boundary must be a complete commit identity')
    require(subprocess.run([*command, 'merge-base', '--is-ancestor', review_base, boundary],
                           capture_output=True).returncode == 0, 'delivery is not an ancestor of the reviewed source')
    require(subprocess.run([*command, 'merge-base', '--is-ancestor', boundary, tested],
                           capture_output=True).returncode == 0, 'reviewed Android source is not an ancestor of the tested source')
    require(subprocess.run([*command, 'diff', '--quiet', sdk_base, 'HEAD', '--',
                           'src', 'include', 'bindings', 'cmake', 'CMakeLists.txt'],
                           capture_output=True).returncode == 0, 'installed SDK source differs from the frozen baseline')
    changed = subprocess.check_output([*command, 'diff', '--name-only', review_base, boundary], text=True).splitlines()
    prefixes = ('examples/android/', 'tests/android_host/')
    files = {'tools/check_android_host.py', 'tools/build_android_host.py', 'tools/android_host_evidence.py',
             'tools/run_android_host_evidence.py', '.github/workflows/wp13-android.yml',
             '.github/workflows/wp13-android-diagnostics.yml',
             '.github/workflows/r5-android-bounded-candidate.yml', 'docs/R5-ANDROID-BOUNDED.md',
             'docs/WP13-ANDROID.md', 'docs/WP13-ANDROID-REVIEW.md', 'docs/validation/wp13-android-review.json'}
    require(all(name.startswith(prefixes) or name in files for name in changed), 'review changes exceed the Android package ownership')
    return {'sdk_base': sdk_base, 'review_base': review_base, 'ownership_head': boundary,
            'candidate_only': bool(candidate_base),
            'tested_source': tested, 'changed_files': changed}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha256(path):
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            sha.update(chunk)
    return sha.hexdigest()


def load(path):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    require(isinstance(value, dict) and value, 'missing or invalid JSON object: ' + str(path))
    return value


def inventory(root):
    root = Path(root).resolve(strict=True)
    files = {}
    for path in sorted(root.rglob('*')):
        require(path.resolve().is_relative_to(root), 'evidence file escapes its root')
        if path.is_file():
            files[path.relative_to(root).as_posix()] = sha256(path)
    require(files, 'empty file inventory: ' + str(root))
    return files


def source_files():
    names = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '--', *SOURCE_PATHS], text=True).splitlines()
    require(names, 'source file inventory missing')
    return {name: sha256(ROOT/name) for name in names}


def cloud_identity():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Android acceptance runs only in cloud CI')
    return {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
            'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'job': os.environ['GITHUB_JOB']}


def check_identity(value, expected):
    for name, identity in expected.items():
        require(value.get(name) == identity, 'identity mismatch: ' + name)


def native_record(data):
    require(data[:6] == b'\x7fELF\x02\x01', 'native program is not a 64-bit little-endian ELF')
    require(struct.unpack_from('<H', data, 18)[0] == 62, 'native program is not x86_64')
    phoff = struct.unpack_from('<Q', data, 32)[0]
    stride, count = struct.unpack_from('<HH', data, 54)
    alignments = []
    build_ids = []
    for index in range(count):
        offset = phoff + index * stride
        kind = struct.unpack_from('<I', data, offset)[0]
        if kind == 1:
            alignments.append(struct.unpack_from('<Q', data, offset + 48)[0])
        if kind == 4:
            start = struct.unpack_from('<Q', data, offset + 8)[0]
            end = start + struct.unpack_from('<Q', data, offset + 32)[0]
            while start + 12 <= end:
                name_size, value_size, note_kind = struct.unpack_from('<III', data, start)
                start += 12
                name = data[start:start + name_size]
                start += (name_size + 3) & ~3
                value = data[start:start + value_size]
                start += (value_size + 3) & ~3
                if name.rstrip(b'\0') == b'GNU' and note_kind == 3:
                    build_ids.append(value.hex())
    require(alignments and min(alignments) >= 16384, 'native LOAD alignment is below 16 KiB')
    require(len(set(build_ids)) == 1 and build_ids[0], 'native build identity missing or ambiguous')
    return {'sha256': hashlib.sha256(data).hexdigest(), 'machine': 62,
            'load_alignments': sorted(set(alignments)), 'build_id': build_ids[0]}


def apk_native(apk):
    with zipfile.ZipFile(apk) as archive:
        expected = {'lib/x86_64/' + name for name in ('libexreader.so', 'libexreader_jni.so', 'libexreader_host.so')}
        names = [name for name in archive.namelist() if name.startswith('lib/') and name.endswith('.so')]
        require(len(names) == len(expected) and set(names) == expected, 'APK native set differs from the declared x86_64 runtime')
        return {name: native_record(archive.read(name)) for name in sorted(expected)}


def check_png(path):
    data = Path(path).read_bytes()
    require(data[:8] == b'\x89PNG\r\n\x1a\n', 'invalid screenshot signature')
    chunks, offset = [], 8
    while offset < len(data):
        require(offset + 12 <= len(data), 'truncated PNG chunk')
        size = int.from_bytes(data[offset:offset + 4], 'big')
        kind = data[offset + 4:offset + 8]
        end = offset + 8 + size
        require(end + 4 <= len(data) and zlib.crc32(data[offset + 4:end]) ==
                int.from_bytes(data[end:end + 4], 'big'), 'invalid PNG chunk length or CRC')
        chunks.append((kind, data[offset + 8:end]))
        offset = end + 4
    require(chunks and chunks[0][0] == b'IHDR' and len(chunks[0][1]) == 13 and
            chunks[-1] == (b'IEND', b'') and sum(kind == b'IHDR' for kind, body in chunks) == 1 and
            sum(kind == b'IEND' for kind, body in chunks) == 1, 'invalid PNG structure')
    width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', chunks[0][1])
    require(0 < width <= 8192 and 0 < height <= 8192 and width * height <= 20000000 and
            depth == 8 and color in (0, 2, 4, 6) and (compression, filtering, interlace) == (0, 0, 0),
            'unsupported or invalid screenshot dimensions/encoding')
    stride = width * {0: 1, 2: 3, 4: 2, 6: 4}[color] + 1
    decoder = zlib.decompressobj()
    raw = decoder.decompress(b''.join(body for kind, body in chunks if kind == b'IDAT'), stride * height + 1)
    require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail and len(raw) == stride * height and
            all(raw[index] <= 4 for index in range(0, len(raw), stride)), 'invalid PNG pixel stream')


def check_instrumentation(path, class_name, method):
    text = Path(path).read_text(encoding='utf-8')
    require(re.search(r'^OK \(1 test\)\s*$', text, re.M) is not None, 'instrumentation did not pass exactly one test')
    require(not any(value in text for value in ('INSTRUMENTATION_FAILED', 'FAILURES!!!', 'INSTRUMENTATION_ABORTED')),
            'instrumentation reported failure')
    require(set(re.findall(r'^INSTRUMENTATION_STATUS: class=(.+)\s*$', text, re.M)) ==
            {'org.exreader.host.uitest.' + class_name}, 'instrumentation class identity mismatch')
    require(set(re.findall(r'^INSTRUMENTATION_STATUS: test=(.+)\s*$', text, re.M)) == {method},
            'instrumentation method identity mismatch')
    require(re.findall(r'^INSTRUMENTATION_CODE: (-?\d+)\s*$', text, re.M) == ['-1'],
            'instrumentation terminal status missing')
    statuses = re.findall(r'^INSTRUMENTATION_STATUS_CODE: (-?\d+)\s*$', text, re.M)
    require(statuses == ['1', '0'], 'instrumentation skipped, failed or executed an unexpected test')


FRAME_FIELDS = '''book index part path start end anchor_kind anchor_sha256 font zoom render_scale bitmap_width bitmap_height glyph_font_first viewport_width viewport_height fit offset_x offset_y selection_mode selection_start selection_end'''.split()


def check_drawn_frame(state):
    require(isinstance(state, dict), 'frame observation missing')
    require(type(state.get('pid')) is int and state['pid'] > 0 and type(state.get('view')) is int,
            'frame process/view identity missing')
    require(type(state.get('accepted_token')) is int and state['accepted_token'] > 0 and
            state['accepted_token'] == state.get('drawn_token') == state.get('settled_token') and
            type(state.get('revision')) is int and state['revision'] > 0 and
            state['revision'] == state.get('drawn_revision') == state.get('settled_revision'),
            'accepted frame has not actually drawn and settled')
    require(type(state.get('drawn_ns')) is int and type(state.get('settled_ns')) is int and
            0 < state['drawn_ns'] <= state['settled_ns'], 'frame after-draw timing missing')
    for name in ('viewport_width', 'viewport_height', 'bitmap_width', 'bitmap_height'):
        require(type(state.get(name)) is int and 0 < state[name] <= 8192, 'invalid frame dimensions: ' + name)
    require(state['viewport_width'] == state.get('drawn_width') and state['viewport_height'] == state.get('drawn_height'),
            'drawn viewport differs from accepted viewport')
    for name in ('fit', 'zoom', 'render_scale'):
        require(type(state.get(name)) in (int, float) and math.isfinite(state[name]) and state[name] > 0,
                'invalid actual frame scale: ' + name)
    for name in ('offset_x', 'offset_y'):
        require(type(state.get(name)) in (int, float) and math.isfinite(state[name]), 'invalid actual frame fit offset')
    require(all(name in state for name in FRAME_FIELDS), 'frame semantic state is incomplete')
    require(type(state['book']) is int and state['book'] > 0 and type(state['index']) is int and state['index'] >= 0 and
            type(state['start']) is int and type(state['end']) is int and 0 <= state['start'] <= state['end'],
            'frame source position invalid')
    if state['anchor_kind'] == 'fixed_page':
        require(state['font'] is None, 'fixed-page font must be explicitly not applicable')
    else:
        require(type(state['font']) in (int, float) and math.isfinite(state['font']) and state['font'] > 0,
                'actual layout font missing or defaulted')
    if state['anchor_kind'] == 'bounded_point':
        require(type(state['part']) is int and state['part'] >= 0 and isinstance(state['path'], str) and state['path'] and
                re.fullmatch(r'[0-9a-f]{64}', state['anchor_sha256'] or ''), 'bounded part/point anchor identity missing')


def frame_key(state, bounds):
    return tuple(state[name] for name in ('pid', 'view', 'accepted_token', 'revision', 'viewport_width', 'viewport_height')) + tuple(bounds)


def check_frame_observations(root, case):
    required = case['id'] in ('process_restart_reflow', 'pdf_process_restart')
    proofs = case.get('frame_observations', [])
    roles = ['pretransition', 'reference', 'restored'] if case['id'] == 'pdf_process_restart' else ['reference', 'restored']
    require(isinstance(proofs, list) and (not required or [proof.get('role') for proof in proofs] == roles),
            'restart frame observations missing or reordered')
    accepted = []
    frame_paths = set()
    for proof in proofs:
        require(proof.get('status') == 'stable_after_draw' and proof.get('budget_ms') == 8000 and
                type(proof.get('elapsed_ms')) is int and 0 < proof['elapsed_ms'] <= 8000 and
                'initial_observation' in proof, 'stable frame observation exceeded the original 8s budget')
        samples = proof.get('samples', [])
        require(isinstance(samples, list) and len(samples) >= 2, 'consecutive frame samples missing')
        for sample in samples:
            name = sample.get('png', '')
            require(isinstance(name, str) and re.fullmatch(r'frames/[A-Za-z0-9_-]+\.png', name), 'frame PNG path invalid')
            require(name not in frame_paths, 'frame PNG was reused for another sample')
            frame_paths.add(name)
            path = root/name
            check_png(path)
            require(path.stat().st_size == sample.get('png_bytes') and sha256(path) == sample.get('png_sha256'),
                    'frame PNG identity mismatch')
            require(re.fullmatch(r'[0-9a-f]{64}', sample.get('pixel_sha256', '')), 'frame pixel identity missing')
        pair = samples[-2:]
        for sample in pair:
            require(sample.get('same_frame') is True and sample.get('within_budget') is True and
                    type(sample.get('captured_elapsed_ms')) is int and 0 <= sample['captured_elapsed_ms'] <= 8000,
                    'stable sample crossed a frame or deadline')
            before, after = sample.get('observation'), sample.get('after_observation')
            check_drawn_frame(before)
            check_drawn_frame(after)
            bounds = sample.get('bounds')
            require(isinstance(bounds, list) and len(bounds) == 4 and all(type(value) is int for value in bounds) and
                    0 <= bounds[0] < bounds[2] and 0 <= bounds[1] < bounds[3], 'frame viewport bounds missing')
            require(bounds == sample.get('after_bounds') and frame_key(before, bounds) == frame_key(after, sample['after_bounds']) and
                    all(before[name] == after[name] for name in FRAME_FIELDS), 'capture crossed accepted frame state')
            width, height = struct.unpack_from('>II', (root/sample['png']).read_bytes(), 16)
            require((width, height) == (bounds[2]-bounds[0], bounds[3]-bounds[1]), 'frame PNG differs from viewport crop')
        require(frame_key(pair[0]['observation'], pair[0]['bounds']) == frame_key(pair[1]['observation'], pair[1]['bounds']) and
                all(pair[0]['observation'][name] == pair[1]['observation'][name] for name in FRAME_FIELDS) and
                pair[0]['pixel_sha256'] == pair[1]['pixel_sha256'] == proof.get('pixel_sha256') and
                pair[0]['png_sha256'] == pair[1]['png_sha256'], 'consecutive screenshots are not stable')
        accepted.append(pair[-1])
    if required:
        if case['id'] == 'pdf_process_restart':
            prior, reference = accepted[:2]
            require(prior['pixel_sha256'] != reference['pixel_sha256'] and prior['png_sha256'] != reference['png_sha256'],
                    'PDF page turn reused the previous page pixels')
        before, after = accepted[-2:]
        require(before['observation']['pid'] != after['observation']['pid'], 'restart did not create a new reader process')
        require(before['pixel_sha256'] == after['pixel_sha256'] and before['png_sha256'] == after['png_sha256'],
                'restart changed the exact accepted pixels')
        require(all(before['observation'][name] == after['observation'][name] for name in FRAME_FIELDS) and
                before['bounds'] == after['bounds'], 'restart changed part/offset/anchor/font/viewport/fit/selection')


def check_suite(evidence, suite, expected, build):
    class_name, method, folder, required_ids = SUITES[suite]
    root = Path(evidence)/folder
    require(root.resolve().is_relative_to(Path(evidence).resolve()), 'suite escapes evidence root')
    report = load(root/'validation.json')
    check_identity(report, {key: expected[key] for key in ('source_sha', 'run_id', 'attempt')})
    require(report.get('apk_sha256') == build['artifacts']['app-debug.apk']['sha256'] and
            report.get('test_apk_sha256') == build['artifacts']['uitest-debug-androidTest.apk']['sha256'],
            'device report APK identity mismatch')
    require(report.get('schema') == 1 and report.get('package') == 'org.exreader.host' and
            report.get('physical_device_execution') is False and report.get('device_is_emulator') is True and
            report.get('api') == 34 and report.get('abi') == 'x86_64', 'device scope identity mismatch')
    cases = report.get('cases')
    require(isinstance(cases, list) and [case.get('id') for case in cases] == required_ids,
            suite + ': missing, duplicate, reordered or unknown case identity')
    require(report.get('summary') == {'total': len(required_ids), 'passed': len(required_ids), 'failed': 0, 'skipped': 0},
            suite + ': failed, skipped or inconsistent summary')
    shots, case_files = set(), set()
    titles = {}
    if suite == 'walkthrough':
        source = (ROOT/'examples/android/uitest/src/androidTest/java/org/exreader/host/uitest/HostWalkthroughTest.java').read_text()
        declared = re.findall(r'step\("([a-z0-9_]+)",\s*"([^"]+)"', source)
        require([item[0] for item in declared] == WALKTHROUGH_IDS, 'declared walkthrough case contract changed')
        original = subprocess.check_output(['git', '-C', str(ROOT), 'show', REVIEW_BASE +
            ':examples/android/uitest/src/androidTest/java/org/exreader/host/uitest/HostWalkthroughTest.java'], text=True)
        require(declared == re.findall(r'step\("([a-z0-9_]+)",\s*"([^"]+)"', original),
                'original walkthrough titles/order changed')
        titles = dict(declared)
    for index, case in enumerate(cases, 1):
        case_id = case['id']
        require(case.get('status') == 'pass', suite + ': case did not pass: ' + case_id)
        if suite == 'walkthrough':
            check_frame_observations(root, case)
        if titles:
            require(case['title'] == titles[case_id], 'walkthrough case title identity mismatch')
        shot = case.get('screenshot', '')
        require(isinstance(shot, str) and re.fullmatch(r'shots/[A-Za-z0-9_-]+\.png', shot) and shot not in shots,
                'case screenshot identity missing, reused or outside shots')
        shots.add(shot)
        path = root/shot
        require(path.resolve().is_relative_to(root.resolve()), 'screenshot escapes suite root')
        check_png(path)
        require(case.get('screenshot_bytes') == path.stat().st_size and case.get('screenshot_sha256') == sha256(path),
                'case screenshot identity mismatch')
        case_name = (f'{index:02d}-' if suite == 'walkthrough' else '') + case_id + '.json'
        case_path = root/'cases'/case_name
        require(case_path.resolve().is_relative_to(root.resolve()) and load(case_path) == case,
                'per-case JSON differs from the aggregate report')
        case_files.add(case_name)
        if suite != 'walkthrough':
            assertions = case.get('assertions')
            require(isinstance(assertions, list) and assertions and all(isinstance(name, str) and name for name in assertions),
                    'review assertions missing')
    require({path.name for path in (root/'cases').iterdir()} == case_files, 'unexpected or missing per-case JSON')
    require({path.name for path in (root/'shots').iterdir()} == {Path(name).name for name in shots},
            'unexpected or missing screenshot files')
    check_instrumentation(Path(evidence)/(suite + '-instrumentation.txt'), class_name, method)
    log = (Path(evidence)/(suite + '-logcat.txt')).read_text(errors='replace')
    require(log.strip(), 'raw native/app log missing')
    require(not any(value in log for value in ('FATAL EXCEPTION', 'UnsatisfiedLinkError', 'Fatal signal')),
            'raw log records a fatal app/native failure')
    if suite == 'walkthrough':
        require(log.count('metric {"event":"page"') >= 12 and 'handle open book=' in log and
                'handle close book=' in log, 'native page/ownership evidence incomplete')
    elif suite == 'review':
        source = (ROOT/'examples/android/uitest/src/androidTest/java/org/exreader/host/uitest/HostReviewTest.java').read_text()
        require(re.findall(r'run\("([a-z0-9_]+)"', source) == REVIEW_IDS, 'review case source contract changed')
        sequence = report.get('sequence', {})
        require(all(sequence.get(key) == value for key, value in {
            'fixture': 'Large.epub', 'rendered_pages': 49, 'native_next_calls': 49,
            'recovery_calls': 0}.items()) and
            type(sequence.get('sequential_elapsed_ms')) is int and sequence['sequential_elapsed_ms'] > 0,
            '49-page sequential acceptance is incomplete')
        paging = [json.loads(value) for value in re.findall(r'paging (\{[^\r\n]+\})', log)]
        require(any(value.get('index') == 48 and value.get('native_next_calls') == 49 and
                    value.get('recovery_calls') == 0 for value in paging),
                'raw paging counters do not establish 49 sequential pages')
        require('worker shutdown complete' in log, 'destroyed Activity worker completion is missing')
    else:
        source = (ROOT/'examples/android/uitest/src/androidTest/java/org/exreader/host/uitest/HostReviewTest.java').read_text()
        require(re.findall(r'boundedCase\("([a-z0-9_]+)"', source) == BOUNDED_IDS, 'bounded case source contract changed')
        require('bounded page {' in log and 'storage mode book=' in log and
                'host-review' in log and all(code in log for code in ('code 7','code 3','code 5','code 6')) and
                'Empty reading chapter is not supported' in log,
                'bounded storage/native page/real write rejection/external-source evidence incomplete')
    return report


def check_evidence(evidence, build_path, stage, upstream, expected=None):
    expected = expected or cloud_identity()
    actual = cloud_identity()
    check_identity(actual, expected)
    require(set(upstream) == {'build', 'static', 'emulator'} and all(value == 'success' for value in upstream.values()),
            'build, static or emulator upstream did not succeed')
    build = load(build_path)
    check_identity(build, expected)
    require(build.get('schema') == 2 and build.get('sdk_built') is True and build.get('apk_built') is True,
            'build provenance missing or skipped')
    require(build.get('source_files_sha256') == source_files(), 'tested source files differ from the build')
    require(build.get('ownership') == ownership(), 'build ownership proof mismatch')
    require(build.get('sdk_files_sha256') == inventory(stage), 'installed SDK bytes differ from the build')
    require(build.get('abi') == 'x86_64' and build.get('abi_version') == 1 and build.get('library_schema') == 7 and
            build.get('ndk') == '27.0.12077973' and build.get('gradle') == '8.9', 'SDK/toolchain identity mismatch')
    header = (ROOT/'include/exr/base.h').read_text()
    require(build.get('sdk_version') == re.search(r'#define EXR_VERSION "([^"]+)"', header)[1], 'SDK version mismatch')
    evidence = Path(evidence)
    require(set(build.get('artifacts', {})) == set(PACKAGES), 'incomplete APK build set')
    for name in PACKAGES:
        for path in (evidence/'artifacts'/name, evidence/'installed'/name):
            require(sha256(path) == build['artifacts'][name]['sha256'] and path.stat().st_size == build['artifacts'][name]['size'],
                    'packaged or installed APK identity mismatch: ' + name)
    native = apk_native(evidence/'artifacts/app-debug.apk')
    require(native == build.get('native'), 'actual APK native metadata mismatch')
    for library in ('libexreader.so', 'libexreader_jni.so'):
        installed = native_record((Path(stage)/'lib'/library).read_bytes())
        require(native['lib/x86_64/' + library]['build_id'] == installed['build_id'],
                'APK runtime differs from installed SDK: ' + library)
    with zipfile.ZipFile(evidence/'artifacts/app-debug.apk') as archive:
        require(hashlib.sha256(archive.read('assets/Reader.otf')).hexdigest() == build['font']['sha256'], 'packaged font identity mismatch')
    execution = load(evidence/'execution.json')
    check_identity(execution, expected)
    require(execution.get('completed') is True and execution.get('errors') == [], 'device execution/collection failed')
    require(execution.get('installed') == {name: build['artifacts'][name]['sha256'] for name in PACKAGES},
            'device installed package set mismatch')
    fixture_root = Path(build_path).parent/'fixtures'
    fixtures = build.get('fixtures', {})
    require(fixtures and load(fixture_root/'fixtures.json') == fixtures, 'fixture manifest mismatch')
    for name, record in fixtures.items():
        require(Path(name).name == name and sha256(fixture_root/name) == record['sha256'] and
                (fixture_root/name).stat().st_size == record['size'], 'fixture bytes mismatch')
    require(execution.get('fixtures') == {name: value['sha256'] for name, value in fixtures.items()}, 'device fixture identity mismatch')
    suites = execution.get('suites', {})
    require(set(suites) == set(SUITES), 'suite execution set is incomplete')
    for suite, (class_name, method, folder, ids) in SUITES.items():
        value = suites[suite]
        require(value.get('class') == 'org.exreader.host.uitest.' + class_name and value.get('method') == method and
                all(value.get(key) == 0 for key in ('exit_code', 'log_exit_code', 'pull_exit_code')),
                'suite execution identity or evidence collection failed')
    reports = {suite: check_suite(evidence, suite, expected, build) for suite in SUITES}
    for suite in SUITES:
        for suffix in ('instrumentation.txt', 'logcat.txt'):
            name = suite + '-' + suffix
            require(execution['files_sha256'].get(name) == sha256(evidence/name), 'raw log identity mismatch')
    return {'schema': 2, 'package': 'org.exreader.host', 'source_sha': expected['source_sha'],
            'run': {'id': expected['run_id'], 'attempt': expected['attempt']},
            'physical_device_execution': False, 'build': build, 'cases': reports['walkthrough']['cases'],
            'summary': reports['walkthrough']['summary'], 'review': reports['review'], 'bounded': reports['bounded'],
            'execution_sha256': sha256(evidence/'execution.json')}
