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

from host_font import fetch as host_font
from run_benchmarks import make_epub

ROOT = Path(__file__).absolute().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sdk, binary, output = args.sdk.absolute(), args.binary.absolute(), args.output.absolute()
    if output.exists():
        parser.error('Choose a new host evidence directory')
    payload = output/'EXReader'
    payload.mkdir(parents=True)
    shutil.copyfile(binary, payload/'EXReader.exe')
    runtimes = [sdk/'bin'/name for name in ('exreader.dll', 'libexreader.dll') if (sdk/'bin'/name).is_file()]
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
    manifest = {'schema': 1, 'passed': True, 'source_sha': source_sha, 'sdk_version': expected,
                'selftest_checks': checked['checks'],
                'files': {str(p.relative_to(payload)).replace('\\', '/'): digest(p)
                          for p in sorted(payload.rglob('*')) if p.is_file()},
                'report_sha256': digest(report), 'image_sha256': digest(image)}
    (output/'build.json').write_text(json.dumps(manifest, indent=2)+'\n')
    shutil.make_archive(str(output/'EXReader-Windows'), 'zip', root_dir=payload)
    print(str(checked['checks'])+' Windows native host checks passed')


if __name__ == '__main__':
    main()
