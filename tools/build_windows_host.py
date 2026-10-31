#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Package and check the Windows native reference host."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

from host_font import fetch as host_font
from run_benchmarks import make_epub

ROOT = Path(__file__).absolute().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_positive_epub(path):
    """Unique short paragraph identifiers keep navigation positive cases unambiguous.

    The original make_epub output remains Sample.epub for the unchanged self-test
    and a separate repeated-quote refusal regression.
    """
    container = ('<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
                 '<rootfiles><rootfile full-path="OPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
    package = ('<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
               '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">urn:exreader:windows-positive</dc:identifier>'
               '<dc:title>EXReader benchmark</dc:title></metadata><manifest>'+
               ''.join('<item id="c%d" href="c%d.xhtml" media-type="application/xhtml+xml"/>' % (i, i) for i in range(3))+
               '</manifest><spine>'+''.join('<itemref idref="c%d"/>' % i for i in range(3))+'</spine></package>')
    entries = [('mimetype', 'application/epub+zip'), ('META-INF/container.xml', container), ('OPS/package.opf', package)]
    for part in range(3):
        body = ''.join('<p>Reading [%d-%04d-a] native pages [%d-%04d-b] preserve words [%d-%04d-c] '
                       'and positions [%d-%04d-d].</p>' % (part, row, part, row, part, row, part, row) for row in range(160))
        entries.append(('OPS/c%d.xhtml' % part,
                        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Positive</title></head><body>'+body+'</body></html>'))
    with zipfile.ZipFile(path, 'w') as archive:
        for name, content in entries:
            entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_STORED if name == 'mimetype' else zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--c02-prefix', type=Path, required=True, help='Installed admission and exact migration commands')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--static-reading', action='store_true', help='Package the installed lightweight static reading consumer')
    args = parser.parse_args()
    sdk, binary, output = args.sdk.absolute(), args.binary.absolute(), args.output.absolute()
    if output.exists():
        parser.error('Choose a new host evidence directory')
    payload = output/'EXReader'
    payload.mkdir(parents=True)
    shutil.copyfile(binary, payload/'EXReader.exe')
    c02 = args.c02_prefix.resolve()
    for name in ('exreader-c02-admission.exe', 'exreader-c02-migrate.exe'):
        shutil.copyfile(c02/'bin'/name, payload/name)
    (payload/'LIBRARY-ADMISSION.txt').write_text(
        'Create a new private library explicitly:\n'
        '  exreader-c02-admission.exe create LIBRARY NEW_PRIVATE_DOMAIN_DIRECTORY\n'
        'Verify an existing library explicitly:\n'
        '  exreader-c02-admission.exe enroll LIBRARY NEW_PRIVATE_DOMAIN_DIRECTORY\n'
        'Check registration: exreader-c02-admission.exe check LIBRARY\n'
        'Open: EXReader.exe --library LIBRARY --data PRIVATE_PROFILE_DIRECTORY\n'
        'Import a legacy pack: exreader-c02-migrate.exe migrate LIBRARY PACK\n'
        'Recover an interrupted import: exreader-c02-migrate.exe recover LIBRARY\n'
        'Keep the original package and recovery evidence for that transaction.\n', encoding='utf-8')
    runtimes = [sdk/'bin'/name for name in ('exreader.dll', 'libexreader.dll') if (sdk/'bin'/name).is_file()]
    if args.static_reading:
        if runtimes:
            parser.error('Static reading stage must not include the shared compatibility SDK')
    else:
        if len(runtimes) != 1:
            parser.error('Expected exactly one installed SDK runtime')
        shutil.copyfile(runtimes[0], payload/runtimes[0].name)
    font = host_font(ROOT/'build/host-font-cache')
    for name in ('Reader.otf', 'OFL.txt'):
        shutil.copyfile(font/name, payload/name)
    shutil.copyfile(ROOT/'LICENSE', payload/'LICENSE.txt')
    shutil.copyfile(ROOT/'THIRD_PARTY_NOTICES.md', payload/'THIRD_PARTY_NOTICES.md')
    shutil.copytree(sdk/'share/exreader/licenses', payload/'licenses')
    make_epub(payload/'Sample.epub', 3, 16384, single_paragraph=True)
    make_positive_epub(payload/'Sample-positive.epub')
    shutil.copyfile(ROOT/'tests/fixtures/pdf-public.pdf', payload/'Sample.pdf')
    shutil.copyfile(ROOT/'tests/fixtures/pdf-public-text.pdf', payload/'Sample-Text.pdf')
    report, image = output/'report.json', output/'page.png'
    with (output/'application.log').open('wb') as log:
        result = subprocess.run([str(payload/'EXReader.exe'), '--self-test',
                                 str(payload/'Reader.otf'), str(payload/'Sample.epub'), str(payload/'Sample.pdf'),
                                 str(report), str(image)], stdout=log, stderr=subprocess.STDOUT, timeout=120,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode != 0 or not report.exists():
        raise RuntimeError('Windows reference host self-check failed; see '+str(output/'application.log'))
    checked = json.loads(report.read_text())
    expected = re.search(r'#define EXR_VERSION "([^"]+)"', (sdk/'include/exr/base.h').read_text())[1]
    if checked.get('passed') is not True or checked.get('checks', 0) < 26 or checked.get('engine_version') != expected:
        raise RuntimeError('Invalid Windows host report')
    source_sha = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    version = subprocess.check_output([str(payload/'exreader-c02-migrate.exe'), '--version'], text=True).strip()
    if not re.fullmatch('exreader-c02-migrate '+source_sha+r' provider=[0-9a-f]{64} SDK=3\.42\.0', version):
        raise RuntimeError('Packaged migration command is not the exact source/SDK provider')
    profile = output/'admission-check'
    profile.mkdir()
    library, authority = profile/'library.sqlite', profile/'native-domain'
    observations = []
    for command in (['create', str(library), str(authority)], ['check', str(library)]):
        result = subprocess.run([str(payload/'exreader-c02-admission.exe'), *command],
            capture_output=True, text=True, timeout=45)
        observations.append(dict(command=command, exit=result.returncode, stdout=result.stdout, stderr=result.stderr))
        (output/'admission-check.json').write_text(json.dumps(observations, indent=2)+'\n')
        if result.returncode or json.loads(result.stdout).get('admitted') is not True:
            raise RuntimeError('Packaged explicit admission failed')
    manifest = {'schema': 1, 'passed': True, 'source_sha': source_sha, 'sdk_version': expected,
                'c02_admission': True, 'migration_version': version,
                'selftest_checks': checked['checks'],
                'files': {str(p.relative_to(payload)).replace('\\', '/'): digest(p)
                          for p in sorted(payload.rglob('*')) if p.is_file()},
                'report_sha256': digest(report), 'image_sha256': digest(image)}
    if args.static_reading:
        manifest['linkage'] = 'static-reading'
    (output/'build.json').write_text(json.dumps(manifest, indent=2)+'\n')
    shutil.make_archive(str(output/'EXReader-Windows'), 'zip', root_dir=payload)
    print(str(checked['checks'])+' Windows native host checks passed')


if __name__ == '__main__':
    main()
