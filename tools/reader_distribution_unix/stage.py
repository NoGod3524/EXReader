#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build the J24 Unix distribution candidate tree from an installed reading SDK.

The candidate keeps the installed layout, adds one pkg-config unit whose prefix is
relative to ${pcfiledir}, plans removal of byte-identical archive materials and
records every identity needed to re-derive the result from uploaded bytes only.
Nothing here selects a build directory through a CMake preset: the workflow passes
the reading-core switches as explicit external arguments.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contract

PROFILE = 'reading-core'
REQUIRED = ('include/exr/base.h', 'include/exr/core.h', 'include/exreader.h',
            'lib/cmake/EXReader/EXReaderConfig.cmake',
            'lib/cmake/EXReader/EXReaderConfigVersion.cmake',
            'lib/cmake/EXReader/EXReaderDependencies.cmake',
            'lib/cmake/EXReader/EXReaderTargets.cmake',
            'docs/SUPPORT_MATRIX.md', 'docs/WP12A-FORMATS.md',
            'share/exreader/licenses', 'LICENSE', 'THIRD_PARTY_NOTICES.md')
DESCRIPTION = 'EXReader native multi-format and PDF reading SDK (reading-core profile)'


def version_abi(header):
    text = header.read_text(encoding='utf-8')
    sdk = re.search(r'^#define EXR_VERSION "([0-9]+\.[0-9]+\.[0-9]+)"$', text, re.M)
    abi = re.search(r'^#define EXR_ABI_VERSION ([0-9]+)u?$', text, re.M)
    contract.need(sdk and abi, 'installed SDK version/ABI declaration missing')
    return sdk.group(1), int(abi.group(1))


