#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify F12 distribution package completeness: licenses, SBOMs, and user guide bundled in packages."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import generate_package_sbom as sbom_gen

MIN_CYCLONEDX_COMPONENTS = 43
MIN_SPDX_PACKAGES = 44
MIN_SPDX_FILES = 15

SDK_REQUIRED_PATHS = (
    'LICENSE',
    'THIRD_PARTY_NOTICES.md',
    'share/exreader/LICENSE',
    'share/exreader/THIRD_PARTY_NOTICES.md',
    'share/exreader/READER-INSTALL-UPGRADE-IMPORT-SYNC.md',
    'share/exreader/hyph-en-us.LICENSE.txt',
    'share/exreader/sbom.cdx.json',
    'share/exreader/sbom.spdx.json',
    'docs/READING-LICENSES.md',
    'docs/READING-LICENSE-REVIEW.md',
    'docs/READER-DISTRIBUTION-INVENTORY.md',
)

WINDOWS_REQUIRED_FILES = (
    'EXReader.exe',
    'Reader.otf',
    'OFL.txt',
    'LICENSE.txt',
    'THIRD_PARTY_NOTICES.md',
    'READER-INSTALL-UPGRADE-IMPORT-SYNC.md',
    'sbom.cdx.json',
    'sbom.spdx.json',
    'licenses/hyph-en-us.LICENSE.txt',
    'licenses/freetype/FTL.TXT',
    'licenses/freetype/LICENSE.TXT',
    'licenses/expat/COPYING',
    'licenses/miniz/LICENSE',
    'licenses/stb/LICENSE',
)

LINUX_REQUIRED_FILES = (
    'bin/exreader-linux',
    'Reader.otf',
    'OFL.txt',
    'LICENSE',
    'THIRD_PARTY_NOTICES.md',
    'READER-INSTALL-UPGRADE-IMPORT-SYNC.md',
    'sbom.cdx.json',
    'sbom.spdx.json',
    'licenses/hyph-en-us.LICENSE.txt',
    'licenses/freetype/FTL.TXT',
    'licenses/freetype/LICENSE.TXT',
    'licenses/expat/COPYING',
    'licenses/miniz/LICENSE',
    'licenses/stb/LICENSE',
)

