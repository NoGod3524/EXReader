"""Authenticate the Windows/raw-module composition; grants no runtime result."""
import json
import os
from pathlib import Path
import subprocess
import re

ROOT = Path(__file__).resolve().parents[2]
COMPOSED = '3561c9a9a2c1d209c66931c080e5f0267d0fe653'
WINDOWS = 'f355525b74ae261db536c56200e46643919ef323'
RAW = '56793e7c'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
CODEC = '5eb0ea09c53e37a371be558d52ec9c958aed80fc'
MODULES = ('revisions','reading-state','reading-commands','annotation-view','commands','sync','session')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, encoding='utf-8').strip()


def legacy_cpp(text):
    frames=[];result=[]
    def visible():return all(not raw or active for raw,active in frames)
    for line in text.splitlines(keepends=True):
        stripped=line.lstrip()
        if re.match(r'#\s*(?:if|ifdef|ifndef)\b',stripped):
            raw=bool(re.fullmatch(r'#ifdef EXR_READER_WINDOWS_RAW3\s*',stripped))
            if not raw and visible():result.append(line)
            frames.append((raw,not raw))
        elif re.match(r'#\s*else\b',stripped):
            if not frames:raise RuntimeError('Unmatched else')
            raw,active=frames[-1]
            if raw:frames[-1]=(raw,not active)
            elif visible():result.append(line)
        elif re.match(r'#\s*endif\b',stripped):
            if not frames:raise RuntimeError('Unmatched endif')
            raw,_=frames[-1]
            if not raw and visible():result.append(line)
            frames.pop()
        elif visible():result.append(line)
    if frames:raise RuntimeError('Unterminated conditional')
    return ''.join(result)


def legacy_cmake(text):
    result=[];depth=0
    for line in text.splitlines(keepends=True):
        stripped=line.strip()
        if depth:
            if stripped.startswith('if('):depth+=1
            elif stripped.startswith('endif('):depth-=1
            continue
        if stripped.startswith('if(EXR_READER_WINDOWS_RAW3'):
            depth=1;continue
        if stripped.startswith('option(EXR_READER_WINDOWS_RAW3 ') or stripped=='set(EXR_WINDOWS_PRODUCT_VERSION 0.1.0)':continue
        result.append(line)
    if depth:raise RuntimeError('Unterminated raw CMake profile')
    value=''.join(result).replace('find_package(EXReaderDesktopMetadata ${EXR_WINDOWS_PRODUCT_VERSION} EXACT CONFIG REQUIRED)',
                                'find_package(EXReaderDesktopMetadata CONFIG REQUIRED)')
    return value.replace('${EXR_WINDOWS_PRODUCT_VERSION}','0.1.0')


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Actions only')
    if git('rev-parse','HEAD') != os.environ['GITHUB_SHA']:
        raise RuntimeError('Checkout differs')
    for source in (COMPOSED,WINDOWS,RAW,CODEC):
        subprocess.run(['git','merge-base','--is-ancestor',source,'HEAD'], cwd=ROOT, check=True)
    owned = {'.github/workflows/reader-windows-raw3-original-full.yml','.github/workflows/reader-windows-raw3-preflight.yml','.github/workflows/reader-windows-raw3-host.yml','.github/workflows/reader-windows-raw3-authenticate.yml','docs/READER-WINDOWS-RAW3.md',
             'apps/reader/desktop-metadata/CMakeLists.txt','apps/reader/desktop-metadata/EXReaderDesktopMetadataConfig.cmake.in',
             'apps/reader/desktop-metadata/include/reader_metadata.h','apps/reader/desktop-metadata/src/metadata.cpp',
             'examples/reader.c','apps/reader/windows-account/CMakeLists.txt',
             'apps/reader/desktop/windows_records.inc','apps/reader/desktop/windows_records_owner.cpp',
             'apps/reader/desktop/windows_raw3_apis.h','apps/reader/desktop/reading_capture_bytes.h',
             '.github/workflows/reader-private-capture.yml','docs/READER-PRIVATE-CAPTURE.md',
             'docs/validation/reader-private-capture.json'}
    owned.update('apps/reader/bulk-organization/'+path for path in (
        'CMakeLists.txt','EXReaderBulkOrganizationConfig.cmake.in','include/reader_bulk.h','src/bulk.cpp'))
    changed = git('diff','--name-only',COMPOSED,'HEAD').splitlines()
    if not all(p in owned or p.startswith(('tests/reader_windows_raw3/','tests/reader_private_capture/')) for p in changed):
        raise RuntimeError('Changed path outside metadata candidate and source composition')
    for module in MODULES:
        path = 'apps/reader/' + module
        if git('rev-parse','HEAD:'+path) != git('rev-parse',RAW+':'+path):
            raise RuntimeError('Raw module source differs: '+module)
    for path in ('apps/reader/desktop/reading_capture_bytes.h','tests/reader_private_capture'):
        if git('rev-parse','HEAD:'+path)!=git('rev-parse',CODEC+':'+path):
            raise RuntimeError('Tested private codec changed: '+path)
    for path in ('examples/reader.c','apps/reader/desktop/windows_records.inc','apps/reader/desktop/windows_records_owner.cpp'):
        original=subprocess.check_output(['git','show',WINDOWS+':'+path],cwd=ROOT,text=True,encoding='utf-8')
        if legacy_cpp((ROOT/path).read_text(encoding='utf-8'))!=original:
            raise RuntimeError('Default-OFF source changed: '+path)
    path='apps/reader/windows-account/CMakeLists.txt'
    if legacy_cmake((ROOT/path).read_text(encoding='utf-8'))!=subprocess.check_output(['git','show',WINDOWS+':'+path],cwd=ROOT,text=True,encoding='utf-8'):
        raise RuntimeError('Default-OFF CMake profile changed')
    subprocess.run(['git','diff','--exit-code',WINDOWS,'HEAD','--','tests/reader_windows_compact',
                    'apps/reader/desktop/windows_compact_ui.inc','tests/reader_windows_records'],cwd=ROOT,check=True)
    subprocess.run(['git','diff','--exit-code',SDK,'HEAD','--','src','include','cmake',
                    'CMakeLists.txt','bindings','tests/fixtures'],cwd=ROOT,check=True)
    out = ROOT/'build/windows-raw3-preflight'
    out.mkdir(parents=True,exist_ok=True)
    report = dict(source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'],composition_source=COMPOSED,
                  windows_baseline=WINDOWS,raw_modules=git('rev-parse',RAW),sdk_source=SDK,
                  source_preflight_passed=True,legacy_source_projection_exact=True,host_raw3_accepted=False,accepted=False,
                  scope='source composition only; no Windows compilation, runtime or interchange grant')
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__ == '__main__':
    main()
