#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only native owner/provider evidence, with unchanged 112/87 exits."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

NAMES={'actualInstalledProviderAndJson','persistedNativeCreateIds','strictUtf16AndEmoji',
       'staleObservedHeadsAreAtomic','explicitDeleteAndRestore','metadataFailureRollsBackAndRetries',
       'outboxFailureRollsBackAndRetries','membershipNeedsExplicitBookBootstrap','publicSdkBootstrapKeepsCurrentProductTitle',
       'shelfAndSeriesMembershipOrder','missingAndDeletedDependenciesRefused','mapFailureKeepsSdkAndCommittedBookCommand',
       'nativeRejectsWrongOwner','nativeRejectsClosedHandle','twoNativeOwnersCompeteOnOneObservedHead',
       'sdkDatabaseRefusedWithoutModification','opensClosedLegacySystemCatalog'}


def require(value,message):
    if not value:raise ValueError(message)


def identity():
    require(os.environ.get('GITHUB_ACTIONS')=='true','Actions execution required')
    return {'source_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT']}


def digest(path):
    raw=path.read_bytes();return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def read_json(path):
    try:return json.loads(path.read_bytes())
    except (json.JSONDecodeError,UnicodeDecodeError) as error:raise ValueError(str(path)+': invalid JSON: '+str(error)) from error


def collect(root):
    proof=root/'native';proof.mkdir(parents=True,exist_ok=True)
    ndk=Path(os.environ['ANDROID_HOME'])/'ndk/27.0.12077973/toolchains/llvm/prebuilt/linux-x86_64/bin'
    app=Path('examples/android/app')
    for variant in ('Debug','Release'):
        kinds=('Debug',) if variant=='Debug' else ('Release','RelWithDebInfo')
        maps=[p for kind in kinds for p in (app/'.cxx'/kind).rglob('product-link.map')]
        binaries=[p for kind in kinds for p in (app/'build/intermediates/cxx'/kind).rglob('libexreader_product.so')]
        require(len(maps)==len(binaries)==1,'ambiguous/missing native '+variant+' outputs')
        prefix=variant.lower();shutil.copyfile(maps[0],proof/(prefix+'.map'));shutil.copyfile(binaries[0],proof/(prefix+'.so'))
        for label,tool,flags in (('symbols','llvm-nm',['--defined-only']),('dynamic','llvm-readelf',['-d'])):
            output=subprocess.check_output([str(ndk/tool),*flags,str(binaries[0])])
            (proof/(prefix+'.'+label+'.txt')).write_bytes(output)
    shutil.copyfile('stage/android-product/include/exreader-product/sqlite3.h',proof/'sqlite3.h')
    inventory={path.name:digest(path) for path in sorted(proof.iterdir()) if path.name!='inventory.json'}
    (proof/'inventory.json').write_text(json.dumps({'identity':identity(),'files':inventory},indent=2)+'\n')


def native(proof):
    inventory=read_json(proof/'inventory.json')
    require(inventory['identity']==identity(),'native build identity differs')
    require(set(inventory['files'])=={'debug.map','debug.so','debug.symbols.txt','debug.dynamic.txt',
            'release.map','release.so','release.symbols.txt','release.dynamic.txt','sqlite3.h'},'native inventory differs')
    for name,expected in inventory['files'].items():require(digest(proof/name)==expected,'native raw proof differs: '+name)
    for variant in ('debug','release'):
        symbols=(proof/(variant+'.symbols.txt')).read_text();mapping=(proof/(variant+'.map')).read_text();dynamic=(proof/(variant+'.dynamic.txt')).read_text()
        require(len(re.findall(r'\bsqlite3_open_v2\s*$',symbols,re.M))==1,'product provider definition is not unique')
        require('libreader_catalog_sqlite.a' in mapping and 'sqlite3_open_v2' in mapping,'link map lacks installed product SQLite')
        require('exr_vendor_exr_sqlite' not in symbols,'SDK SQLite leaked into product JNI')
        require(not re.search(r'NEEDED.*(?:sqlite|exreader)',dynamic,re.I),'product JNI depends on another SQLite/SDK provider')
        require(('Java_org_exreader_host_ProductFixture_' in symbols)==(variant=='debug'),'fixture functions present in release or absent in debug')
    header=(proof/'sqlite3.h').read_text()
    return re.search(r'#define SQLITE_SOURCE_ID\s+"([^"]+)"',header)[1],inventory