PRIVATE_PATH_NEEDLES = ('/home/runner/', '/Users/runner/', 'D:\\a\\', 'C:\\Users\\', 'C:/Users/')


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def verify_sbom_documents(cdx: dict, spdx: dict, decl: dict) -> list:
    problems = []
    sdk_version = decl['versions']['EXR_VERSION']

    if cdx.get('bomFormat') != 'CycloneDX' or cdx.get('specVersion') != '1.5':
        problems.append('CycloneDX header must be bomFormat=CycloneDX specVersion=1.5')
    components = cdx.get('components')
    if not isinstance(components, list) or len(components) < MIN_CYCLONEDX_COMPONENTS:
        problems.append(
            f'CycloneDX component count {len(components) if isinstance(components, list) else 0} < {MIN_CYCLONEDX_COMPONENTS}'
        )
    else:
        comp_names = {c.get('name') for c in components}
        for mod in decl['sdk_modules']:
            if mod['name'] not in comp_names:
                problems.append(f'CycloneDX missing SDK module {mod["name"]}')
        for reg in decl['registered_components']:
            if reg['name'] not in comp_names:
                problems.append(f'CycloneDX missing registered component {reg["name"]}')
        for pkg in decl['product_packages']:
            if pkg['name'] not in comp_names:
                problems.append(f'CycloneDX missing product package {pkg["name"]}')

    meta_comp = cdx.get('metadata', {}).get('component', {})
    if meta_comp.get('version') != sdk_version:
        problems.append(f'CycloneDX metadata version {meta_comp.get("version")!r} != {sdk_version!r}')

    props = {p.get('name'): p.get('value') for p in cdx.get('metadata', {}).get('properties', [])}
    files_by_path = {f['path']: f for f in decl['tracked_files']}
    if props.get('exr:user_guide') != 'docs/READER-INSTALL-UPGRADE-IMPORT-SYNC.md':
        problems.append('CycloneDX metadata missing exr:user_guide property')
    if props.get('exr:user_guide_sha256') != files_by_path['docs/READER-INSTALL-UPGRADE-IMPORT-SYNC.md']['sha256']:
        problems.append('CycloneDX exr:user_guide_sha256 does not match docs/READER-INSTALL-UPGRADE-IMPORT-SYNC.md')
    if props.get('exr:license_sha256') != files_by_path['LICENSE']['sha256']:
        problems.append('CycloneDX exr:license_sha256 does not match LICENSE')
    if props.get('exr:third_party_notices_sha256') != files_by_path['THIRD_PARTY_NOTICES.md']['sha256']:
        problems.append('CycloneDX exr:third_party_notices_sha256 does not match THIRD_PARTY_NOTICES.md')

    if spdx.get('spdxVersion') != 'SPDX-2.3' or spdx.get('dataLicense') != 'CC0-1.0':
        problems.append('SPDX header must be spdxVersion=SPDX-2.3 dataLicense=CC0-1.0')
    packages = spdx.get('packages')
    if not isinstance(packages, list) or len(packages) < MIN_SPDX_PACKAGES:
        problems.append(
            f'SPDX package count {len(packages) if isinstance(packages, list) else 0} < {MIN_SPDX_PACKAGES}'
        )
    spdx_files = spdx.get('files')
    if not isinstance(spdx_files, list) or len(spdx_files) < MIN_SPDX_FILES:
        problems.append(
            f'SPDX file count {len(spdx_files) if isinstance(spdx_files, list) else 0} < {MIN_SPDX_FILES}'
        )
    else:
        observed_sha1s = []
        for sf in spdx_files:
            fname = sf.get('fileName')
            if fname not in files_by_path:
                problems.append(f'SPDX lists unknown file {fname!r}')
                continue
            expected_file = files_by_path[fname]
            sums = {c.get('algorithm'): c.get('checksumValue') for c in sf.get('checksums', [])}
            if sums.get('SHA256') != expected_file['sha256'] or sums.get('SHA1') != expected_file['sha1']:
                problems.append(f'SPDX file checksum mismatch for {fname}')
            if sums.get('SHA1'):
                observed_sha1s.append(sums['SHA1'])
        if packages and isinstance(packages, list):
            expected_verif = hashlib.sha1(''.join(sorted(observed_sha1s)).encode('ascii')).hexdigest()
            actual_verif = packages[0].get('packageVerificationCode', {}).get('packageVerificationCodeValue')
            if actual_verif != expected_verif:
                problems.append('SPDX packageVerificationCodeValue mismatch')

    return problems


def verify_repo_sboms_and_scripts(root: Path = ROOT) -> tuple[list, dict]:
    problems = []
    decl = sbom_gen.collect_declarations(root)
    cdx_path = root / 'docs/sbom.cdx.json'
    spdx_path = root / 'docs/sbom.spdx.json'
    if not cdx_path.is_file() or not spdx_path.is_file():
        return ['missing docs/sbom.cdx.json or docs/sbom.spdx.json'], {}

    cdx_raw = cdx_path.read_bytes()
    spdx_raw = spdx_path.read_bytes()
    for label, raw in (('docs/sbom.cdx.json', cdx_raw), ('docs/sbom.spdx.json', spdx_raw)):
        for needle in PRIVATE_PATH_NEEDLES:
            if needle.encode('utf-8') in raw:
                problems.append(f'{label} contains private path needle {needle!r}')

    cdx = json.loads(cdx_raw.decode('utf-8'))
    spdx = json.loads(spdx_raw.decode('utf-8'))
    problems.extend(verify_sbom_documents(cdx, spdx, decl))

    expected_cdx = sbom_gen.build_cyclonedx(decl, cdx.get('metadata', {}).get('timestamp', sbom_gen.DEFAULT_TIMESTAMP))
    expected_spdx = sbom_gen.build_spdx(decl, spdx.get('creationInfo', {}).get('created', sbom_gen.DEFAULT_TIMESTAMP))
    if cdx != expected_cdx:
        problems.append('docs/sbom.cdx.json differs from live CMake/license declarations')
    if spdx != expected_spdx:
        problems.append('docs/sbom.spdx.json differs from live CMake/license declarations')

    cmake_text = (root / 'CMakeLists.txt').read_text(encoding='utf-8')
    for token in ('docs/READER-INSTALL-UPGRADE-IMPORT-SYNC.md', 'data/hyph-en-us.LICENSE.txt',
                  'docs/sbom.cdx.json', 'docs/sbom.spdx.json'):
        if token not in cmake_text:
            problems.append(f'CMakeLists.txt install rules missing {token}')

    for script_rel in ('tools/build_windows_host.py', 'tools/build_linux_host.py'):
        script_text = (root / script_rel).read_text(encoding='utf-8')
        for token in ('READER-INSTALL-UPGRADE-IMPORT-SYNC.md', 'hyph-en-us.LICENSE.txt',
                      'sbom.cdx.json', 'sbom.spdx.json', 'THIRD_PARTY_NOTICES.md'):
            if token not in script_text:
                problems.append(f'{script_rel} missing packaging copy for {token}')

    summary = {
        'sdk_version': decl['versions']['EXR_VERSION'],
        'cyclonedx_components': len(cdx.get('components', [])),
        'spdx_packages': len(spdx.get('packages', [])),
        'spdx_files': len(spdx.get('files', [])),
    }
    return problems, summary


