"""Actions-only: bind the Android 3.42 archive's licence materials to the installed SDK/product trees.

  verify    archive licenses/ == SDK install tree (byte for byte, closed set); registered licence set for the
            switches in the build's own CMakeCache; vendor archives actually installed; product prefix licence
            files incl. the SQLite declaration; native libraries the APK really needs.
  finalize  the original emulator install result for the same archive.

Materials check only. It does not read the compiled binaries for third-party code and gives no legal conclusion.
"""
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import check as handoff  # noqa: E402
import safezip  # noqa: E402

OUT = ROOT / 'build/c3-android'
WAVE = ROOT / 'build/wave3'
F06 = ROOT / 'build/f06'
VERSION = '3.42.0'
PRODUCT_KEYS = ('licen', 'copying', 'notice', 'public-domain')
SYSTEM_LIBS = {'libc.so', 'libm.so', 'libdl.so', 'liblog.so', 'libandroid.so', 'libz.so', 'libjnigraphics.so'}


def tree(base):
    base = Path(base)
    return {p.relative_to(base).as_posix(): p.read_bytes() for p in sorted(base.rglob('*')) if p.is_file()}


def sdk_switches():
    values, used = {}, []
    for cache in sorted(WAVE.rglob('CMakeCache.txt')):
        found = {}
        for line in cache.read_text(encoding='utf-8', errors='replace').splitlines():
            match = re.match(r'(EXR_\w+):\w+=(.*)$', line)
            if match:
                found[match.group(1)] = handoff.normal(match.group(2))
        if 'EXR_ENABLE_PDF' in found and 'EXR_ENABLE_AUDIO' in found:
            used.append(cache.relative_to(ROOT).as_posix())
            for key, value in found.items():
                values[key] = 'ON' if 'ON' in (values.get(key), value) else 'OFF'
    merged = dict(handoff.option_defaults())
    merged.update(values)
    return merged, used


def package_versions(prefix):
    out = {}
    for config in sorted(Path(prefix).glob('lib/cmake/*')):
        version = ''
        for candidate in config.glob('*ConfigVersion.cmake'):
            match = re.search(r'PACKAGE_VERSION\s+"([^"]+)"', candidate.read_text(encoding='utf-8', errors='replace'))
            version = match.group(1) if match else ''
        out[config.name] = version or 'no version file'
    return out


def needed(apk_bytes):
    ndk = Path(os.environ['ANDROID_HOME']) / 'ndk' / os.environ['C11_NDK'] / 'toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf'
    folder = OUT / 'apk-libs'
    folder.mkdir(parents=True, exist_ok=True)
    result = {}
    with zipfile.ZipFile(io.BytesIO(apk_bytes)) as apk:
        for name in sorted(apk.namelist()):
            if re.fullmatch(r'lib/[^/]+/[^/]+\.so', name):
                target = folder / (name.replace('/', '__'))
                target.write_bytes(apk.read(name))
                text = subprocess.check_output([str(ndk), '-d', str(target)], text=True)
                result[name] = sorted(re.findall(r'\(NEEDED\)\s+Shared library: \[([^\]]+)\]', text))
    return result


