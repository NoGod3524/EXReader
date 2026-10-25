"""Actions-only source compilation before installed-host runtime acceptance."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]


def main():
    if os.environ.get('GITHUB_ACTIONS')!='true' or sys.platform!='win32':
        raise RuntimeError('Windows Actions only')
    out=ROOT/'build/windows-raw3-metadata/host-syntax'
    out.mkdir(parents=True,exist_ok=False)
    includes=[ROOT/'include',ROOT/'apps/reader/desktop',ROOT/'apps/reader/store/native']
    includes += [ROOT/'apps/reader'/module/'include' for module in (
        'desktop-metadata','revisions','commands','reading-state','reading-commands','annotation-view','sync','session')]
    includes += [ROOT/'extras'/module/'include' for module in ('credentials','sideload')]
    results=[]
    for raw in (False,True):
        name='raw' if raw else 'legacy'
        flags=['cl.exe','/nologo','/utf-8','/W3','/DEXR_STATIC=1']+['/I'+str(path) for path in includes]
        if raw:
            flags+=['/DEXR_READER_WINDOWS_RAW3=1','/DEXR_READER_SELECTOR_BYTES_CANDIDATE=1','/DEXR_READER_METADATA_RAW3=1']
        for source,language,extra in (
            ('apps/reader/desktop/windows_records_owner.cpp','/std:c++17',['/EHsc']),
            ('examples/reader.c','/std:c11',['/DEXR_READER_PRODUCT_CATALOG=1','/DEXR_READER_DESKTOP_METADATA=1',
              '/DEXR_READER_WINDOWS_ACCOUNT=1','/DEXR_READER_WINDOWS_RECORDS=1',
              '/DEXR_READER_WINDOWS_PRODUCT_HEADER="'+(ROOT/'apps/reader/desktop/windows_catalog.inc').as_posix()+'"'])):
            tag=name+'-'+Path(source).stem
            obj=out/(tag+'.obj')
            proc=subprocess.run(flags+[language,*extra,'/c',str(ROOT/source),'/Fo'+str(obj)],cwd=ROOT,
                                capture_output=True,encoding='utf-8',errors='replace',timeout=180)
            log=proc.stdout+proc.stderr
            (out/(tag+'.log')).write_text(log,encoding='utf-8')
            if proc.returncode:
                print(log,flush=True)
                raise RuntimeError(tag+' source compilation failed')
            results.append(dict(profile=name,source=source,object_sha256=hashlib.sha256(obj.read_bytes()).hexdigest()))
    report=dict(source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                compiled=results,source_compile_passed=True,host_raw3_accepted=False,
                scope='public source headers and actual Win32 translation units; no link, install or runtime grant')
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    main()
