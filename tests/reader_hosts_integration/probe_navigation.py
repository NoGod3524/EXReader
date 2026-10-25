"""Actions-only replay of an authenticated original GTK host; no acceptance."""
import configparser
from collections import Counter
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
from PIL import Image, ImageChops

from final import Bundle, fetch, identity, pages, require


def pixel_difference(before, after):
    require(before.size == after.size, 'original screenshot dimensions differ')
    difference = ImageChops.difference(before, after)
    count = 0; samples = []; deltas = Counter(); bounds = None
    for index, (a, b) in enumerate(zip(before.getdata(), after.getdata())):
        if a == b:continue
        x, y = index % before.width, index // before.width
        count += 1;deltas[max(abs(a[k] - b[k]) for k in range(3))] += 1
        if len(samples) < 24:samples.append([x, y, a, b])
        bounds = [x, y, x + 1, y + 1] if bounds is None else [
            min(bounds[0], x), min(bounds[1], y), max(bounds[2], x + 1), max(bounds[3], y + 1)]
    return dict(size=list(before.size), changed_pixels=count, changed_bounds=bounds,
                pil_changed_bounds=difference.getbbox(), max_channel_delta_histogram=dict(sorted(deltas.items())),
                before_rgb_sha256=hashlib.sha256(before.tobytes()).hexdigest(),
                after_rgb_sha256=hashlib.sha256(after.tobytes()).hexdigest(), samples=samples)


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    run_id = int(sys.argv[1])
    run = fetch('actions/runs/%d' % run_id)
    require(run['path'] == '.github/workflows/reader-hosts-integration.yml',
            'not a shared-host run')
    source, attempt = run['head_sha'], run['run_attempt']
    subprocess.run(['git', 'merge-base', '--is-ancestor', source, 'HEAD'], check=True)
    # Fixtures and actual navigation code must still match the old program.
    # Other host changes are listed as differences, never granted by this run.
    subprocess.run(['git', 'diff', '--exit-code', source, 'HEAD', '--', 'src', 'include', 'cmake',
                    'CMakeLists.txt', 'bindings', 'tests/fixtures', 'apps/reader/navigation',
                    'examples/linux/navigation_backend.inc', 'examples/linux/navigation_ui.inc',
                    'tests/reader_navigation/make_navigation_fixtures.py',
                    'tests/reader_gtk_navigation/make_inputs.py', 'tests/linux_host/generate_fixed.py'], check=True)
    producers = {'GTK G03 G04 reading records and retained native suites': 'reader-gtk-reading-records',
                 'GTK book file drop paste and retained native suites': 'reader-gtk-drop-import'}
    jobs = [j for j in pages('actions/runs/%d/attempts/%d/jobs' % (run_id, attempt), 'jobs')
            if j['name'] in producers]
    require(len(jobs) == 1 and jobs[0]['status'] == 'completed' and jobs[0]['head_sha'] == source,
            'original GTK producer missing')
    names = [a for a in pages('actions/runs/%d/artifacts' % run_id, 'artifacts')
             if a['name'] == '%s-%d-%d' % (producers[jobs[0]['name']], run_id, attempt)]
    require(len(names) == 1 and names[0]['workflow_run']['head_sha'] == source and
            names[0]['workflow_run']['id'] == run_id, 'foreign or duplicate original artifact')
    out = Path('build/navigation-probe');out.mkdir(parents=True, exist_ok=True)
    bundle = Bundle(names[0])
    try:
        original = bundle.report('gtk-navigation-ui/result.json');identity(original, source, run_id, attempt)
        (out / 'original-report.json').write_text(json.dumps(original, indent=2) + '\n')
        # Inspect the original failing captures as well as replaying the exact
        # program. A later pass cannot explain or replace those original bytes.
        captures = {}
        for label in ('before-directory', 'after-directory'):
            try:
                raw = bundle.bytes('gtk-navigation-ui/' + label + '.png', 16 * 1024**2)
            except ValueError:
                continue
            picture = Image.open(io.BytesIO(raw));require(picture.width <= 4096 and picture.height <= 4096, 'oversized original PNG')
            captures[label] = picture.convert('RGB')
            (out / ('original-' + label + '.png')).write_bytes(raw)
        original_pixels = dict(diagnostic_only=True, accepted=False, available=list(captures))
        if len(captures) == 2:
            before, after = captures['before-directory'], captures['after-directory']
            original_pixels.update(pixel_difference(before, after))
            state_bytes = bundle.bytes('gtk-navigation-ui/state.ini', 1024**2)
            (out / 'original-state.ini').write_bytes(state_bytes)
            state = configparser.ConfigParser(interpolation=None);state.read_string(state_bytes.decode())
            require(state.has_section('host') and state.has_section('preferences'), 'original failure state absent')
            host, preferences = dict(state['host']), dict(state['preferences'])
            width, height = int(preferences['bitmap_width']), int(preferences['bitmap_height'])
            page_x, page_y = int(host['page_x']), int(host['page_y'])
            page_width, page_height = int(host['page_width']), int(host['page_height'])
            x = page_x + (page_width - width) // 2;y = page_y + (page_height - height) // 2
            box = [x, y, x + width, y + height]
            require(0 < width <= 4096 and 0 < height <= 4096, 'unbounded original bitmap')
            roi_before, roi_after = before.crop(box), after.crop(box)
            roi_before.save(out / 'original-before-directory-derived-roi.png')
            roi_after.save(out / 'original-after-directory-derived-roi.png')
            original_pixels.update(original_state_sha256=hashlib.sha256(state_bytes).hexdigest(),
                failure_state=dict(host=host, preferences=preferences),
                original_image_formula_crop=box,
                crop_inside_window=(0 <= x < x + width <= before.width and 0 <= y < y + height <= before.height),
                original_scrolled_window=[page_x, page_y, page_width, page_height],
                original_formula_roi_difference=pixel_difference(roi_before, roi_after),
                viewport_difference=pixel_difference(before.crop([page_x, page_y, page_x + page_width, page_y + page_height]),
                                                     after.crop([page_x, page_y, page_x + page_width, page_y + page_height])),
                failure_state_painted_generation_matches_frame=(host['painted_generation'] == host['frame_generation']),
                before_state_available=bool(original.get('image_observations')),
                original_image_observations=original.get('image_observations', []),
                state_is_failure_finally_snapshot=True)
            tree_bytes = bundle.bytes('gtk-navigation-ui/failure-tree.json', 4 * 1024**2)
            tree = json.loads(tree_bytes)
            def walk_tree(node):
                yield node
                for child in node.get('children', []):yield from walk_tree(child)
            relevant = []
            for node in walk_tree(tree):
                if node['name'] in ('EXReader Linux', 'Rendered page; selectable text is in the adjacent panel',
                                    'Reading page gestures', 'Directory and page entries') or node['role'] == 'dialog':
                    relevant.append({key: node.get(key) for key in ('role', 'name', 'states', 'extents', 'path')})
            original_pixels.update(original_failure_tree_sha256=hashlib.sha256(tree_bytes).hexdigest(),
                                   original_failure_tree_geometry=relevant)
            # OCR is a bounded diagnostic of the immutable original captures,
            # never a pass/fail oracle or replacement for exact RGB equality.
            if not shutil.which('tesseract'):
                subprocess.run(['sudo', 'apt-get', 'install', '-y', 'tesseract-ocr'], check=True)
            ocr = {}
            for label in ('before-directory', 'after-directory'):
                text = subprocess.check_output(['tesseract', str(out / ('original-' + label + '.png')),
                                                'stdout', '--psm', '11', 'tsv'], text=True, timeout=30)
                (out / ('original-' + label + '.tsv')).write_text(text)
                words = []
                for row in text.splitlines()[1:]:
                    columns = row.split('\t', 11)
                    if len(columns) == 12 and columns[11].strip():
                        words.append(dict(text=columns[11], bounds=list(map(int, columns[6:10])), confidence=columns[10]))
                require(len(words) <= 2000, 'unbounded original screenshot OCR')
                ocr[label] = words
            original_pixels.update(original_capture_ocr=ocr,
                ocr_version=subprocess.check_output(['tesseract', '--version'], text=True).splitlines()[0])
        (out / 'original-pixel-difference.json').write_text(json.dumps(original_pixels, indent=2) + '\n')
        print(json.dumps(dict(original_pixel_difference=original_pixels)), flush=True)
        # CFI inputs are emitted by the original installed SDK consumer. Copy
        # the authenticated original fixtures, including those captured CFIs.
        fixture_hashes = {};fixture_bytes = 0
        for item in bundle.zip.infolist():
            parts = PurePosixPath(item.filename).parts
            if 'gtk-navigation-fixtures' not in parts or item.is_dir():continue
            relative = PurePosixPath(*parts[parts.index('gtk-navigation-fixtures') + 1:])
            require(relative.parts and str(relative) not in fixture_hashes and len(fixture_hashes) < 200,
                    'duplicate or unbounded original navigation fixtures')
            data = bundle.bytes(item.filename, 32 * 1024**2);fixture_bytes += len(data)
            require(fixture_bytes <= 64 * 1024**2, 'unbounded navigation fixture bytes')
            destination = out / 'fixtures' / str(relative)
            destination.parent.mkdir(parents=True, exist_ok=True);destination.write_bytes(data)
            fixture_hashes[str(relative)] = hashlib.sha256(data).hexdigest()
        require({'surrogate.cfi', 'collapsed.cfi', 'normal.cfi', 'cancel.epub'} <= set(fixture_hashes),
                'actual captured navigation inputs absent')
        payload = out / 'payload';payload.mkdir()
        found, members, unpacked = set(), 0, 0
        info = bundle.info('account-package/EXReader-Linux.tar.gz')
        with bundle.zip.open(info) as stream, tarfile.open(fileobj=stream, mode='r|gz') as archive:
            for entry in archive:
                members += 1;unpacked += entry.size
                require(members <= 10000 and 0 <= entry.size <= 128 * 1024**2 and unpacked <= 512 * 1024**2,
                        'oversized original host package')
                target = next((name for name in ('bin/exreader-linux', 'Reader.otf')
                               if entry.name == name or entry.name.endswith('/' + name)), None)
                if target is None:continue
                require(target not in found and entry.isfile(), 'duplicate or nonregular host member')
                found.add(target)
                data = archive.extractfile(entry).read(entry.size + 1)
                require(len(data) == entry.size, 'truncated original host member')
                path = payload / target;path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(data)
        require(found == {'bin/exreader-linux', 'Reader.otf'}, 'original host binary/font absent')
        binary = payload / 'bin/exreader-linux';binary.chmod(0o755)
        require(hashlib.sha256(binary.read_bytes()).hexdigest() == original['program_sha256'],
                'original navigation program bytes differ')
        record = dict(accepted=False, diagnostic_only=True, program_source_sha=source,
                      program_sha256=original['program_sha256'], original_run=run_id, original_attempt=attempt,
                      test_source_sha=os.environ['GITHUB_SHA'], test_run=os.environ['GITHUB_RUN_ID'],
                      original_fixture_sha256=fixture_hashes,
                      artifact={k: names[0][k] for k in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
        (out / 'input.json').write_text(json.dumps(record, indent=2) + '\n')
        with open(os.environ['GITHUB_ENV'], 'a') as env:
            env.write('NAV_PROBE_PAYLOAD=' + str(payload.resolve()) + '\n')
            env.write('GTK_NAVIGATION_PROGRAM_SOURCE=' + source + '\n')
        print(json.dumps(record), flush=True)
    finally:
        bundle.close()


if __name__ == '__main__':
    main()
