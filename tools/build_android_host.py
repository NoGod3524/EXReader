#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build the installed EXReader SDK for an Android x86_64 emulator, package the
native host app, and materialize deterministic fixtures. Linux CI only."""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).absolute().parents[1]
ANDROID = ROOT / 'examples/android'
NDK_VERSION = '27.0.12077973'
AGP_VERSION = '8.6.1'
GRADLE_VERSION = '8.9'
COMPILE_SDK = 35
MIN_SDK = 26
MAX_FIXTURE = 33 * 1024 * 1024


def run(command, cwd=None, env=None):
    printable = ' '.join(str(value) for value in command)
    print('+', printable, flush=True)
    subprocess.run([str(value) for value in command], cwd=cwd, env=env, check=True)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def android_home():
    home = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
    if not home or not Path(home).is_dir():
        raise SystemExit('ANDROID_HOME/ANDROID_SDK_ROOT must point at the Android SDK')
    return Path(home)


def ndk_home():
    candidate = android_home() / 'ndk' / NDK_VERSION
    if candidate.is_dir():
        return candidate
    explicit = os.environ.get('ANDROID_NDK_HOME') or os.environ.get('ANDROID_NDK_ROOT')
    if explicit and Path(explicit).is_dir():
        return Path(explicit)
    installed = sorted((android_home() / 'ndk').glob('*')) if (android_home() / 'ndk').is_dir() else []
    if installed:
        return installed[-1]
    raise SystemExit('Android NDK is not installed')


def ndk_revision(ndk):
    properties = ndk / 'source.properties'
    if not properties.is_file():
        return 'unknown'
    for line in properties.read_text().splitlines():
        if line.startswith('Pkg.Revision'):
            return line.split('=', 1)[1].strip()
    return 'unknown'


def header_version(path, name):
    text = Path(path).read_text()
    match = re.search(r'#define\s+' + re.escape(name) + r'\s+"([^"]+)"', text)
    return match.group(1) if match else 'unknown'


def build_sdk(stage, build):
    cmake = shutil.which('cmake')
    if not cmake:
        raise SystemExit('cmake is required')
    ndk = ndk_home()
    configure = [cmake, '-S', ROOT, '-B', build,
                 '-DCMAKE_TOOLCHAIN_FILE=' + str(ndk / 'build/cmake/android.toolchain.cmake'),
                 '-DANDROID_ABI=x86_64', '-DANDROID_PLATFORM=android-' + str(MIN_SDK),
                 '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_INSTALL_PREFIX=' + str(stage),
                 '-DEXR_BUILD_TOOLS=OFF', '-DEXR_BUILD_TESTS=OFF', '-DEXR_BUILD_JNI=ON',
                 '-DEXR_ENABLE_LIBRARY=ON', '-DEXR_ENABLE_AUDIO=ON',
                 '-DEXR_ENABLE_PDF=ON', '-DEXR_ENABLE_PDF_EDIT=ON',
                 '-DEXR_ENABLE_PDF_CRYPTO=OFF', '-DEXR_ENABLE_AAC=OFF',
                 '-DEXR_ENABLE_TEXT_INDEX=OFF', '-DEXR_BUILD_TEXT_INDEX=OFF',
                 '-DEXR_ENABLE_IMAGE_WEBP=OFF', '-DEXR_ENABLE_IMAGE_TIFF=OFF',
                 '-DEXR_ENABLE_IMAGE_AVIF=OFF', '-DEXR_BUILD_SHARED_COMPAT=ON']
    if shutil.which('ninja'):
        configure = [configure[0], configure[1], configure[2], '-G', 'Ninja'] + configure[3:]
    run(configure)
    run([cmake, '--build', build, '--parallel', '4', '--target', 'install'])
    return ndk


def patch_android_libraries(stage):
    patchelf = shutil.which('patchelf')
    if not patchelf:
        raise SystemExit('patchelf is required to give the Android runtime a plain .so name')
    libraries = sorted((stage / 'lib').glob('libexreader.so.*.*'))
    if not libraries:
        raise SystemExit('installed SDK is missing the versioned engine runtime')
    engine = libraries[-1]
    run([patchelf, '--set-soname', 'libexreader.so', engine])
    jni = stage / 'lib/libexreader_jni.so'
    if not jni.is_file():
        raise SystemExit('installed SDK is missing libexreader_jni.so')
    run([patchelf, '--replace-needed', 'libexreader.so.1', 'libexreader.so', jni])
    target = ANDROID / 'app/src/main/jniLibs/x86_64'
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(engine, target / 'libexreader.so')
    shutil.copyfile(jni, target / 'libexreader_jni.so')
    # The imported CMake target points at the versioned file; keep its symlink
    # usable for the host JNI link step as well.
    link = stage / 'lib/libexreader.so'
    if link.is_symlink() or not link.exists():
        if link.is_symlink() or link.exists():
            link.unlink()
        shutil.copyfile(engine, link)
    return target


def epub(path, title, chapters, stored=False):
    """Deterministic EPUB 3 writer used for fixtures."""
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = []
    spine = []
    files = {}
    for index, body in enumerate(chapters, start=1):
        name = 'ch%02d.xhtml' % index
        manifest.append('<item id="c%d" href="%s" media-type="application/xhtml+xml"/>' % (index, name))
        spine.append('<itemref idref="c%d"/>' % index)
        files['OEBPS/' + name] = ('<?xml version="1.0" encoding="utf-8"?>\n'
                                  '<!DOCTYPE html>\n'
                                  '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">'
                                  '<head><title>%s</title></head><body>%s</body></html>'
                                  % (escape(title), body)).encode('utf-8')
    files['META-INF/container.xml'] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
        '</rootfiles></container>').encode('utf-8')
    files['OEBPS/nav.xhtml'] = (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
        '<head><title>Contents</title></head><body><nav epub:type="toc"><ol>'
        + ''.join('<li><a href="ch%02d.xhtml">Chapter %d</a></li>' % (i, i)
                  for i in range(1, len(chapters) + 1)) +
        '</ol></nav></body></html>').encode('utf-8')
    files['OEBPS/content.opf'] = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:identifier id="id">urn:uuid:wp13-%s</dc:identifier>'
        '<dc:title>%s</dc:title><dc:language>en</dc:language></metadata>'
        '<manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        '%s</manifest><spine>%s</spine></package>'
        % (hashlib.sha256(title.encode()).hexdigest()[:16], escape(title),
           ''.join(manifest), ''.join(spine))).encode('utf-8')
    with zipfile.ZipFile(path, 'w') as archive:
        info = zipfile.ZipInfo('mimetype', date_time=(2026, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, b'application/epub+zip')
        for name, data in files.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)


def escape(value):
    return (value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def stream_text(size, seed):
    """Deterministic low-compressibility ASCII text."""
    chunk = hashlib.sha256(seed.encode()).digest()
    alphabet = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 '
    parts = []
    produced = 0
    counter = 0
    while produced < size:
        counter += 1
        chunk = hashlib.sha256(chunk + str(counter).encode()).digest()
        text = ''.join(alphabet[byte % len(alphabet)] for byte in chunk)
        parts.append(text)
        produced += len(text)
    return ''.join(parts)[:size]


def write_fixtures(folder):
    folder.mkdir(parents=True, exist_ok=True)
    sample = [
        '<h1>EXReader Android host sample</h1>'
        '<p>EXReader Android host sample. The quick brown fox jumps over the lazy dog.</p>'
        '<p>Touch, select and annotate this paragraph on an emulator. The host keeps the '
        'document, pager and bitmap lifetimes separate.</p>'
        '<p>字体回退：这一段中文使用 Noto Sans CJK 渲染。书页翻动后位置应保持稳定。</p>'
        '<p>Second page content for reflow navigation. Each paragraph is real engine text.</p>'
        '<p>Third page content. Annotations are stored in the SDK SQLite library.</p>',
        '<h1>Chapter two</h1><p>Chapter two keeps the sampler long enough for three pages. '
        'A quick brown fox appears again for selection tests.</p>',
        '<h1>Chapter three</h1><p>Chapter three closes the sample.</p>'
    ]
    epub(folder / 'Sample.epub', 'EXReader Android Sample', sample)
    epub(folder / 'Second.epub', 'Second Sample', [
        '<h1>Second sample</h1><p>Second sample book. This is the second title in the shelf.</p>',
        '<h1>Second chapter</h1><p>Another paragraph for navigation.</p>'
    ])
    big = []
    block = ('Lorem ipsum dolor sit amet, consectetur adipiscing elit. ' * 18)
    for index in range(2000):
        big.append('<p>%s Paragraph %d.</p>' % (block, index))
    epub(folder / 'BigChapter.epub', 'Big Chapter Sample', ['<h1>Big chapter</h1>' + ''.join(big)])
    epub(folder / 'Ambiguous.epub', 'Ambiguous Sample',
         ['<h1>Repeated</h1><p>' + ('spam ' * 2000) + '</p>'])
    (folder / 'Sample.txt').write_text(
        'EXReader plain text sample.\n\n'
        'The text host reads UTF-8 paragraphs and paginates them with the same engine.\n\n'
        'A second paragraph keeps the page navigation meaningful.\n', encoding='utf-8')
    broken = b'PK\x03\x04' + bytes(range(256)) * 16
    (folder / 'Broken.epub').write_bytes(broken)
    pdf = ROOT / 'tests/fixtures/pdf-public.pdf'
    if not pdf.is_file():
        raise SystemExit('missing tests/fixtures/pdf-public.pdf')
    shutil.copyfile(pdf, folder / 'Sample.pdf')
    large = ('<h1>Large</h1><p>' + stream_text(30 * 1024 * 1024, 'large') + '</p>')
    epub(folder / 'Large.epub', 'Large Import', [large], stored=True)
    too_large = ('<h1>Too large</h1><p>' + stream_text(33 * 1024 * 1024, 'too-large') + '</p>')
    epub(folder / 'TooLarge.epub', 'Too Large Import', [too_large], stored=True)
    manifest = {}
    for path in sorted(folder.iterdir()):
        if path.is_file():
            manifest[path.name] = {'size': path.stat().st_size, 'sha256': sha256(path)}
    (folder / 'fixtures.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def elf_check(path):
    data = Path(path).read_bytes()
    if data[:4] != b'\x7fELF' or data[4] != 2 or data[5] != 1:
        raise SystemExit('not a 64-bit little-endian ELF: ' + str(path))
    machine = struct.unpack_from('<H', data, 18)[0]
    if machine != 62:
        raise SystemExit('expected x86_64 ELF, machine=%d: %s' % (machine, path))
    phoff = struct.unpack_from('<Q', data, 32)[0]
    phentsize = struct.unpack_from('<H', data, 54)[0]
    phnum = struct.unpack_from('<H', data, 56)[0]
    alignments = []
    for index in range(phnum):
        offset = phoff + index * phentsize
        p_type = struct.unpack_from('<I', data, offset)[0]
        if p_type == 1:
            alignments.append(struct.unpack_from('<Q', data, offset + 48)[0])
    if not alignments or min(alignments) < 16384:
        raise SystemExit('ELF LOAD alignment is below 16 KiB: ' + str(path))
    return {'machine': machine, 'load_alignments': sorted(set(alignments))}


def inspect_apk(apk):
    info = {}
    with zipfile.ZipFile(apk) as archive:
        names = [name for name in archive.namelist() if name.startswith('lib/')]
        for required in ['lib/x86_64/libexreader.so', 'lib/x86_64/libexreader_jni.so']:
            if required not in names:
                raise SystemExit('APK is missing ' + required)
        if any(name.endswith('libexreader.so.1') for name in names):
            raise SystemExit('APK still contains the versioned engine name')
        for name in ['lib/x86_64/libexreader.so', 'lib/x86_64/libexreader_jni.so',
                     'lib/x86_64/libexreader_host.so']:
            if name not in names:
                raise SystemExit('APK is missing ' + name)
            payload = archive.read(name)
            if b'libexreader.so.1' in payload:
                raise SystemExit(name + ' still references the versioned engine name')
            target = Path('/tmp') / Path(name).name
            target.write_bytes(payload)
            info[name] = elf_check(target)
    return info


def gradle_build(stage, gradle):
    sdk = android_home()
    local = ANDROID / 'local.properties'
    local.write_text('sdk.dir=%s\n' % str(sdk).replace('\\', '\\\\'))
    command = [gradle, '-p', ANDROID, '--no-daemon', '--stacktrace',
               ':app:assembleDebug', ':uitest:assembleDebug', ':uitest:assembleDebugAndroidTest',
               '-PexrSdk=' + str(stage)]
    env = dict(os.environ)
    env.setdefault('ANDROID_HOME', str(sdk))
    env.setdefault('ANDROID_SDK_ROOT', str(sdk))
    run(command, env=env)
    version = 'unknown'
    try:
        output = subprocess.check_output([gradle, '--version'], text=True, env=env)
        match = re.search(r'Gradle\s+([0-9.]+)', output)
        if match:
            version = match.group(1)
    except Exception:
        pass
    return version


def collect_artifacts(build):
    artifacts = build / 'artifacts'
    artifacts.mkdir(parents=True, exist_ok=True)
    sources = {
        'app-debug.apk': ANDROID / 'app/build/outputs/apk/debug/app-debug.apk',
        'uitest-debug.apk': ANDROID / 'uitest/build/outputs/apk/debug/uitest-debug.apk',
        'uitest-debug-androidTest.apk': ANDROID / 'uitest/build/outputs/apk/androidTest/debug/uitest-debug-androidTest.apk',
    }
    result = {}
    for name, source in sources.items():
        if not source.is_file():
            raise SystemExit('missing Gradle output: ' + str(source))
        target = artifacts / name
        shutil.copyfile(source, target)
        result[name] = {'path': str(target), 'size': target.stat().st_size, 'sha256': sha256(target)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, default=ROOT / 'stage/android-x86_64')
    parser.add_argument('--sdk-build', type=Path, default=ROOT / 'build/android-sdk')
    parser.add_argument('--build-dir', type=Path, default=ROOT / 'build/android-host')
    parser.add_argument('--gradle', default=shutil.which('gradle') or 'gradle')
    parser.add_argument('--skip-sdk', action='store_true')
    parser.add_argument('--skip-gradle', action='store_true')
    args = parser.parse_args()
    if platform.system() != 'Linux':
        raise SystemExit('Android host builds run in Linux CI only')
    stage = args.stage.absolute()
    build = args.build_dir.absolute()
    build.mkdir(parents=True, exist_ok=True)
    if not args.skip_sdk:
        build_sdk(stage, args.sdk_build.absolute())
    if not (stage / 'lib/libexreader_jni.so').is_file():
        raise SystemExit('the installed SDK is incomplete: ' + str(stage))
    patch_android_libraries(stage)

    sys.path.insert(0, str(ROOT / 'tools'))
    from host_font import fetch as fetch_font
    font = fetch(ROOT / 'build/host-font-cache')
    assets = ANDROID / 'app/src/main/assets'
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(font / 'Reader.otf', assets / 'Reader.otf')
    shutil.copyfile(font / 'OFL.txt', assets / 'OFL.txt')

    fixtures = build / 'fixtures'
    manifest = write_fixtures(fixtures)

    gradle_version = GRADLE_VERSION
    if not args.skip_gradle:
        gradle_version = gradle_build(stage, args.gradle)
    artifacts = collect_artifacts(build)

    source_sha = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    branch = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', '--abbrev-ref', 'HEAD'], text=True).strip()
    ndk = ndk_home()
    identity = {
        'schema': 1,
        'source_sha': source_sha,
        'branch': branch,
        'sdk_version': header_version(stage / 'include/exr/base.h', 'EXR_VERSION'),
        'core_version': header_version(stage / 'include/exr/base.h', 'EXR_CORE_VERSION'),
        'library_version': header_version(stage / 'include/exr/library.h', 'EXR_LIBRARY_VERSION'),
        'abi_version': 1,
        'library_schema': 6,
        'abi': 'x86_64',
        'android_platform': 'android-' + str(MIN_SDK),
        'compile_sdk': COMPILE_SDK,
        'min_sdk': MIN_SDK,
        'target_sdk': COMPILE_SDK,
        'ndk': ndk_revision(ndk),
        'cmake': subprocess.check_output(['cmake', '--version'], text=True).splitlines()[0].replace('cmake version ', ''),
        'agp': AGP_VERSION,
        'gradle': gradle_version,
        'font': {'name': 'NotoSansCJKsc-Regular.otf', 'sha256': sha256(font / 'Reader.otf')},
        'fixtures': manifest,
        'artifacts': artifacts,
        'native': inspect_apk(Path(artifacts['app-debug.apk']['path'])),
    }
    (build / 'build.json').write_text(json.dumps(identity, indent=2) + '\n')
    print(json.dumps({'build_dir': str(build), 'apk': artifacts['app-debug.apk']}, indent=2))


if __name__ == '__main__':
    main()
