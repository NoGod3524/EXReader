#!/usr/bin/env python3
"""Records and checks the built Android artifacts: the AAR declares no component, the Release probe APK exists,
and the native archive never references thread creation or file deletion."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NDK = '27.0.12077973'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    problems, files = [], {}
    outputs = ROOT / 'extras/android-import-entry/android/importentry/build/outputs/aar'
    for variant in ('debug', 'release'):
        aar = outputs / ('importentry-%s.aar' % variant)
        if not aar.is_file():
            problems.append('missing ' + aar.name)
            continue
        with zipfile.ZipFile(aar) as z:
            names = z.namelist()
            manifest = z.read('AndroidManifest.xml')
            # Binary manifests do not occur in AARs; a plain-text scan is exact.
            if re.search(rb'<(uses-permission|provider|activity|service|receiver)\b', manifest):
                problems.append(aar.name + ' manifest declares a component')
            if any(n.endswith('.so') for n in names):
                problems.append(aar.name + ' bundles a native library')
            if not any(n.startswith('classes') and n.endswith('.jar') for n in names):
                problems.append(aar.name + ' has no classes')
        files[aar.name] = {'bytes': aar.stat().st_size, 'sha256': sha(aar)}
    apk_root = ROOT / 'tests/reader_android_import_entry/android'
    for rel in ('app/build/outputs/apk/debug/app-debug.apk', 'app/build/outputs/apk/release/app-release-unsigned.apk',
                'source/build/outputs/apk/debug/source-debug.apk'):
        apk = apk_root / rel
        if not apk.is_file():
            problems.append('missing ' + rel)
        else:
            files[apk.name] = {'bytes': apk.stat().st_size, 'sha256': sha(apk)}
    home = os.environ.get('ANDROID_HOME', '')
    nm = Path(home) / 'ndk' / NDK / 'toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-nm'
    symbols = {}
    for config, prefix in (('Release', args.stage), ('Debug', args.work / 'debug-prefix')):
        archive = prefix / 'lib/libexr_android_import_entry.a'
        out = subprocess.check_output([str(nm), '-u', str(archive)], text=True)
        undefined = sorted({line.split()[-1] for line in out.splitlines() if line.strip().startswith('U ')})
        symbols[config] = undefined
        bad = [s for s in undefined if re.fullmatch(r'pthread_create|fork|unlink|remove|rename|rmdir|execv.*|execl.*|system', s)]
        if bad:
            problems.append('%s native archive references %s' % (config, bad))
        files['libexr_android_import_entry.a-' + config] = {'bytes': archive.stat().st_size, 'sha256': sha(archive)}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'packages.json').write_text(json.dumps({'files': files, 'undefined_symbols': symbols, 'problems': problems}, indent=2))
    print(json.dumps({'problems': problems}, indent=2))
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
