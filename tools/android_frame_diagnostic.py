#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Inspect immutable Android failure evidence in Actions; never execute the app."""
import hashlib
import io
import json
import os
from collections import Counter
from pathlib import Path, PurePosixPath
import re
import xml.etree.ElementTree as ET
import zipfile

from PIL import Image, ImageChops
from check_parallel_integration import download_artifact_zip, fetch, pages, require

RUN = 39991607049
HEAD = 'de9871aca6a54f70c6c1d147ba12f308cedf1004'
ARTIFACT = 12517859271
BYTES = 157060818
DIGEST = 'a68d1d71afa48a2d05bcc9c44732b619af6139db4bac39fa08c6051922046ec0'
CASES = ('process_restart_reflow', 'pdf_process_restart')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def pixel_difference(left, right):
    result = {'same_png_size': left.size == right.size}
    if left.size != right.size:
        return result
    left, right = left.convert('RGBA'), right.convert('RGBA')
    channels = ImageChops.difference(left, right).split()
    mask = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
    mask = ImageChops.lighter(mask, channels[3])
    mask = mask.point(lambda value: 255 if value else 0)
    pixels = left.width * left.height
    absolute = sum(sum(index * count for index, count in enumerate(channel.histogram())) for channel in channels[:3])
    result.update(diff_bbox=mask.getbbox(), changed_pixels=pixels - mask.histogram()[0],
                  total_pixels=pixels, absolute_rgb_difference=absolute,
                  mean_absolute_channel_difference=absolute / (pixels * 3),
                  max_channel_difference=max(max(channel.getextrema()) for channel in channels))
    signed = {}
    for name, before, after in zip(('R', 'G', 'B', 'A'), left.split(), right.split()):
        histogram = Counter(b - a for a, b in zip(before.tobytes(), after.tobytes()))
        nonzero = [(delta, count) for delta, count in histogram.items() if delta]
        signed[name] = {'changed_pixels': sum(count for delta, count in nonzero),
                        'max_absolute_delta': max((abs(delta) for delta, count in nonzero), default=0),
                        'nonzero_top20': [{'delta': delta, 'count': count}
                                          for delta, count in sorted(nonzero, key=lambda row: (-row[1], row[0]))[:20]]}
    result['signed_rgba_after_minus_before'] = signed
    return result


