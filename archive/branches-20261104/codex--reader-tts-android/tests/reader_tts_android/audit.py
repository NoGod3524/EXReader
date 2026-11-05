#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only package audit for the Android TTS backend and its probe apps."""
import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def describe(path, entries=False):
    record = {'path': str(path).replace('\\', '/'), 'bytes': path.stat().st_size, 'sha256': sha256(path)}
    if entries and path.suffix in ('.aar', '.apk'):
        with zipfile.ZipFile(path) as archive:
            names = sorted(archive.namelist())
        record['entries'] = len(names)
        record['native_libraries'] = [name for name in names if name.startswith('lib/')]
        record['classes_archive'] = [name for name in names if name.endswith('classes.jar')]
        record['dex_files'] = [name for name in names if name.endswith('.dex')]
    return record


def first(*patterns, root='.'):
    for pattern in patterns:
        matches = sorted(Path(root).glob(pattern))
        if matches:
            return matches[0]
    raise SystemExit('missing build product: ' + ' | '.join(patterns))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--workspace', default='.')
    arguments = parser.parse_args()
    workspace = Path(arguments.workspace).resolve()
    output = Path(arguments.output)
    output.mkdir(parents=True, exist_ok=True)

    aar = first('extras/reader-tts-android/android/tts/build/outputs/aar/*.aar', root=workspace)
    debug_apk = first('tests/reader_tts_android/android/probe/build/outputs/apk/debug/*.apk', root=workspace)
    release_apk = first('tests/reader_tts_android/android/probe/build/outputs/apk/release/*.apk', root=workspace)
    test_apk = first('tests/reader_tts_android/android/probe/build/outputs/apk/androidTest/debug/*.apk',
                     'tests/reader_tts_android/android/probe/build/outputs/apk/androidTest/*.apk', root=workspace)
    baseline_apk = first('tests/reader_tts_android/android/baseline/build/outputs/apk/release/*.apk', root=workspace)
    archive = first('build/reader-tts-android/stage-release/lib/*/libreader_tts.a',
                    'build/reader-tts-android/stage-release/lib/libreader_tts.a', root=workspace)
    archive_debug = first('build/reader-tts-android/stage-debug/lib/*/libreader_tts.a',
                          'build/reader-tts-android/stage-debug/lib/libreader_tts.a', root=workspace)

    packages = {
        'aar': describe(aar, entries=True),
        'probe_debug_apk': describe(debug_apk, entries=True),
        'probe_release_apk': describe(release_apk, entries=True),
        'probe_android_test_apk': describe(test_apk, entries=True),
        'baseline_apk': describe(baseline_apk, entries=True),
        'static_archive_release': describe(archive),
        'static_archive_debug': describe(archive_debug),
    }
    with zipfile.ZipFile(debug_apk) as probe_archive, zipfile.ZipFile(baseline_apk) as plain_archive:
        probe_entries = set(probe_archive.namelist())
        plain_entries = set(plain_archive.namelist())
        native = [name for name in sorted(probe_entries) if name.startswith('lib/') and name.endswith('.so')]
        packages['probe_native_libraries'] = [
            {'entry': name, 'bytes': probe_archive.getinfo(name).file_size,
             'sha256': hashlib.sha256(probe_archive.read(name)).hexdigest()} for name in native]
        packages['baseline_native_libraries'] = [
            name for name in sorted(plain_entries) if name.startswith('lib/') and name.endswith('.so')]
    packages['probe_apk_bytes_delta'] = packages['probe_debug_apk']['bytes'] - packages['baseline_apk']['bytes']
    packages['delta_scope'] = ('minimal app carrying the support AAR versus the same app with the C consumer, '
                               'the backend static archive and the JNI bridge')
    packages['runtime_dependencies'] = []
    packages['jar_dependencies'] = 'none: the Android library declares no Maven dependencies'
    if not packages['probe_native_libraries']:
        raise SystemExit('the probe APK ships no native library')
    if packages['baseline_native_libraries']:
        raise SystemExit('the baseline APK unexpectedly ships native libraries')
    (output / 'packages.json').write_text(json.dumps(packages, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'packages': list(packages), 'probe_libs': len(packages['probe_native_libraries'])}))


if __name__ == '__main__':
    sys.exit(main())