def verify_sdk_stage(stage: Path, root: Path = ROOT) -> list:
    problems = []
    stage = stage.resolve()
    for rel in SDK_REQUIRED_PATHS:
        target = stage / rel
        if not target.is_file() or target.stat().st_size == 0:
            problems.append(f'SDK stage missing required file: {rel}')
    expected_map = {
        'LICENSE': root / 'LICENSE',
        'THIRD_PARTY_NOTICES.md': root / 'THIRD_PARTY_NOTICES.md',
        'share/exreader/LICENSE': root / 'LICENSE',
        'share/exreader/THIRD_PARTY_NOTICES.md': root / 'THIRD_PARTY_NOTICES.md',
        'share/exreader/READER-INSTALL-UPGRADE-IMPORT-SYNC.md': root / 'docs/READER-INSTALL-UPGRADE-IMPORT-SYNC.md',
        'share/exreader/hyph-en-us.LICENSE.txt': root / 'data/hyph-en-us.LICENSE.txt',
        'share/exreader/sbom.cdx.json': root / 'docs/sbom.cdx.json',
        'share/exreader/sbom.spdx.json': root / 'docs/sbom.spdx.json',
    }
    for rel, src in expected_map.items():
        installed = stage / rel
        if installed.is_file() and src.is_file():
            if sha256_bytes(installed.read_bytes()) != sha256_bytes(src.read_bytes()):
                problems.append(f'SDK stage {rel} SHA-256 differs from source {src.relative_to(root).as_posix()}')
    return problems


def load_archive_entries(package_path: Path) -> tuple[dict, dict | None]:
    package_path = package_path.resolve()
    manifest = None
    if package_path.is_dir():
        if (package_path / 'build.json').is_file():
            manifest = json.loads((package_path / 'build.json').read_text(encoding='utf-8'))
        if (package_path / 'EXReader-Windows.zip').is_file():
            package_path = package_path / 'EXReader-Windows.zip'
        elif (package_path / 'EXReader-Linux.tar.gz').is_file():
            package_path = package_path / 'EXReader-Linux.tar.gz'
        else:
            payload = package_path / 'payload' if (package_path / 'payload').is_dir() else package_path
            entries = {
                p.relative_to(payload).as_posix(): p.read_bytes()
                for p in sorted(payload.rglob('*'))
                if p.is_file()
            }
            return entries, manifest

    entries = {}
    if package_path.name.endswith('.zip'):
        with zipfile.ZipFile(package_path) as zf:
            for info in zf.infolist():
                if not info.is_dir():
                    entries[info.filename.replace('\\', '/')] = zf.read(info)
    elif package_path.name.endswith(('.tar.gz', '.tgz')):
        with tarfile.open(package_path, 'r:gz') as tf:
            for member in tf.getmembers():
                if member.isfile():
                    extracted = tf.extractfile(member)
                    if extracted is not None:
                        clean_name = member.name.lstrip('./')
                        entries[clean_name] = extracted.read()
    else:
        raise ValueError(f'unsupported package path: {package_path}')
    return entries, manifest