def inspect_case(archive, case, output):
    names = archive.namelist()
    matches = [name for name in names if name.endswith('-' + case + '.json') and '/cases/' in name]
    require(len(matches) == 1, 'Missing/duplicate case: ' + case)
    case_name = matches[0]
    raw = archive.read(case_name)
    require(len(raw) <= 8 * 1024 * 1024, 'Oversized case JSON')
    entry = json.loads(raw)
    require(entry['id'] == case and entry['status'] == 'fail', 'Wrong retained failed case')
    write_json(output / (case + '-original.json'), entry)
    root = PurePosixPath(case_name).parent.parent
    summary = {'case_file': case_name, 'status': entry['status'], 'detail': entry.get('detail'),
               'frame_observations': entry['frame_observations'], 'pngs': [], 'xml': []}
    selected = {}
    for observation in entry['frame_observations']:
        role = observation['role']
        if role not in ('reference', 'restored'):
            continue
        require(observation['samples'], 'Frame samples missing')
        for index, sample in enumerate(observation['samples']):
            relative = PurePosixPath(sample['png'])
            require(not relative.is_absolute() and '..' not in relative.parts, 'Unsafe PNG path')
            name = str(root / relative)
            require(names.count(name) == 1, 'PNG missing/duplicate: ' + name)
            png = archive.read(name)
            require(len(png) == sample['png_bytes'] and sha(png) == sample['png_sha256'], 'Retained PNG digest changed')
            with Image.open(io.BytesIO(png)) as image:
                rgb = image.convert('RGBA')
            summary['pngs'].append({'role': role, 'sample': index, 'path': name, 'bytes': len(png),
                                    'sha256': sha(png), 'mode': rgb.mode, 'size': list(rgb.size)})
            selected[role] = (sample, rgb)
            (output / (case + '-' + role + '-' + str(index) + '.png')).write_bytes(png)
    require(set(selected) == {'reference', 'restored'}, 'Reference/restored pair missing')
    left, right = (selected[role] for role in ('reference', 'restored'))
    comparison = pixel_difference(left[1], right[1])
    fields = ('book', 'index', 'part', 'path', 'start', 'end', 'anchor_sha256', 'font', 'zoom',
              'render_scale', 'bitmap_width', 'bitmap_height', 'viewport_width', 'viewport_height',
              'drawn_width', 'drawn_height', 'fit', 'offset_x', 'offset_y', 'selection_mode',
              'selection_start', 'selection_end', 'bitmap_identity')
    comparison['reference'] = {key: left[0]['observation'].get(key) for key in fields}
    comparison['restored'] = {key: right[0]['observation'].get(key) for key in fields}
    comparison['different_observation_fields'] = [key for key in fields if comparison['reference'][key] != comparison['restored'][key]]
    comparison['reference_bounds'] = left[0]['bounds']
    comparison['restored_bounds'] = right[0]['bounds']
    comparison['reference_observation'] = left[0]['observation']
    comparison['restored_observation'] = right[0]['observation']
    if entry.get('screenshot'):
        relative = PurePosixPath(entry['screenshot'])
        require(not relative.is_absolute() and '..' not in relative.parts, 'Unsafe failure screenshot path')
        name = str(root / relative)
        require(names.count(name) == 1, 'Failure screenshot missing/duplicate')
        png = archive.read(name)
        require(len(png) == entry['screenshot_bytes'] and sha(png) == entry['screenshot_sha256'], 'Failure screenshot digest changed')
        with Image.open(io.BytesIO(png)) as image:
            full = image.convert('RGBA')
        failure = {'path': name, 'size': list(full.size), 'sha256': sha(png), 'crops': {}}
        for role, (sample, image) in selected.items():
            bounds = sample['bounds']
            require(0 <= bounds[0] < bounds[2] <= full.width and 0 <= bounds[1] < bounds[3] <= full.height,
                    'Failure screenshot crop outside bounds')
            crop = full.crop(bounds)
            crop.save(output / (case + '-failure-crop-' + role + '.png'))
            failure['crops'][role] = {'bounds': bounds, 'comparison_to_sample': pixel_difference(image, crop)}
        summary['failure_screenshot'] = failure
    for name in names:
        if case not in name or not name.endswith('.xml'):
            continue
        xml = archive.read(name)
        require(len(xml) <= 4 * 1024 * 1024, 'Oversized UI XML')
        tree = ET.fromstring(xml)
        keep = ('reader_view', 'book_title', 'page_label', 'font_label', 'zoom_label', 'reader_status', 'notes_button')
        nodes = [dict(node.attrib) for node in tree.iter() if any(node.attrib.get('resource-id', '').endswith('/' + key) for key in keep)]
        summary['xml'].append({'path': name, 'sha256': sha(xml), 'nodes': nodes})
        (output / (case + '-' + PurePosixPath(name).name)).write_bytes(xml)
    pids = {str(selected[role][0]['observation']['pid']) for role in selected}
    log_names = [name for name in names if name.endswith('walkthrough-logcat.txt')]
    require(len(log_names) == 1, 'Walkthrough logcat missing/duplicate')
    log = archive.read(log_names[0]).decode('utf-8', errors='replace')
    relevant = [line for line in log.splitlines() if 'EXRHost' in line and any(re.search(r'\b' + pid + r'\b', line) for pid in pids)]
    summary['host_log'] = {'path': log_names[0], 'pids': sorted(pids), 'matching_lines': len(relevant), 'last_lines': relevant[-160:]}
    summary['comparison'] = comparison
    write_json(output / (case + '-diagnostic.json'), summary)
    print(json.dumps({'case': case, 'comparison': comparison,
                      'sample_counts': {role: sum(len(o['samples']) for o in entry['frame_observations'] if o['role'] == role) for role in selected},
                      'failure_screenshot': summary.get('failure_screenshot'),
                      'xml': summary['xml'], 'host_log': summary['host_log']}, ensure_ascii=False), flush=True)
    return summary


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('GITHUB_REPOSITORY') == 'NoGod3524/EXReader', 'Cloud repository required')
    output = Path('build/android-frame-diagnostic')
    output.mkdir(parents=True, exist_ok=False)
    report = {'diagnostic_only': True, 'accepted': False, 'app_executed': False,
              'diagnostic_source': os.environ['GITHUB_SHA'], 'diagnostic_run': os.environ['GITHUB_RUN_ID'],
              'inspected_run': RUN, 'inspected_attempt': 1, 'inspected_head': HEAD,
              'artifact_id': ARTIFACT, 'artifact_bytes': BYTES, 'artifact_digest': 'sha256:' + DIGEST,
              'diagnostic_completed': False, 'problems': []}
    try:
        run = fetch(f'actions/runs/{RUN}')
        require(run['id'] == RUN and run['run_attempt'] == 1 and run['head_sha'] == HEAD and
                run['event'] == 'workflow_dispatch' and run['path'] == '.github/workflows/wp13-android.yml' and
                run['status'] == 'completed' and run['conclusion'] == 'failure', 'Failed run identity refused')
        artifacts = [row for row in pages(f'actions/runs/{RUN}/artifacts', 'artifacts')
                     if row['id'] == ARTIFACT or row['name'] == 'EXReader-WP13-Android']
        require(len(artifacts) == 1, 'Original artifact missing/duplicate')
        item = artifacts[0]
        require(item['id'] == ARTIFACT and item['name'] == 'EXReader-WP13-Android' and
                item['size_in_bytes'] == BYTES and item['digest'] == 'sha256:' + DIGEST and not item['expired'] and
                item['workflow_run']['id'] == RUN and item['workflow_run']['head_sha'] == HEAD, 'Original artifact metadata refused')
        report['artifact_metadata'] = item
        archive_path = output / 'original-12517859271.zip'
        with archive_path.open('wb') as stream:
            download_artifact_zip(ARTIFACT, stream)
        require(archive_path.stat().st_size == BYTES and file_sha(archive_path) == DIGEST,
                'Original ZIP bytes/digest refused')
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            require(len(names) == len(set(names)), 'Duplicate original ZIP members')
            report['related_paths'] = [name for name in names if any(case in name for case in CASES) or name.endswith(('build.json', 'execution.json', 'walkthrough-logcat.txt', 'validation.json'))][:180]
            report['xml_paths'] = [name for name in names if name.lower().endswith('.xml')][:180]
            print(json.dumps({'diagnostic_only': True, 'accepted': False, 'artifact_verified': True,
                              'related_paths': report['related_paths'], 'xml_paths': report['xml_paths']}), flush=True)
            report['cases'] = {case: inspect_case(archive, case, output) for case in CASES}
        report['diagnostic_completed'] = True
    except Exception as error:
        report['problems'].append(type(error).__name__ + ': ' + str(error))
    write_json(output / 'diagnostic.json', report)
    print(json.dumps({key: value for key, value in report.items() if key not in ('cases', 'artifact_metadata', 'related_paths')}), flush=True)
    return 0 if report['diagnostic_completed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
