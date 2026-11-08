#!/usr/bin/env python3
"""Package the installed native SDK and existing Java JNI binding as an AAR."""
import argparse
import io
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from check_exports import DEFAULT_CONTRACT, ROOT, inspect


def archive(entries):
    result = io.BytesIO()
    with zipfile.ZipFile(result, 'w', zipfile.ZIP_DEFLATED) as output:
        for name, content in sorted(entries.items()):
            info = zipfile.ZipInfo(name, (2026, 11, 8, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            output.writestr(info, content)
    return result.getvalue()


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', required=True, type=Path)
    parser.add_argument('--abi', required=True, choices=['arm64-v8a', 'x86_64'])
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    expected = set(json.loads(DEFAULT_CONTRACT.read_text())['symbols'])
    machine = {'arm64-v8a': '0xb7', 'x86_64': '0x3e'}[args.abi]
    entries = {}
    for name in ('libexreader.so', 'libexreader_jni.so'):
        path = args.sdk / 'lib' / name
        report = inspect(path, expected)
        if len(report['slices']) != 1 or report['slices'][0]['format'] != 'ELF':
            raise ValueError('expected one ELF slice')
        part = report['slices'][0]
        if part['machine'] != machine:
            raise ValueError(f'{name}: wrong Android ABI')
        if name == 'libexreader.so' and part['missing']:
            raise ValueError('incomplete core ABI: ' + ', '.join(part['missing']))
        entries[f'jni/{args.abi}/{name}'] = path.read_bytes()
    with tempfile.TemporaryDirectory() as temporary:
        classes = Path(temporary)
        subprocess.run(['javac', '--release', '8', '-d', str(classes),
                        str(ROOT/'bindings/jni/EXReader.java'),
                        str(ROOT/'bindings/jni/EXReaderException.java')], check=True)
        entries['classes.jar'] = archive({p.relative_to(classes).as_posix(): p.read_bytes()
                                          for p in classes.rglob('*.class')})
    entries['AndroidManifest.xml'] = (b'<manifest xmlns:android="http://schemas.android.com/apk/res/android" '
                                       b'package="org.exreader.sdk"><uses-sdk android:minSdkVersion="24" /></manifest>')
    # Include the installed license tree, including third-party notices.
    for path in (args.sdk/'share').rglob('*'):
        if path.is_file():
            entries['assets/exreader/' + path.relative_to(args.sdk/'share').as_posix()] = path.read_bytes()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(archive(entries))
    print(f'{args.output}: {args.output.stat().st_size} bytes; JNI + Java; {args.abi}; minSdk=24')


if __name__ == '__main__':
    main()