def verify_host_package(package_path: Path, platform_kind: str, root: Path = ROOT) -> list:
    problems = []
    entries, manifest = load_archive_entries(package_path)
    required = WINDOWS_REQUIRED_FILES if platform_kind == 'windows' else LINUX_REQUIRED_FILES
    for req in required:
        if req not in entries:
            problems.append(f'{platform_kind} package missing {req}')
        elif len(entries[req]) == 0:
            problems.append(f'{platform_kind} package has empty {req}')

    license_name = 'LICENSE.txt' if platform_kind == 'windows' else 'LICENSE'
    comparisons = {
        license_name: root / 'LICENSE',
        'THIRD_PARTY_NOTICES.md': root / 'THIRD_PARTY_NOTICES.md',
        'READER-INSTALL-UPGRADE-IMPORT-SYNC.md': root / 'docs/READER-INSTALL-UPGRADE-IMPORT-SYNC.md',
        'sbom.cdx.json': root / 'docs/sbom.cdx.json',
        'sbom.spdx.json': root / 'docs/sbom.spdx.json',
        'licenses/hyph-en-us.LICENSE.txt': root / 'data/hyph-en-us.LICENSE.txt',
    }
    for arc_name, src_path in comparisons.items():
        if arc_name in entries and src_path.is_file():
            if sha256_bytes(entries[arc_name]) != sha256_bytes(src_path.read_bytes()):
                problems.append(f'{platform_kind} package {arc_name} SHA-256 differs from repository source')

    if manifest is not None:
        manifest_files = {k.replace('\\', '/'): v for k, v in manifest.get('files', {}).items()}
        for req in required:
            if req not in manifest_files:
                problems.append(f'{platform_kind} build.json missing {req}')
            elif req in entries and manifest_files[req] != sha256_bytes(entries[req]):
                problems.append(f'{platform_kind} build.json digest mismatch for {req}')

    return problems


