"""Actions-only installed F3 archive, original DSO and frozen provider audit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

assert os.environ.get('GITHUB_ACTIONS') == 'true'
p = argparse.ArgumentParser()
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
ndk = Path(os.environ['ANDROID_HOME']) / 'ndk/27.2.12479018/toolchains/llvm/prebuilt/linux-x86_64'


def tool(name, *args):
    return subprocess.check_output([str(ndk / 'bin' / name), *map(str, args)], text=True)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


stage = Path('build/android-preferences/preferences-stage')
archive = stage / 'lib/libreader_preferences.a'
symbols = tool('llvm-nm', '--defined-only', archive)
assert all(name in symbols for name in ('reader_preferences_defaults', 'reader_preferences_save', 'reader_preferences_load'))
assert not re.search(r'\b(?:sqlite3_|exr_library_|exr_document_|exr_pager_)\w*\s*$', symbols, re.M)
assert (stage / 'include/reader_preferences.h').read_bytes() == Path('apps/reader/preferences/include/reader_preferences.h').read_bytes()
(a.output / 'preferences-archive-defined.txt').write_text(symbols)
checks = []
app = Path('examples/android/app')
for variant in ('Debug', 'Release'):
    lower = variant.lower()
    kinds = (variant,) if variant == 'Debug' else ('Release', 'RelWithDebInfo')
    apk = app / 'build/outputs/apk' / lower / ('app-' + lower + ('-unsigned' if variant == 'Release' else '') + '.apk')
    with zipfile.ZipFile(apk) as package:
        evidence = {}
        for name in ('exreader_host', 'exreader_product'):
            copied = a.output / (lower + '-lib' + name + '.so')
            copied.write_bytes(package.read('lib/x86_64/lib' + name + '.so'))
            files = [path for kind in kinds for path in (app / 'build/intermediates/cxx' / kind).rglob('lib' + name + '.so')]
            assert len(files) == 1
            symbols = tool('llvm-nm', '--defined-only', files[0])
            needed = re.findall(r'\(NEEDED\).*\[([^\]]+)\]', tool('llvm-readelf', '-d', copied))
            assert ('reader_preferences_save' in symbols) == (name == 'exreader_host')
            if name == 'exreader_host':
                assert 'Java_org_exreader_host_NativePreferences_save' in symbols and needed.count('libexreader.so') == 1
                assert not re.search(r'\b(?:sqlite3_|reader_revision_)\w*\s*$', symbols, re.M)
            else:
                assert 'libexreader.so' not in needed and len(re.findall(r'\bsqlite3_open_v2\s*$', symbols, re.M)) == 1
            (a.output / (lower + '-' + name + '-defined.txt')).write_text(symbols)
            evidence[name] = {'bytes': copied.stat().st_size, 'sha256': digest(copied), 'needed': needed}
        if variant == 'Release':
            assert not any(b'PreferencesUiTest' in package.read(entry) for entry in package.namelist())
    checks.append({'variant': variant, 'apk_bytes': apk.stat().st_size, 'apk_sha256': digest(apk), 'libraries': evidence})
result = {**{key: os.environ[value] for key, value in [('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT')]},
          'accepted': True, 'archive_bytes': archive.stat().st_size, 'archive_sha256': digest(archive), 'checks': checks,
          'single_existing_sdk_owner': True, 'unchanged_product_owner': True}
(a.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result), flush=True)