def build(profile, install, output, platform, runner_os, arch, licenses):
    contract.need(profile == PROFILE, 'J24 stages the reading-core distribution only')
    install, output = Path(install).resolve(strict=True), Path(output)
    contract.need(not output.exists(), 'candidate output already exists: ' + str(output))
    for relative in REQUIRED:
        contract.need((install / relative).exists(), 'installed SDK is missing ' + relative)
    sdk_version, abi = version_abi(install / 'include/exr/base.h')
    contract.need(sdk_version == '3.40.0' and abi == 1,
                  'unexpected SDK identity %s/ABI %d' % (sdk_version, abi))
    exported = (install / 'lib/cmake/EXReader/EXReaderTargets.cmake').read_text(encoding='utf-8')
    dependencies = (install / 'lib/cmake/EXReader/EXReaderDependencies.cmake').read_text(encoding='utf-8')
    components = contract.link_order(exported)
    vendor = contract.vendor_archives(dependencies)
    system = contract.system_libraries(dependencies)
    for name in components:
        contract.need((install / 'lib' / name).is_file(), 'missing component archive ' + name)
    for name in vendor:
        contract.need((install / 'lib/exreader' / name).is_file(), 'missing private archive ' + name)
    contract.need(not any(name.startswith('libexr_library') for name in components),
                  'reading-core candidate unexpectedly exports the SQLite bookshelf')
    licence_report = contract.decode_json(licenses)
    contract.need(licence_report.get('release_ready') is True and licence_report.get('failures') == []
                  and licence_report.get('mandatory_missing') == [] and licence_report.get('pending') == [],
                  'release licence materials are not complete on this installed stage')
    contract.need(licence_report.get('profile') == PROFILE, 'licence report was recorded for another profile')

    output.mkdir(parents=True)
    prefix = output / 'prefix'
    shutil.copytree(install, prefix, symlinks=False)
    pc_text = contract.render_pc(sdk_version, DESCRIPTION, components, vendor, system)
    pc_path = prefix / 'lib/pkgconfig/exreader.pc'
    pc_path.parent.mkdir(parents=True, exist_ok=True)
    pc_path.write_text(pc_text, encoding='utf-8')
    pc_fields, pc_problems = contract.pc_contract(pc_text, sdk_version, components, vendor, system)
    contract.need(not pc_problems, 'generated pkg-config unit is invalid: ' + '; '.join(pc_problems))

    records = contract.walk(prefix)
    plan = contract.dedupe_plan(records)
    duplicate_bytes = sum(item['bytes'] for item in plan)
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    contract.need(source == os.environ.get('GITHUB_SHA'), 'checkout and workflow source differ')
    ci = {name: os.environ.get(name, '') for name in
          ('GITHUB_REPOSITORY', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_JOB',
           'RUNNER_OS', 'RUNNER_ARCH', 'ImageOS', 'ImageVersion')}
    stage = {
        'schema': 1,
        'source_sha': source,
        'ci': ci,
        'platform': platform,
        'runner_os': runner_os,
        'architecture': arch,
        'profile': PROFILE,
        'prefixes': {'install': str(install), 'staged': str(prefix)},
        'sdk_version': sdk_version,
        'abi': abi,
        'description': DESCRIPTION,
        'pkgconfig': {'path': 'lib/pkgconfig/exreader.pc', 'bytes': len(pc_text.encode('utf-8')),
                      'sha256': contract.digest(pc_path), 'text': pc_text,
                      'fields': pc_fields},
        'link_order': components,
        'private_archives': vendor,
        'system_libraries': system,
        'files': records,
        'totals': {'files': len(records), 'bytes': sum(record['bytes'] for record in records),
                   'executables': sum(1 for record in records if record['executable']),
                   'material_files': sum(1 for record in records if contract.is_material(record['path']))},
        'dedupe_plan': plan,
        'dedupe_summary': {'groups': len({item['sha256'] for item in plan}),
                           'duplicates': len(plan), 'duplicate_bytes': duplicate_bytes,
                           'material_roots': list(contract.MATERIAL_ROOTS)},
        'licenses': {'path': str(Path(licenses).resolve(strict=True)), 'release_ready': True,
                     'materials_check_passed': licence_report.get('materials_check_passed'),
                     'profile': licence_report.get('profile'),
                     'failures': [], 'pending': [], 'mandatory_missing': []},
        'checks': [],
        'problems': [],
        'release_ready': False,
    }
    checks = [
        ('installed_layout', 'pass', 'all required installed paths are present'),
        ('sdk_identity', 'pass', 'SDK %s / ABI %d from installed headers' % (sdk_version, abi)),
        ('component_link_order', 'pass', ' '.join(components)),
        ('private_archives', 'pass', '%d archives in upstream order' % len(vendor)),
        ('pkgconfig_relative_prefix', 'pass', 'prefix is ${pcfiledir}/../.. with no absolute flag'),
        ('pkginfo_unit', 'pass', 'validated Name/Version/Cflags/Libs/Libs.private coverage'),
        ('licence_materials', 'pass', 'installed materials check reported release ready'),
        ('duplicate_material_plan', 'pass', '%d duplicate copies, %d bytes' % (len(plan), duplicate_bytes)),
    ]
    stage['checks'] = [{'id': name, 'status': status, 'detail': detail}
                       for name, status, detail in checks]
    stage['release_ready'] = True
    (output / 'stage.json').write_text(json.dumps(stage, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'platform': platform, 'sdk_version': sdk_version, 'files': len(records),
                      'bytes': stage['totals']['bytes'], 'pkgconfig_sha256':
                      stage['pkgconfig']['sha256'], 'duplicates': len(plan),
                      'duplicate_bytes': duplicate_bytes, 'release_ready': True}))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default=PROFILE)
    parser.add_argument('--install', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--platform', choices=('linux', 'macos'), required=True)
    parser.add_argument('--runner-os', required=True)
    parser.add_argument('--arch', required=True)
    parser.add_argument('--licenses', type=Path, required=True)
    args = parser.parse_args()
    contract.need(args.build.is_dir(), 'build directory missing')
    contract.need(os.environ.get('GITHUB_ACTIONS') == 'true',
                  'distribution candidates are staged in cloud CI only')
    try:
        return build(args.profile, args.install, args.output, args.platform,
                     args.runner_os, args.arch, args.licenses)
    except contract.ContractError as error:
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / 'stage.json').write_text(json.dumps(
            {'schema': 1, 'source_sha': os.environ.get('GITHUB_SHA'), 'platform': args.platform,
             'profile': args.profile, 'problems': [str(error)], 'checks': [],
             'release_ready': False}, indent=2) + '\n', encoding='utf-8')
        print('stage: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