def verify():
    failures = []
    manifest = json.loads((F06 / 'android/manifest.json').read_text(encoding='utf-8'))
    archive = F06 / 'android' / manifest['archive']['name']
    sha = handoff.sha256_file(archive)
    assert sha == manifest['archive']['sha256'] and archive.stat().st_size == manifest['archive']['bytes']
    assert manifest['source_sha'] == os.environ['GITHUB_SHA'] and manifest['sdk_version'] == VERSION and manifest['target'] == 'android'
    assert manifest['provenance']['run_id'] == os.environ['GITHUB_RUN_ID']
    assert manifest['provenance']['attempt'] == os.environ['GITHUB_RUN_ATTEMPT']
    contents = safezip.read_members(archive, archive.name)
    assert set(contents) == set(manifest['files']) | set(manifest['metadata_files']), 'archive members differ from manifest'
    for name, record in manifest['files'].items():
        assert handoff.sha256(contents[name]) == record['sha256'] and len(contents[name]) == record['bytes'], name

    # 1. archive licenses/ is the SDK install tree, byte for byte, and nothing else.
    sdk = tree(WAVE / 'sdk-stage/share/exreader/licenses')
    packed = {n[len('licenses/'):]: d for n, d in contents.items() if n.startswith('licenses/')}
    missing_from_archive = sorted(set(sdk) - set(packed))
    extra_in_archive = sorted(set(packed) - set(sdk))
    differing = sorted(n for n in set(sdk) & set(packed) if sdk[n] != packed[n])
    if not sdk or missing_from_archive or extra_in_archive or differing:
        failures.append(['archive licenses/ differs from the SDK install tree', missing_from_archive, extra_in_archive, differing])

    # 2. registered licence set for the build's own switches, and the vendor archives really installed.
    module = handoff.registry()
    switches, caches = sdk_switches()
    if not caches:
        failures.append('no SDK CMakeCache with EXR_ENABLE_* switches found under build/wave3')
    expected = handoff.expected_materials(module, switches)
    registry_missing = sorted(set(expected) - set(sdk))
    unregistered_installed = sorted(set(sdk) - set(expected))
    if registry_missing:
        failures.append(['registered licence files not installed by the SDK', registry_missing])
    enabled = [c for c in module.COMPONENTS if c['id'] != 'exreader' and module.enabled(c['when'], switches)]
    vendor_dir = WAVE / 'sdk-stage/lib/exreader'
    installed_vendor = sorted(re.sub(r'^(lib)?exr_vendor_|\.(a|lib)$', '', p.name) for p in vendor_dir.glob('*')) if vendor_dir.is_dir() else []
    wanted_vendor = sorted({v for c in enabled for v in c.get('vendor_files', [])})
    known_vendor = {v for c in module.COMPONENTS for v in c.get('vendor_files', [])}
    vendor_missing = sorted(set(wanted_vendor) - set(installed_vendor))
    vendor_unregistered = sorted(set(installed_vendor) - known_vendor)
    if vendor_missing or vendor_unregistered:
        failures.append(['vendor archives differ from the registry', vendor_missing, vendor_unregistered])

    # 3. product prefix: licence-like files must be shipped; SQLite declaration must match the repository text.
    stage = WAVE / 'stage'
    share = stage / 'share'
    product = {p.relative_to(share).as_posix(): p.read_bytes() for p in sorted(share.rglob('*'))
               if p.is_file() and any(k in p.name.lower() for k in PRODUCT_KEYS)} if share.is_dir() else {}
    packed_product = {n[len('product-licenses/'):]: d for n, d in contents.items() if n.startswith('product-licenses/')}
    if product != packed_product or not product:
        failures.append(['archive product-licenses/ differs from the product prefix',
                         sorted(set(product) ^ set(packed_product)), sorted(n for n in set(product) & set(packed_product) if product[n] != packed_product[n])])
    sqlite_key = 'exreader-product/sqlite-public-domain.txt'
    repository_sqlite = (ROOT / 'licenses/sqlite-public-domain.txt').read_bytes()
    if product.get(sqlite_key) != repository_sqlite or packed_product.get(sqlite_key) != repository_sqlite:
        failures.append('product SQLite declaration missing or not equal to licenses/sqlite-public-domain.txt')
    if switches.get('EXR_ENABLE_LIBRARY') == 'ON' and 'sqlite/sqlite-public-domain.txt' not in packed:
        failures.append('SDK SQLite declaration absent from archive licenses/')
    product_archives = sorted(p.name for p in (stage / 'lib').glob('*.a')) if (stage / 'lib').is_dir() else []

    # 4. native libraries the APK needs (system/NDK provided ones are not EXReader-packaged).
    apk_bytes = contents['artifacts/app-debug.apk']
    assert apk_bytes == (WAVE / 'artifacts/app-debug.apk').read_bytes(), 'archive APK differs from the built APK'
    libs = needed(apk_bytes)
    unclassified = sorted({n for deps in libs.values() for n in deps} - SYSTEM_LIBS)
    with zipfile.ZipFile(io.BytesIO(apk_bytes)) as apk:
        apk_assets = sorted(n for n in apk.namelist() if n.startswith('assets/'))
    report = dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                  archive=manifest['archive'], sdk_cmake_caches=caches, sdk_switches={k: v for k, v in sorted(switches.items()) if k.startswith('EXR_ENABLE_')},
                  sdk_licence_files=len(sdk), archive_licence_files=len(packed), byte_identical_to_sdk_tree=not (missing_from_archive or extra_in_archive or differing),
                  registry_expected=len(expected), registry_missing=registry_missing, installed_but_not_in_registry_expected=unregistered_installed,
                  enabled_components=[c['id'] for c in enabled], installed_vendor_archives=installed_vendor,
                  vendor_missing=vendor_missing, vendor_unregistered=vendor_unregistered,
                  sdk_packages=package_versions(WAVE / 'sdk-stage'), product_packages=package_versions(stage), product_archives=product_archives,
                  product_licence_files=sorted(product), product_sqlite_matches_repository=product.get(sqlite_key) == repository_sqlite,
                  apk_native_libraries={k: v for k, v in libs.items()}, apk_needed_not_system=unclassified, apk_assets=apk_assets,
                  limits=['third-party code inside the compiled .so files is inferred from CMake switches and installed archives, not from the binaries',
                          'NDK c++_static runtime and Android system libraries are not licence-packaged by EXReader',
                          'Gradle/Java dependencies are the first-party local projects webdav, credentials and importentry (examples/android/app/build.gradle)',
                          'licence text equality with upstream is checked by tools/check_reading_licenses.py, not here',
                          'no legal conclusion'],
                  failures=failures, passed=not failures)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'license-verify.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    handoff.summary_line('### Android SDK 3.42 archive licence binding (source `' + os.environ['GITHUB_SHA'][:12] + '`)')
    handoff.summary_line('- archive `%s` sha256 `%s`' % (archive.name, sha))
    handoff.summary_line('- archive licenses/ = %d files, SDK install tree = %d files, byte-identical: %s' % (
        len(packed), len(sdk), report['byte_identical_to_sdk_tree']))
    handoff.summary_line('- registry-expected %d, missing %d, installed-but-unexpected %d; enabled components: %s' % (
        len(expected), len(registry_missing), len(unregistered_installed), ', '.join(report['enabled_components'])))
    handoff.summary_line('- vendor archives: %s; missing %s; unregistered %s' % (installed_vendor, vendor_missing, vendor_unregistered))
    handoff.summary_line('- product packages %s; product licence files %s; product SQLite declaration equals repository: %s' % (
        report['product_packages'], sorted(product), report['product_sqlite_matches_repository']))
    handoff.summary_line('- APK native libraries need (non-system): %s' % (unclassified or 'none'))
    handoff.summary_line('- failures: %s' % (failures or 'none'))
    assert not failures, failures


def finalize():
    manifest = json.loads((F06 / 'android/manifest.json').read_text(encoding='utf-8'))
    result = json.loads((F06 / 'android/result.json').read_text(encoding='utf-8'))
    entry = json.loads((F06 / 'android/entry.json').read_text(encoding='utf-8'))
    apk_sha = manifest['files']['artifacts/app-debug.apk']['sha256']
    assert result['passed'] is True and result['target'] == 'android' and result['source_sha'] == os.environ['GITHUB_SHA']
    assert result['program_sha256'] == apk_sha == entry['installed_apk_sha256'] and entry['launch_passed'] is True
    handoff.summary_line('- emulator: installed APK sha256 `%s` equals the archived APK; launch passed (API %s, %s)' % (
        apk_sha, entry.get('api'), entry.get('abi')))


if __name__ == '__main__':
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub Actions only'
    {'verify': verify, 'finalize': finalize}[sys.argv[1]]()
