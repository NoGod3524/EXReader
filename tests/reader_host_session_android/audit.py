"""Actions-only formal APK shared-SDK and isolated-product provider audit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

assert os.environ.get('GITHUB_ACTIONS')=='true'
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
ndk=Path(os.environ['ANDROID_HOME'])/'ndk/27.2.12479018/toolchains/llvm/prebuilt/linux-x86_64/bin'
def tool(name,*args):return subprocess.check_output([str(ndk/name),*map(str,args)],text=True)
archive=Path('build/session-android/sideload-stage/lib/libexr_sideload.a')
undefined=tool('llvm-nm','-u',archive);defined=tool('llvm-nm','--defined-only',archive)
(a.output/'installed-sideload-undefined.txt').write_text(undefined);(a.output/'installed-sideload-defined.txt').write_text(defined)
assert 'exr_library_source' in undefined and not re.search(r'\b(?:sqlite3_|reader_catalog_)',undefined+defined)
checks=[];app=Path('examples/android/app')
for variant in ('Debug','Release'):
    lower=variant.lower();apk=app/'build/outputs/apk'/lower/('app-'+lower+('-unsigned' if variant=='Release' else '')+'.apk')
    kinds=(variant,) if variant=='Debug' else ('Release','RelWithDebInfo')
    with zipfile.ZipFile(apk) as package:
        sdk_names=[n for n in package.namelist() if re.fullmatch(r'lib/x86_64/libexreader\.so(?:\.\d+)*',n)]
        assert len(sdk_names)==1,sdk_names
        sdk=a.output/(lower+'-sdk.so');sdk.write_bytes(package.read(sdk_names[0]))
        staged=Path('build/session-android/sdk-stage/lib/libexreader.so')
        expected_id=re.search(r'Build ID:\s*(\w+)',tool('llvm-readelf','-n',staged))
        actual_id=re.search(r'Build ID:\s*(\w+)',tool('llvm-readelf','-n',sdk))
        assert expected_id and actual_id and expected_id[1]==actual_id[1]
        for library,map_name in (('exreader_host','sdk-host-link.map'),('exreader_product','product-link.map')):
            originals=[f for kind in kinds for f in (app/'build/intermediates/cxx'/kind).rglob('lib'+library+'.so')]
            maps=[f for kind in kinds for f in (app/'.cxx'/kind).rglob(map_name)]
            assert len(originals)==len(maps)==1,(library,variant,originals,maps)
            original=originals[0];mapping=maps[0].read_text();symbols=tool('llvm-nm','--defined-only',original);dynamic=tool('llvm-readelf','-d',original)
            packaged=a.output/(lower+'-'+library+'.so');packaged.write_bytes(package.read('lib/x86_64/lib'+library+'.so'))
            original_id=re.search(r'Build ID:\s*(\w+)',tool('llvm-readelf','-n',original));package_id=re.search(r'Build ID:\s*(\w+)',tool('llvm-readelf','-n',packaged));assert original_id and package_id and original_id[1]==package_id[1]
            prefix=a.output/(lower+'-'+library);Path(str(prefix)+'.map').write_text(mapping);Path(str(prefix)+'-symbols.txt').write_text(symbols);Path(str(prefix)+'-dynamic.txt').write_text(dynamic)
            if library=='exreader_host':
                assert 'libexr_sideload.a' in mapping and 'exr_sideload_export_original' in symbols
                assert not re.search(r'\b(?:sqlite3_|exr_library_|exr_document_|exr_anchor_|exr_pager_)\w*\s*$',symbols,re.M)
                assert 'libexr_library.a' not in mapping and 'exr_vendor_exr_sqlite' not in mapping and 'reader_catalog_sqlite' not in mapping
                assert re.search(r'NEEDED.*libexreader\.so',dynamic)
            else:
                assert len(re.findall(r'\bsqlite3_open_v2\s*$',symbols,re.M))==1 and 'libreader_catalog_sqlite.a' in mapping
                assert 'exr_vendor_exr_sqlite' not in mapping and not re.search(r'\bexr_library_\w*\s*$',symbols,re.M)
                assert not re.search(r'NEEDED.*(?:sqlite|exreader|curl|xml|ssl|crypto)',dynamic,re.I)
                assert ('Java_org_exreader_host_NativeSyncProbe_sessions' in symbols)==(variant=='Debug')
            checks.append({'variant':variant,'library':library,'build_id':original_id[1],'packaged_sha256':hashlib.sha256(packaged.read_bytes()).hexdigest(),'shared_sdk_build_id':actual_id[1]})
        if variant=='Release':
            forbidden=(b'host_sync_fixture_ca',b'host_sync_fixture_network_security',b'NativeSyncProbe',b'HostSyncTest',b'EXReader Android test-only CA')
            for item in package.infolist():assert not any(token in item.filename.encode()+package.read(item) for token in forbidden),item.filename
    checks[-1]['apk_sha256']=hashlib.sha256(apk.read_bytes()).hexdigest()
result={**{key:os.environ[value] for key,value in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]},'accepted':True,'checks':checks,'installed_sideload_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'no_static_sdk_or_sqlite_in_host':True,'product_provider_isolated':True}
(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
