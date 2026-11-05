#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build the native GTK reference host against an installed SDK, on Linux only."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
from host_font import fetch

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--sdk-version', choices=('3.40.0', '3.41.0'), default='3.40.0',
                        help='Exact SDK version; the frozen default remains 3.40.0')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--binary', type=Path, help='Package this already-built native consumer instead of rebuilding the reference host')
    args = parser.parse_args()
    if platform.system() != 'Linux':
        parser.error('Build and run this consumer on Linux')
    output = args.output.resolve()
    if output.exists():
        parser.error('Choose a new output directory')
    output.mkdir(parents=True)
    build, payload = output/'consumer', output/'EXReader-Linux'
    if args.binary is not None:
        (payload/'bin').mkdir(parents=True)
        shutil.copy2(args.binary.resolve(strict=True), payload/'bin/exreader-linux')
    else:
        subprocess.run(['cmake', '-S', str(ROOT/'examples/linux'), '-B', str(build),
                        '-DEXR_SDK='+str(args.sdk.resolve()), '-DEXR_SDK_VERSION='+args.sdk_version,
                        '-DCMAKE_BUILD_TYPE=Release'], check=True)
        subprocess.run(['cmake', '--build', str(build), '--parallel', '4'], check=True)
        subprocess.run(['cmake', '--install', str(build), '--prefix', str(payload)], check=True)
    identity = subprocess.check_output([str(payload/'bin/exreader-linux'), '--version'], text=True).strip()
    if identity != args.sdk_version + ' 1':
        raise RuntimeError('Installed host reports an unexpected SDK or ABI')
    dependencies = subprocess.check_output(['ldd', str(payload/'bin/exreader-linux')], text=True)
    (output/'runtime-dependencies.txt').write_text(dependencies)
    modules = [line.split()[0].rsplit('/', 1)[-1].lower() for line in dependencies.splitlines() if line.strip()]
    if 'not found' in dependencies or any(marker in name for name in modules for marker in ('webkit', 'webview', 'libcef', 'electron')):
        raise RuntimeError('Native host has an unavailable or browser runtime dependency')
    assets = fetch(ROOT/'build/linux-font-cache')
    for name in ('Reader.otf', 'OFL.txt'):
        shutil.copyfile(assets/name, payload/name)
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
        shutil.copyfile(ROOT/name, payload/name)
    shutil.copytree(args.sdk/'share/exreader/licenses', payload/'licenses')
    source = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    manifest = {'schema': 1, 'source_sha': source, 'sdk_version': identity.split()[0], 'abi': int(identity.split()[1]),
                'gtk_version': subprocess.check_output(['pkg-config', '--modversion', 'gtk+-3.0'], text=True).strip(),
                'files': {str(p.relative_to(payload)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted(payload.rglob('*')) if p.is_file()}}
    (output/'build.json').write_text(json.dumps(manifest, indent=2)+'\n')
    shutil.make_archive(str(output/'EXReader-Linux'), 'gztar', root_dir=payload)


if __name__ == '__main__':
    main()
