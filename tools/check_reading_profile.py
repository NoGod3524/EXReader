#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify installed reading profile composition and record actual installed sizes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            result.update(block)
    return result.hexdigest()


def inspect(profile, build, sdk, executable):
    values = {}
    for line in (build / 'CMakeCache.txt').read_text(encoding='utf-8').splitlines():
        if line and not line.startswith(('#', '//')) and '=' in line and ':' in line:
            key, value = line.split('=', 1)
            values[key.split(':', 1)[0]] = value
    on = ['EXR_ENABLE_PDF', 'EXR_ENABLE_PDF_CRYPTO', 'EXR_ENABLE_ICC',
          'EXR_ENABLE_IMAGE_WEBP', 'EXR_ENABLE_IMAGE_TIFF', 'EXR_ENABLE_IMAGE_AVIF']
    off = ['EXR_ENABLE_AUDIO', 'EXR_ENABLE_MP3', 'EXR_ENABLE_AAC',
           'EXR_ENABLE_TEXT_INDEX', 'EXR_BUILD_TEXT_INDEX', 'EXR_ENABLE_PDF_EDIT',
           'EXR_BUILD_SHARED_COMPAT', 'EXR_BUILD_JNI', 'EXR_BUILD_TOOLS', 'EXR_BUILD_TESTS']
    expected = dict.fromkeys(on, 'ON') | dict.fromkeys(off, 'OFF')
    expected['EXR_ENABLE_LIBRARY'] = 'ON' if profile == 'reading-library' else 'OFF'
    problems = [f'{key}: expected {value}, observed {values.get(key)}'
                for key, value in expected.items() if values.get(key) != value]
    targets = (sdk / 'lib/cmake/EXReader/EXReaderTargets.cmake').read_text(encoding='utf-8')
    exported = set(re.findall(r'add_library\(EXReader::(\w+)\s', targets))
    if not {'exr_core', 'exr_pdf'} <= exported:
        problems.append('Required core/PDF imported targets missing')
    if exported & {'exr_audio', 'exr_pdf_edit', 'exr_textindex'}:
        problems.append('Optional components leaked into exported package')
    if ('exr_library' in exported) != (profile == 'reading-library'):
        problems.append('Bookshelf component does not match requested profile')
    runtime = subprocess.run(['ldd', str(executable.resolve())], capture_output=True, text=True)
    if runtime.returncode:
        problems.append('Cannot inspect linked consumer runtime dependencies')
    forbidden = ['webview', 'webkit', 'chromium', 'electron', 'faad', 'minimp3']
    if profile == 'reading-core':
        forbidden.append('sqlite')
    if any(word in runtime.stdout.lower() for word in forbidden) or 'not found' in runtime.stdout:
        problems.append('Forbidden or unresolved runtime dependency')
    files = [{'path': path.relative_to(sdk).as_posix(), 'bytes': path.stat().st_size,
              'sha256': digest(path)} for path in sorted(sdk.rglob('*')) if path.is_file()]
    libraries = [item for item in files if item['path'].startswith('lib/') and
                 re.search(r'\.(?:a|lib|so(?:\..*)?|dylib)$', item['path'])]
    if not libraries:
        problems.append('Installed library archives are missing')
    return {'schema': 1, 'profile': profile, 'accepted': not problems, 'problems': problems,
            'composition_scope': 'Linux installed static SDK and linked document consumer',
            'performance_budget_accepted': False, 'expected_cache_variables': expected,
            'cache_variables': {key: values.get(key) for key in expected},
            'exported_targets': sorted(exported), 'runtime_dependencies': runtime.stdout,
            'runtime_dependency_stderr': runtime.stderr,
            'installed_total_bytes': sum(item['bytes'] for item in files),
            'installed_library_bytes': sum(item['bytes'] for item in libraries),
            'files': files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', choices=['reading-core', 'reading-library'])
    parser.add_argument('build', type=Path)
    parser.add_argument('sdk', type=Path)
    parser.add_argument('executable', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    report = inspect(args.profile, args.build, args.sdk, args.executable)
    report['source_sha'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    report['consumer_sha256'] = digest(args.executable)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps({key: report[key] for key in
                      ['profile', 'accepted', 'problems', 'installed_library_bytes']}))
    return 0 if report['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
