"""Authenticate the Windows/raw-module composition; grants no runtime result."""
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
COMPOSED = '3561c9a9a2c1d209c66931c080e5f0267d0fe653'
WINDOWS = 'f355525b74ae261db536c56200e46643919ef323'
RAW = '56793e7c'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
MODULES = ('revisions','reading-state','reading-commands','annotation-view','commands','sync','session')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Actions only')
    if git('rev-parse','HEAD') != os.environ['GITHUB_SHA']:
        raise RuntimeError('Checkout differs')
    for source in (COMPOSED,WINDOWS,RAW):
        subprocess.run(['git','merge-base','--is-ancestor',source,'HEAD'], cwd=ROOT, check=True)
    owned = {'.github/workflows/reader-windows-raw3-preflight.yml','docs/READER-WINDOWS-RAW3.md',
             'apps/reader/desktop-metadata/CMakeLists.txt','apps/reader/desktop-metadata/EXReaderDesktopMetadataConfig.cmake.in',
             'apps/reader/desktop-metadata/include/reader_metadata.h','apps/reader/desktop-metadata/src/metadata.cpp'}
    changed = git('diff','--name-only',COMPOSED,'HEAD').splitlines()
    if not all(p in owned or p.startswith('tests/reader_windows_raw3/') for p in changed):
        raise RuntimeError('Changed path outside metadata candidate and source composition')
    for module in MODULES:
        path = 'apps/reader/' + module
        if git('rev-parse','HEAD:'+path) != git('rev-parse',RAW+':'+path):
            raise RuntimeError('Raw module source differs: '+module)
    subprocess.run(['git','diff','--exit-code',WINDOWS,'HEAD','--','examples/reader.c',
                    'apps/reader/desktop','apps/reader/windows-account','tests/reader_windows_compact'],cwd=ROOT,check=True)
    subprocess.run(['git','diff','--exit-code',SDK,'HEAD','--','src','include','cmake',
                    'CMakeLists.txt','bindings','tests/fixtures'],cwd=ROOT,check=True)
    out = ROOT/'build/windows-raw3-preflight'
    out.mkdir(parents=True,exist_ok=True)
    report = dict(source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'],composition_source=COMPOSED,
                  windows_baseline=WINDOWS,raw_modules=git('rev-parse',RAW),sdk_source=SDK,
                  source_preflight_passed=True,host_raw3_implemented=False,accepted=False,
                  scope='source composition only; no Windows compilation, runtime or interchange grant')
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)


if __name__ == '__main__':
    main()
