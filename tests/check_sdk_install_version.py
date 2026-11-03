#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify package, generated header, pkg-config and linked runtime identities."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from sdk_version import ROOT, installed_version, source_version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--build-dir', type=Path, required=True)
    args = parser.parse_args()
    sdk, build = args.sdk.resolve(), args.build_dir.resolve()
    expected = source_version()
    subprocess.run(['cmake', '-S', str(ROOT / 'tests/sdk_version_identity'), '-B', str(build),
                    '-G', 'Ninja', '-DCMAKE_PREFIX_PATH=' + str(sdk),
                    '-DEXPECTED_VERSION=' + expected], check=True)
    subprocess.run(['cmake', '--build', str(build)], check=True)
    env = dict(os.environ)
    env['PATH'] = str(sdk / 'bin') + os.pathsep + env.get('PATH', '')
    env['PKG_CONFIG_PATH'] = str(sdk / 'lib/pkgconfig')
    executable = build / ('version-probe.exe' if os.name == 'nt' else 'version-probe')
    runtime = subprocess.check_output([str(executable)], env=env, text=True).strip().splitlines()
    package = (build / 'cmake-version.txt').read_text(encoding='utf-8').strip()
    header = installed_version(sdk)
    pkgconf = shutil.which('pkgconf') or shutil.which('pkg-config')
    if not pkgconf:
        raise RuntimeError('pkgconf or pkg-config is required for the installed channel check')
    pkg = subprocess.check_output([pkgconf, '--modversion', 'exreader'], env=env, text=True).strip()
    if not package == header == pkg == expected:
        raise AssertionError((package, header, pkg, expected))
    print('SDK_CHANNELS_JSON ' + json.dumps(dict(sdk=expected, cmake_package_version=package,
          generated_header_version=header, pkgconfig_version=pkg, runtime=runtime)))


if __name__ == '__main__':
    main()