def run_negative_selftests(root: Path = ROOT) -> list:
    checks = []
    decl = sbom_gen.collect_declarations(root)
    cdx = sbom_gen.build_cyclonedx(decl)
    spdx = sbom_gen.build_spdx(decl)
    assert verify_sbom_documents(cdx, spdx, decl) == []
    checks.append('positive-sbom-validation')

    truncated_cdx = deepcopy(cdx)
    truncated_cdx['components'] = truncated_cdx['components'][:10]
    assert any('CycloneDX component count' in p for p in verify_sbom_documents(truncated_cdx, spdx, decl))
    checks.append('reject-truncated-cyclonedx-components')

    tampered_guide_cdx = deepcopy(cdx)
    for prop in tampered_guide_cdx['metadata']['properties']:
        if prop['name'] == 'exr:user_guide_sha256':
            prop['value'] = '0' * 64
    assert any('exr:user_guide_sha256' in p for p in verify_sbom_documents(tampered_guide_cdx, spdx, decl))
    checks.append('reject-tampered-user-guide-digest')

    tampered_spdx = deepcopy(spdx)
    tampered_spdx['files'][0]['checksums'][1]['checksumValue'] = '0' * 64
    assert any('SPDX file checksum mismatch' in p for p in verify_sbom_documents(cdx, tampered_spdx, decl))
    checks.append('reject-tampered-spdx-file-digest')

    with tempfile.TemporaryDirectory(prefix='f12-dist-test-') as tmp:
        tmp_path = Path(tmp)
        win_zip = tmp_path / 'EXReader-Windows.zip'
        with zipfile.ZipFile(win_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            for name in WINDOWS_REQUIRED_FILES:
                if name == 'LICENSE.txt':
                    zf.writestr(name, (root / 'LICENSE').read_bytes())
                elif name == 'THIRD_PARTY_NOTICES.md':
                    zf.writestr(name, (root / 'THIRD_PARTY_NOTICES.md').read_bytes())
                elif name == 'READER-INSTALL-UPGRADE-IMPORT-SYNC.md':
                    zf.writestr(name, (root / 'docs/READER-INSTALL-UPGRADE-IMPORT-SYNC.md').read_bytes())
                elif name == 'sbom.cdx.json':
                    zf.writestr(name, (root / 'docs/sbom.cdx.json').read_bytes())
                elif name == 'sbom.spdx.json':
                    zf.writestr(name, (root / 'docs/sbom.spdx.json').read_bytes())
                elif name == 'licenses/hyph-en-us.LICENSE.txt':
                    zf.writestr(name, (root / 'data/hyph-en-us.LICENSE.txt').read_bytes())
                else:
                    zf.writestr(name, b'synthetic-fixture-bytes')
        assert verify_host_package(win_zip, 'windows', root) == []
        checks.append('positive-windows-archive-contract')

        incomplete_zip = tmp_path / 'incomplete.zip'
        with zipfile.ZipFile(win_zip, 'r') as src_zf, zipfile.ZipFile(incomplete_zip, 'w') as dst_zf:
            for info in src_zf.infolist():
                if info.filename != 'READER-INSTALL-UPGRADE-IMPORT-SYNC.md':
                    dst_zf.writestr(info, src_zf.read(info))
        assert any('READER-INSTALL-UPGRADE-IMPORT-SYNC.md' in p for p in verify_host_package(incomplete_zip, 'windows', root))
        checks.append('reject-missing-user-guide-in-package')

        linux_tar = tmp_path / 'EXReader-Linux.tar.gz'
        linux_dir = tmp_path / 'linux-payload'
        for name in LINUX_REQUIRED_FILES:
            dest = linux_dir / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if name == 'LICENSE':
                dest.write_bytes((root / 'LICENSE').read_bytes())
            elif name == 'THIRD_PARTY_NOTICES.md':
                dest.write_bytes((root / 'THIRD_PARTY_NOTICES.md').read_bytes())
            elif name == 'READER-INSTALL-UPGRADE-IMPORT-SYNC.md':
                dest.write_bytes((root / 'docs/READER-INSTALL-UPGRADE-IMPORT-SYNC.md').read_bytes())
            elif name == 'sbom.cdx.json':
                dest.write_bytes((root / 'docs/sbom.cdx.json').read_bytes())
            elif name == 'sbom.spdx.json':
                dest.write_bytes((root / 'docs/sbom.spdx.json').read_bytes())
            elif name == 'licenses/hyph-en-us.LICENSE.txt':
                dest.write_bytes((root / 'data/hyph-en-us.LICENSE.txt').read_bytes())
            else:
                dest.write_bytes(b'synthetic-linux-fixture-bytes')
        with tarfile.open(linux_tar, 'w:gz') as tf:
            for p in sorted(linux_dir.rglob('*')):
                if p.is_file():
                    tf.add(p, arcname=p.relative_to(linux_dir).as_posix())
        assert verify_host_package(linux_tar, 'linux', root) == []
        checks.append('positive-linux-archive-contract')

    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk-stage', type=Path)
    parser.add_argument('--windows-package', type=Path)
    parser.add_argument('--linux-package', type=Path)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()

    problems, summary = verify_repo_sboms_and_scripts(ROOT)
    checked_targets = ['repo-sbom-and-scripts']

    if args.sdk_stage:
        problems.extend(verify_sdk_stage(args.sdk_stage, ROOT))
        checked_targets.append('sdk-stage')
    if args.windows_package:
        problems.extend(verify_host_package(args.windows_package, 'windows', ROOT))
        checked_targets.append('windows-package')
    if args.linux_package:
        problems.extend(verify_host_package(args.linux_package, 'linux', ROOT))
        checked_targets.append('linux-package')

    selftests = []
    if args.self_test or not (args.sdk_stage or args.windows_package or args.linux_package):
        selftests = run_negative_selftests(ROOT)

    result = {
        'accepted': not problems,
        'checked_targets': checked_targets,
        'selftests': selftests,
        'selftest_count': len(selftests),
        'summary': summary,
        'problems': problems,
    }
    print(json.dumps(result, indent=2))
    return 0 if not problems else 1


if __name__ == '__main__':
    raise SystemExit(main())
