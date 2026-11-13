#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build the native Apple reference host against an installed EXReader SDK."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import zipfile
from host_font import fetch as host_font
from run_benchmarks import make_epub

ROOT = Path(__file__).absolute().parents[1]


def run(*command):
    subprocess.run([str(x) for x in command], check=True)


def make_navigation_books(resources):
    """Exercise chapter boundaries through the real Apple host, including failures."""
    def html(text):
        return '<html xmlns="http://www.w3.org/1999/xhtml"><body>'+text+'</body></html>'

    first = html('<p>First reading chapter.</p>'+('<p>'+('Navigation regression words. '*10)+'</p>')*8+
                 '<p>FINAL FIRST CHAPTER</p>')
    for name, broken in [('Navigation.epub', False), ('BrokenChapter.epub', True)]:
        with zipfile.ZipFile(resources/name, 'w', zipfile.ZIP_DEFLATED) as book:
            book.writestr('mimetype', 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
            book.writestr('META-INF/container.xml', '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
            book.writestr('book.opf', '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">'+name+'</dc:identifier><dc:title>Navigation regression</dc:title><dc:language>en</dc:language></metadata><manifest><item id="first" href="first.xhtml" media-type="application/xhtml+xml"/><item id="optional" href="optional.xhtml" media-type="application/xhtml+xml"/><item id="second" href="second.xhtml" media-type="application/xhtml+xml"/><item id="auxiliary" href="auxiliary.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="first"/><itemref idref="optional" linear="no"/><itemref idref="second"/></spine></package>')
            book.writestr('first.xhtml', html('<p>SAFE BEFORE BROKEN CHAPTER</p>') if broken else first)
            book.writestr('optional.xhtml', html('<p>SKIPPED NONLINEAR</p>'))
            book.writestr('second.xhtml', '<html><body><p>broken' if broken else html('<p>SECOND READING CHAPTER</p>'))
            book.writestr('auxiliary.xhtml', html('<p>SKIPPED AUXILIARY</p>'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--platform', choices=['macos', 'simulator', 'iphoneos'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.error('The Apple SDK build requires a macOS host')
    sdk, output = args.sdk.absolute(), args.output.absolute()
    if output.exists():
        parser.error('Choose a new output directory to preserve earlier artifacts')
    for path in [sdk/'include/exreader.h', sdk/'lib', ROOT/'examples/apple/ReaderApp.swift']:
        if not path.exists():
            parser.error('Missing SDK or host source: '+str(path))
    output.mkdir(parents=True)
    app = output/'EXReader.app'
    mobile = args.platform != 'macos'
    executable = app/'EXReader' if mobile else app/'Contents/MacOS/EXReader'
    resources = app if mobile else app/'Contents/Resources'
    frameworks = app/'Frameworks' if mobile else app/'Contents/Frameworks'
    for folder in [executable.parent, resources, frameworks]:
        folder.mkdir(parents=True, exist_ok=True)
    native_sdk = {'macos': 'macosx', 'simulator': 'iphonesimulator', 'iphoneos': 'iphoneos'}[args.platform]
    sdk_path = subprocess.check_output(['xcrun', '--sdk', native_sdk, '--show-sdk-path'], text=True).strip()
    architecture = 'arm64' if mobile else subprocess.check_output(['uname', '-m'], text=True).strip()
    target = architecture+('-apple-macosx12.0' if not mobile else '-apple-ios15.0'+('-simulator' if args.platform == 'simulator' else ''))
    rpath = '@executable_path/Frameworks' if mobile else '@executable_path/../Frameworks'
    command = ['xcrun', '--sdk', native_sdk, 'swiftc', '-swift-version', '5', '-O',
               '-sdk', sdk_path, '-target', target, '-I', sdk/'include', '-L', sdk/'lib',
               '-lexreader', '-Xlinker', '-rpath', '-Xlinker', rpath,
               ROOT/'bindings/swift/EXReader.swift', ROOT/'examples/apple/ReaderApp.swift',
               '-o', executable]
    run(*command)
    source_sha = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    version = re.search(r'#define EXR_VERSION "([^"]+)"', (sdk/'include/exr/base.h').read_text())[1]
    info = {'CFBundleExecutable': 'EXReader', 'CFBundleIdentifier': 'org.exreader.host',
            'CFBundleName': 'EXReader', 'CFBundleDisplayName': 'EXReader',
            'CFBundlePackageType': 'APPL', 'CFBundleVersion': '1',
            'CFBundleShortVersionString': version, 'EXRSourceSHA': source_sha}
    if mobile:
        info.update({'MinimumOSVersion': '15.0', 'LSRequiresIPhoneOS': True,
                     'UIApplicationSceneManifest': {'UIApplicationSupportsMultipleScenes': True},
                     'CFBundleSupportedPlatforms': ['iPhoneSimulator' if args.platform == 'simulator' else 'iPhoneOS'],
                     'UIDeviceFamily': [1, 2], 'UILaunchScreen': {}, 'UIFileSharingEnabled': True,
                     'LSSupportsOpeningDocumentsInPlace': True,
                     'UISupportedInterfaceOrientations': ['UIInterfaceOrientationPortrait',
                         'UIInterfaceOrientationLandscapeLeft', 'UIInterfaceOrientationLandscapeRight'],
                     'UISupportedInterfaceOrientations~ipad': ['UIInterfaceOrientationPortrait',
                         'UIInterfaceOrientationPortraitUpsideDown', 'UIInterfaceOrientationLandscapeLeft',
                         'UIInterfaceOrientationLandscapeRight']})
    else:
        info.update({'LSMinimumSystemVersion': '12.0', 'NSHighResolutionCapable': True})
    with (app/'Info.plist' if mobile else app/'Contents/Info.plist').open('wb') as stream:
        plistlib.dump(info, stream)
    for name, source in [('Sample.pdf', 'pdf-public.pdf')]:
        shutil.copyfile(ROOT/'tests/fixtures'/source, resources/name)
    make_epub(resources/'Sample.epub', 3, 16384, single_paragraph=True)
    make_navigation_books(resources)
    font = host_font(ROOT/'build/host-font-cache')
    shutil.copyfile(font/'Reader.otf', resources/'Reader.otf')
    shutil.copyfile(font/'OFL.txt', resources/'Noto-OFL.txt')
    shutil.copyfile(ROOT/'LICENSE', resources/'EXReader-LICENSE.txt')
    shutil.copyfile(ROOT/'THIRD_PARTY_NOTICES.md', resources/'THIRD_PARTY_NOTICES.md')
    shutil.copytree(sdk/'share/exreader/licenses', resources/'licenses')
    libraries = list((sdk/'lib').glob('libexreader*.dylib'))
    if not libraries:
        parser.error('Installed SDK is missing its shared runtime')
    # Keep versioned runtime names required by the linker's install name.
    for library in libraries:
        shutil.copyfile(library, frameworks/library.name)
        run('codesign', '--force', '--sign', '-', frameworks/library.name)
    run('codesign', '--force', '--deep', '--sign', '-', app)
    manifest = {'schema': 1, 'source_sha': source_sha, 'sdk_version': version,
                'platform': args.platform, 'target': target, 'bundle': str(app),
                'signing': 'ad-hoc; device installation requires the owner signing identity',
                'files': {str(p.relative_to(app)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted(app.rglob('*')) if p.is_file()}}
    (output/'build.json').write_text(json.dumps(manifest, indent=2)+'\n')
    if args.platform == 'iphoneos':
        payload = output/'Payload'
        payload.mkdir()
        shutil.copytree(app, payload/'EXReader.app')
        archive = shutil.make_archive(str(output/'EXReader-iOS-unsigned'), 'zip', root_dir=output, base_dir='Payload')
        Path(archive).rename(output/'EXReader-iOS-unsigned.ipa')
    print('Built '+str(app))


if __name__ == '__main__':
    main()
