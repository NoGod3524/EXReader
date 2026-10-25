"""Actions-only exact seven installed archives and actual raw Debug/Release providers."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile
assert os.environ.get('GITHUB_ACTIONS')=='true'
out=Path('build/android-raw3/native');out.mkdir(parents=True,exist_ok=True)
ndk=Path(os.environ['ANDROID_HOME'])/'ndk/27.2.12479018/toolchains/llvm/prebuilt/linux-x86_64/bin'
def tool(name,*args):return subprocess.check_output([str(ndk/name),*map(str,args)],text=True)
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def build_id(path):
    found=re.search(r'Build ID:\s*(\w+)',tool('llvm-readelf','-n',path));assert found,path
    return found[1]
modules=[('reader_revisions','reader_revision_get_raw_v3'),('reader_reading_state_codec','reader_rs_decode_raw_v3'),
 ('reader_reading_commands','reader_rc_apply_raw_v3'),('reader_annotation_view','reader_av_page_get_raw_v3'),
 ('reader_commands','reader_command_apply_book_raw_v3'),('reader_sync','reader_sync_step_raw_v3'),
 ('reader_session','reader_session_create_raw_v3')]
archives={}
for name,symbol in modules:
    file=Path('build/android-raw3/product-stage/lib')/('lib'+name+'.a')
    defined=tool('llvm-nm','--defined-only',file);assert re.search(r'\b'+symbol+r'\s*$',defined,re.M)
    assert not re.search(r'\b(?:sqlite3_|exr_library_|exr_document_|exr_pager_)\w*\s*$',defined,re.M)
    (out/(name+'-defined.txt')).write_text(defined)
    archives[name]={'sha256':digest(file),'bytes':file.stat().st_size,'symbol':symbol}
checks=[];app=Path('examples/android/app')
for variant,kinds in [('debug',['Debug']),('release',['Release','RelWithDebInfo'])]:
    apk=Path('build/android-raw3/apks')/('host-'+variant+'.apk');libraries={}
    with zipfile.ZipFile(apk) as z:
        sdk_names=[p for p in z.namelist() if re.fullmatch(r'lib/x86_64/libexreader\.so(?:\.\d+)*',p)]
        assert sdk_names==['lib/x86_64/libexreader.so']
        sdk=out/(variant+'-sdk.so');sdk.write_bytes(z.read(sdk_names[0]))
        assert build_id(sdk)==build_id(Path('build/session-android/sdk-stage/lib/libexreader.so'))
        for name,mapname in [('exreader_host','sdk-host-link.map'),('exreader_product','product-link.map')]:
            packaged=out/(variant+'-'+name+'.so');packaged.write_bytes(z.read('lib/x86_64/lib'+name+'.so'))
            maps=[]
            for kind in kinds:
                for mapping in (app/'.cxx'/kind).rglob(mapname):
                    cache=mapping.parent/'CMakeCache.txt'
                    if cache.is_file() and 'EXR_READER_SELECTOR_BYTES_CANDIDATE:BOOL=ON' in cache.read_text():maps.append(mapping)
            assert len(maps)==1,(variant,name,maps)
            mapping=maps[0];key=mapping.parent.parent.name
            originals=[file for kind in kinds for file in (app/'build/intermediates/cxx'/kind).rglob('lib'+name+'.so') if key in file.parts]
            assert len(originals)==1 and build_id(originals[0])==build_id(packaged),(name,originals,key)
            defined=tool('llvm-nm','--defined-only',originals[0]);dynamic=tool('llvm-readelf','-d',packaged);text=mapping.read_text()
            (out/(variant+'-'+mapname)).write_text(text);(out/(variant+'-'+name+'-defined.txt')).write_text(defined)
            if name=='exreader_product':
                assert all(symbol in defined and 'lib'+module+'.a' in text for module,symbol in modules)
                assert len(re.findall(r'\bsqlite3_open_v2\s*$',defined,re.M))==1 and 'libreader_catalog_sqlite.a' in text
                assert 'exr_vendor_exr_sqlite' not in text and not re.search(r'\bexr_(?:library_|document_|pager_|anchor_)\w*\s*$',defined,re.M)
                assert ('Java_org_exreader_host_Raw3Probe_family' in defined)==(variant=='debug')
                assert not re.search(r'NEEDED.*(?:sqlite|exreader|curl|xml|ssl|crypto)',dynamic,re.I)
            else:
                assert len(re.findall(r'NEEDED.*\[libexreader.so\]',dynamic))==1
                assert not re.search(r'\b(?:sqlite3_|reader_revision_|reader_rc_|reader_av_)\w*\s*$',defined,re.M)
            libraries[name]={'sha256':digest(packaged),'build_id':build_id(packaged)}
        if variant=='release':
            assert not any(b'Raw3Probe' in z.read(p) or b'Raw3InteropTest' in z.read(p) for p in z.namelist())
    checks.append({'variant':variant,'apk_sha256':digest(apk),'sdk_dso_sha256':digest(sdk),'libraries':libraries})
result={**{k:os.environ[v] for k,v in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]},
 'accepted':True,'archives':archives,'checks':checks,'legacy_anchor_max_version':2,'single_shared_sdk':True,'one_product_sqlite':True,'default_enabled':False}
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