def inspect(root,all_exits):
    expected=identity();require((root/'source.txt').read_text().strip()==expected['source_sha'],'checkout source differs')
    require((root/'device-api.txt').read_text().strip()=='34' and (root/'device-abi.txt').read_text().strip()=='x86_64','API34 x86_64 required')
    device=read_json(root/'device-report.json');require(all(device.get(k)==v for k,v in expected.items()),'device source/run/attempt differs')
    require(device['api']==34 and device['abi']=='x86_64' and device['count']==len(NAMES) and device['failed']==0,'owner device execution failed')
    checks=device['checks'];require(len(checks)==len(NAMES) and {v['id'] for v in checks}==NAMES and all(v['pass'] is True for v in checks),'owner checks missing/duplicated/failed')
    raw_run=(root/'owner-instrumentation.txt').read_text()
    require(re.search(r'^INSTRUMENTATION_CODE: -1\s*$',raw_run,re.M) and 'OK (17 tests)' in raw_run and 'FAILURES' not in raw_run,'manual owner run failed')
    manual=[];status={}
    for line in raw_run.splitlines():
        if line.startswith('INSTRUMENTATION_STATUS: '):
            key,_,value=line[len('INSTRUMENTATION_STATUS: '):].partition('=');status[key]=value
        elif line.startswith('INSTRUMENTATION_STATUS_CODE: '):
            code=int(line.split(':',1)[1]);require(code in (0,1),'manual owner failure/skip status')
            if code==0:
                require(status.get('class')=='org.exreader.host.ProductOwnerTest','manual owner class differs')
                manual.append(status.get('test'))
            status={}
    require(len(manual)==len(NAMES) and set(manual)==NAMES,'manual owner checks missing/duplicated')
    names=[];reports={}
    for path in sorted((root/'owner-reports').rglob('*.xml')):
        tree=ET.fromstring(path.read_bytes());reports[str(path.relative_to(root))]=digest(path)
        for suite in tree.iter('testsuite'):require(not any(int(suite.get(k,'0')) for k in ('failures','errors','skipped')),'owner suite failed/skipped')
        for case in tree.iter('testcase'):
            require(case.get('classname')=='org.exreader.host.ProductOwnerTest' and not any(case.find(k) is not None for k in ('failure','error','skipped')),'owner XML failure or unexpected class')
            names.append(case.get('name'))
    require(len(names)==len(NAMES) and set(names)==NAMES,'owner XML cases missing/duplicated')
    source,proof=native(root/'native');provider=device['provider']
    build=read_json(Path('build/android-host/build.json'));application=digest(root/'apks/app-debug.apk')
    require(application['bytes']==build['artifacts']['app-debug.apk']['size'] and application['sha256']==build['artifacts']['app-debug.apk']['sha256'],
            'owner reinstallation APK differs from original same-source application')
    from android_host_evidence import native_record
    with zipfile.ZipFile(root/'apks/app-debug.apk') as archive:
        packaged=native_record(archive.read('lib/x86_64/libexreader_product.so'))
    require(packaged['build_id']==native_record((root/'native/debug.so').read_bytes())['build_id'],'packaged product provider differs from link proof')
    require(provider[0]=='3.54.0' and provider[1]==provider[2]==source,'actual provider source/header differs')
    require(Path(provider[3]).name=='libexreader_product.so','actual runtime function is from another provider')
    require({'THREADSAFE=1','DQS=0','OMIT_LOAD_EXTENSION','MAX_LENGTH=2147483647'}<=set(provider[4].split(';')),'actual provider options differ')
    phases={}
    for phase in ('before','after'):
        seed=root/('seed-'+phase+'.txt');recovery=root/('recover-'+phase+'.txt');witness=root/('witness-'+phase+'.txt')
        require('INSTRUMENTATION_RESULT: shortMsg=Process crashed.' in seed.read_text(),'typed command seed was not really killed')
        text=recovery.read_text();require('EXR_OWNER_RECOVERED recover-'+phase in text and re.search(r'^INSTRUMENTATION_CODE: -1\s*$',text,re.M) and 'EXR_OWNER_PHASE_FAILED' not in text,'native recovery failed')
        require(witness.read_text()==('1,1,0' if phase=='before' else '1,1,1'),'native three-write crash witness differs')
        phases[phase]={p.name:digest(p) for p in (seed,recovery,witness)}
    result={**expected,'accepted':True,'problems':[],'owner_checks':len(NAMES),'typed_kill_checks':2,
            'device_reports':reports,'native_proof':proof,'process_boundaries':phases,
            'manual_instrumentation':digest(root/'owner-instrumentation.txt'),
            'reinstalled_apks':{name:digest(root/'apks'/name) for name in ('app-debug.apk','app-debug-androidTest.apk')},
            'native_owner_serial_catalog_revision_handles':2,'local_project_three_writes_atomic':True,
            'cross_handle_or_sdk_database_atomicity_claimed':False,'classification_ui_accepted':False,
            'performance_accepted':False,'physical_device_execution':False,'complete_product':False}
    if all_exits:
        shelf=Path('build/shelf-android');original=read_json(shelf/'shelf-result.json')
        require(original['accepted'] is True and original['problems']==[] and all(original.get(k)==v for k,v in expected.items()),'original shelf acceptance missing')
        require(original['passed']==12 and original['ui']['ui_passed']==10 and original['import_mapping_passed']==14
                and original['killed_process_recovery_passed']==2 and original['original_host_accepted'] is True,'original 112 functional cases differ')
        for name,count in (('build/android-host/gate-review.json',48),('build/android-host/bounded-gate-review.json',20),('build/shelf-android/shelf-gate-review.json',19)):
            gate=read_json(Path(name));require(gate['accepted'] is True and gate.get('problems',[])==[] and not gate.get('problem')
                and all(gate.get(k)==v for k,v in expected.items()) and len(gate['checks'])==count
                and all(v.get('passed') is True for v in gate['checks']),'original 87 gate checks missing')
        result.update(original_functional_checks=112,original_gate_checks=87,original_shelf_accepted=True)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--collect-native',action='store_true');p.add_argument('--all-exits',action='store_true');a=p.parse_args()
    expected=identity();a.evidence.mkdir(parents=True,exist_ok=True)
    if a.collect_native:collect(a.evidence);return
    result={**expected,'accepted':False,'problems':[]}
    try:result=inspect(a.evidence,a.all_exits)
    except (ValueError,OSError,KeyError,TypeError,IndexError,ET.ParseError) as error:result['problems'].append(str(error))
    (a.evidence/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
    if not result['accepted']:raise SystemExit(1)


if __name__=='__main__':main()
