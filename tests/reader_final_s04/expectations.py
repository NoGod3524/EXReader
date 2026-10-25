"""Re-derive the S04 APK expectations from the frozen producer source.

The expectations are never typed in by hand: they are read out of the producer
commit's build.gradle, AndroidManifest.xml files, SDK version header, pinned
font table and native JNI sources. The sealed contract only pins the blob ids
and the authenticated artifact identity, so a changed producer source is a
refusal instead of a silent re-baseline.
"""
import pathlib
import re
import subprocess

MANIFESTS = ('examples/android/app/src/main/AndroidManifest.xml',
             'extras/webdav/android/webdav/src/main/AndroidManifest.xml',
             'extras/credentials/android/credentials/src/main/AndroidManifest.xml',
             'extras/android-import-entry/android/importentry/src/main/AndroidManifest.xml',
             'tests/reader_host_session_android/debug/AndroidManifest.xml')
SOURCES = ('examples/android/app/build.gradle', 'examples/android/settings.gradle',
           'examples/android/build.gradle', 'examples/android/gradle.properties',
           'include/exr/base.h', 'include/exreader.h', 'tools/host_font.py',
           'tools/reader_catalog_assets.py', 'apps/reader/store/001_catalog.sql') + MANIFESTS


def git_show(source_sha, path):
    return subprocess.run(['git', 'show', source_sha + ':' + path], check=True,
                          stdout=subprocess.PIPE).stdout


def git_blob(source_sha, path):
    return subprocess.run(['git', 'rev-parse', source_sha + ':' + path], check=True,
                          stdout=subprocess.PIPE).stdout.decode().strip()


def git_files(source_sha, directory, suffixes):
    listing = subprocess.run(['git', 'ls-tree', '-r', '--name-only', source_sha, directory],
                             check=True, stdout=subprocess.PIPE).stdout.decode().splitlines()
    return [path for path in listing if path.endswith(suffixes)]


def _match(pattern, text, label):
    found = re.search(pattern, text)
    if not found:
        raise SystemExit('cannot derive ' + label + ' from the producer source')
    return found.group(1)


def derive(source_sha):
    gradle = git_show(source_sha, 'examples/android/app/build.gradle').decode()
    values = {
        'namespace': _match(r"namespace\s+'([^']+)'", gradle, 'namespace'),
        'applicationId': _match(r"applicationId\s+'([^']+)'", gradle, 'applicationId'),
        'versionCode': _match(r"versionCode\s+(\d+)", gradle, 'versionCode'),
        'versionName': _match(r"versionName\s+'([^']+)'", gradle, 'versionName'),
        'minSdk': _match(r"minSdk\s+(\d+)", gradle, 'minSdk'),
        'targetSdk': _match(r"targetSdk\s+(\d+)", gradle, 'targetSdk'),
        'compileSdk': _match(r"compileSdk\s+(\d+)", gradle, 'compileSdk'),
        'abi': _match(r"abiFilters\s+'([^']+)'", gradle, 'abiFilters'),
    }
    values['abis'] = [values.pop('abi')]
    permissions = set()
    manifests = {}
    for path in MANIFESTS:
        text = git_show(source_sha, path).decode()
        manifests[path] = text
        for name in re.findall(r'<uses-permission[^>]*android:name="([^"]+)"', text):
            permissions.add(name)
    values['permissions'] = sorted(permissions)
    main = manifests['examples/android/app/src/main/AndroidManifest.xml']
    values['allowBackup'] = _match(r'android:allowBackup="([^"]+)"', main, 'allowBackup')
    values['main_activity'] = _match(r'android:name="\.([A-Za-z0-9_]+)"', main, 'main activity')
    values['launchable_activity'] = values['namespace'] + '.' + values['main_activity']
    values['activity_exported'] = _match(r'android:exported="([^"]+)"', main, 'activity exported')
    values['debug_network_security'] = 'networkSecurityConfig' in manifests[
        'tests/reader_host_session_android/debug/AndroidManifest.xml']
    base = git_show(source_sha, 'include/exr/base.h').decode()
    values['sdk_version'] = _match(r'#define\s+EXR_VERSION\s+"([^"]+)"', base, 'EXR_VERSION')
    host_font = git_show(source_sha, 'tools/host_font.py').decode()
    values['font_asset'] = {'name': _match(r"'(Reader\.otf)':", host_font, 'font asset'),
                            'sha256': _match(r"'Reader\.otf':\s*\('[^']*',\s*\n?\s*'([0-9a-f]{64})'", host_font,
                                             'font digest')}
    symbols = set()
    for path in git_files(source_sha, 'examples/android/app/src/main/cpp',
                          ('.c', '.cpp', '.inc', '.h')):
        text = git_show(source_sha, path).decode('utf-8', 'replace')
        symbols.update(re.findall(r'Java_(org_exreader_[A-Za-z0-9_]+)\s*\(', text))
    values['jni_symbols'] = sorted(symbols)
    values['sources'] = {path: git_blob(source_sha, path) for path in SOURCES}
    values['catalog_sql'] = {'path': 'apps/reader/store/001_catalog.sql',
                             'blob': git_blob(source_sha, 'apps/reader/store/001_catalog.sql')}
    return values


def check_sealed(contract, derived):
    sealed = contract['producer'].get('sealed_source_blobs') or {}
    if not sealed:
        return {'sealed': False, 'checked': 0}
    different = {path: {'sealed': blob, 'derived': derived['sources'].get(path)}
                 for path, blob in sealed.items() if derived['sources'].get(path) != blob}
    if different:
        raise SystemExit('producer source differs from the sealed blob ids: ' + repr(different))
    return {'sealed': True, 'checked': len(sealed)}


def source_root():
    return pathlib.Path(__file__).resolve().parents[2]
