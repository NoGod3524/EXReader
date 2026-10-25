"""Actions-only G03/G04 ABI/provider evidence on the actual Debug/Release APKs."""
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


product = Path('build/session-android/product-stage')
archives = {}
for name, symbol in [('reader_reading_commands', 'reader_rc_apply'), ('reader_annotation_view', 'reader_av_page_get')]:
    archive = product / 'lib' / ('lib' + name + '.a')
    symbols = tool('llvm-nm', '--defined-only', archive)
    assert symbol in symbols and not re.search(r'\b(?:sqlite3_|exr_library_|exr_document_|exr_pager_)\w*\s*$', symbols, re.M)
    (a.output / (name + '-defined.txt')).write_text(symbols)
    archives[name] = {'bytes': archive.stat().st_size, 'sha256': digest(archive)}
app = Path('examples/android/app')
sdk_archives = {path.name for path in Path('build/session-android/sdk-stage').rglob('*.a')}
assert sdk_archives
checks = []
for variant in ('Debug', 'Release'):
    lower = variant.lower()
    kinds = (variant,) if variant == 'Debug' else ('Release', 'RelWithDebInfo')
    apk = app / 'build/outputs/apk' / lower / ('app-' + lower + ('-unsigned' if variant == 'Release' else '') + '.apk')
    libraries = {}
    with zipfile.ZipFile(apk) as package:
        for name in ('exreader_host', 'exreader_product'):
            entry = 'lib/x86_64/lib' + name + '.so'
            copied = a.output / (lower + '-' + Path(entry).name)
            copied.write_bytes(package.read(entry))
            dynamic = tool('llvm-readelf', '-d', copied)
            libraries[name] = {'sha256': digest(copied), 'bytes': copied.stat().st_size,
                               'needed': re.findall(r'\(NEEDED\).*\[([^\]]+)\]', dynamic)}
            files = [path for kind in kinds for path in (app / 'build/intermediates/cxx' / kind).rglob('lib' + name + '.so')]
            mapname = 'sdk-host-link.map' if name == 'exreader_host' else 'product-link.map'
            maps = [path for kind in kinds for path in (app / '.cxx' / kind).rglob(mapname)]
            assert len(files) == len(maps) == 1
            symbols = tool('llvm-nm', '--defined-only', files[0])
            mapping = maps[0].read_text()
            (a.output / (lower + '-' + mapname)).write_text(mapping)
            (a.output / (lower + '-' + name + '-defined.txt')).write_text(symbols)
            if name == 'exreader_product':
                assert 'libreader_reading_commands.a' in mapping and 'libreader_annotation_view.a' in mapping and 'libreader_reading_state_codec.a' in mapping
                assert all(symbol in symbols for symbol in ('reader_rc_apply', 'reader_av_page_get', 'reader_rs_decode'))
                assert len(re.findall(r'\bsqlite3_open_v2\s*$', symbols, re.M)) == 1
                assert not any(item in mapping for item in sdk_archives)
                assert not re.search(r'\bexr_(?:library_|document_|pager_|anchor_)\w*\s*$', symbols, re.M)
                assert ('Java_org_exreader_host_NativeReadingProbe_nativeReceive' in symbols) == (variant == 'Debug')
            else:
                assert libraries[name]['needed'].count('libexreader.so') == 1
                assert all('lib' + archive + '.a' not in mapping for archive in archives)
                assert not re.search(r'\b(?:sqlite3_|reader_rc_|reader_av_|reader_revision_)\w*\s*$', symbols, re.M)
        if variant == 'Release':
            for entry in package.infolist():
                data = entry.filename.encode() + package.read(entry)
                assert not any(name in data for name in (b'NativeReadingProbe', b'ReadingReview', b'ReadingUiTest')), entry.filename
    checks.append({'variant': variant, 'apk_sha256': digest(apk), 'apk_bytes': apk.stat().st_size, 'libraries': libraries})
result = {**{key: os.environ[value] for key, value in [('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT')]},
          'accepted': True, 'archives': archives, 'checks': checks, 'same_product_owner_dso': True,
          'one_product_sqlite': True, 'sdk_single_shared_provider': True, 'codec_does_not_link_sdk': True}
(a.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result), flush=True)
