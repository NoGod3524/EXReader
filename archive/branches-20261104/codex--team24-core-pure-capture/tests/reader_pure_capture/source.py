"""Actions-only source receipt for the independent pure raw capture candidate."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASE = 'c05a4c2c1782872c943b4179c55529bb343b3fbe'
CANDIDATE = 'a911cd0e8405a362dae1bb489190de02c4c81d51'
SDK = '9d3a3f8bfa06c099ebba0d9e1ba613d276c3af09'
FILES = {
    'apps/reader/reading-state/CMakeLists.txt': '2b513deeb2681eb2e0c674fe447ddfee83cb3994',
    'apps/reader/reading-state/include/reader_reading_state_capture_raw_candidate.h': '0cce3515dbcbed3c6b49356e1d6dc137b5a31aaa',
    'apps/reader/reading-state/src/reading_state.cpp': '25de29dd59828371d7c35dc8a6295b9d74bc738d',
}
OLD_HEADER = 'apps/reader/reading-state/include/reader_reading_state.h'
SDK_PATHS = ('src', 'include', 'cmake', 'CMakeLists.txt', 'CMakePresets.json',
             'bindings', 'tools/layers.json', 'tests/fixtures')
REVIEW_FILES = {'.github/workflows/reader-pure-capture.yml',
                'docs/reader-team24-core/PURE-CAPTURE-IMPLEMENTATION.md'}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode('utf-8').strip()


def entries(ref):
    result = {}
    for entry in subprocess.check_output(['git', 'ls-tree', '-rz', '--full-tree', ref], cwd=ROOT).split(b'\0'):
        if entry:
            metadata, path = entry.split(b'\t', 1)
            result[path.decode('utf-8')] = tuple(metadata.decode('ascii').split())
    return result


def receipt():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    source = os.environ['GITHUB_SHA']
    candidate = os.environ['PURE_CAPTURE_SOURCE']
    assert re.fullmatch('[0-9a-f]{40}', source) and candidate == CANDIDATE, 'fixed full source pins required'
    assert git('rev-parse', 'HEAD') == source, 'event source differs from checked-out source'
    assert git('rev-list', '--parents', '-n', '1', candidate).split() == [candidate, BASE], 'candidate parent differs'
    subprocess.run(['git', 'merge-base', '--is-ancestor', candidate, source], cwd=ROOT, check=True)
    baseline, adopted, actual = entries(BASE), entries(candidate), entries(source)
    changed = {path for path in set(baseline) | set(adopted) if baseline.get(path) != adopted.get(path)}
    assert changed == set(FILES), ('candidate must change exactly three production files', sorted(changed))
    for path, blob in FILES.items():
        assert adopted.get(path) == actual.get(path) == ('100644', 'blob', blob), ('candidate blob/mode mismatch', path)
    assert baseline[OLD_HEADER] == adopted[OLD_HEADER] == actual[OLD_HEADER], 'old public header bytes changed'
    # The two existing files are additive: no old API body/build statement is removed.
    for path in FILES:
        if path in baseline:
            added, removed, _ = git('diff', '--numstat', BASE, candidate, '--', path).split('\t')
            assert added.isdecimal() and removed == '0', ('old source was replaced', path)
    review_paths = []
    for path in sorted(set(adopted) | set(actual)):
        if adopted.get(path) != actual.get(path):
            assert path in REVIEW_FILES or path.startswith('tests/reader_pure_capture/'), ('outside review scope', path)
            assert actual.get(path, ())[:2] == ('100644', 'blob'), ('review path must be a regular source file', path)
            review_paths.append(path)
    sdk = {path: git('rev-parse', source + ':' + path) for path in SDK_PATHS}
    for path, identity in sdk.items():
        assert identity == git('rev-parse', SDK + ':' + path), ('frozen SDK differs', path)
    guards = {path: value[2] for path, value in baseline.items()
              if 'guard' in Path(path).name.lower() and path.startswith(('apps/', 'tests/', 'tools/'))}
    assert all(actual.get(path) == baseline[path] for path in guards), 'an existing guard source changed'
    return dict(source_sha=source, run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                candidate_source=candidate, base_anchor=BASE, sdk_source=SDK,
                candidate_blobs=FILES, base_blobs={path: baseline.get(path) for path in FILES},
                old_public_header_blob=actual[OLD_HEADER][2], sdk_objects=sdk,
                unchanged_guard_blobs=guards, review_paths=review_paths,
                production_delta=sorted(changed), source_accepted=True,
                runtime_accepted=False, option_off_behavior_accepted=False,
                package_0_1_behavior_accepted=False, package_0_2_behavior_accepted=False,
                no_write_accepted=False, complete_product=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'build/reader-pure-capture/source.json')
    options = parser.parse_args()
    value = receipt()
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value[key] for key in ('source_sha', 'candidate_source', 'base_anchor',
        'source_accepted', 'runtime_accepted', 'production_delta')}))


if __name__ == '__main__':
    main()
