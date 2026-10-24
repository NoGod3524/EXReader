"""Actions-only installed Navigation/shared SDK and complete APK runtime materials."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

assert os.environ.get('GITHUB_ACTIONS')=='true'
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
ndk=Path(os.environ['ANDROID_HOME'])/'ndk/27.2.12479018/toolchains/llvm/prebuilt/linux-x86_64'
def tool(name,*args):return subprocess.check_output([str(ndk/'bin'/name),*map(str,args)],text=True)
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
cache=Path('build/session-android/sdk/CMakeCache.txt');text=cache.read_text();options={}
for key in ('EXR_ENABLE_AUDIO','EXR_ENABLE_MP3','EXR_ENABLE_AAC','EXR_BUILD_JNI','EXR_BUILD_SHARED_COMPAT'):
    values=re.findall('^'+key+r':BOOL=(ON|OFF)$',text,re.M);assert len(values)==1,(key,values);options[key]=values[0]
assert options['EXR_ENABLE_AUDIO']=='ON' and options['EXR_ENABLE_AAC']=='OFF'
archive=Path('build/android-navigation/navigation-stage/lib/libreader_navigation.a');defined=tool('llvm-nm','--defined-only',archive);undefined=tool('llvm-nm','-u',archive)
(a.output/'installed-navigation-defined.txt').write_text(defined);(a.output/'installed-navigation-undefined.txt').write_text(undefined)
assert 'reader_navigation_children' in defined and not re.search(r'\b(?:sqlite3_|reader_revision_|exr_library_)\w*\s*$',defined,re.M)
assert 'exr_document_resolve' in undefined and 'exr_publication_navigation' in undefined
system_names={path.name for path in (ndk/'sysroot/usr/lib/x86_64-linux-android/26').glob('*.so')};assert {'libc.so','libm.so','libdl.so'}<=system_names
sdk_archives={path.name for path in Path('build/session-android/sdk-stage').rglob('*.a')};assert sdk_archives
app=Path('examples/android/app');checks=[];installed={}
for name in ('libexreader.so','libexreader_jni.so'):
    path=Path('build/session-android/sdk-stage/lib')/name;dynamic=tool('llvm-readelf','-d',path);(a.output/('installed-'+name+'-dynamic.txt')).write_text(dynamic)
    installed[name]={'bytes':path.stat().st_size,'sha256':digest(path),'needed':re.findall(r'\(NEEDED\).*\[([^\]]+)\]',dynamic)}
for variant in ('Debug','Release'):
    lower=variant.lower();apk=app/'build/outputs/apk'/lower/('app-'+lower+('-unsigned' if variant=='Release' else '')+'.apk');kinds=(variant,) if variant=='Debug' else ('Release','RelWithDebInfo')
    with zipfile.ZipFile(apk) as package:
        runtimes={name.rsplit('/',1)[-1]:name for name in package.namelist() if name.startswith('lib/x86_64/') and name.endswith('.so')};materials={}
        assert set(runtimes)=={'libexreader.so','libexreader_jni.so','libexreader_host.so','libexreader_product.so'},runtimes
        for name,entry in runtimes.items():
            path=a.output/(lower+'-'+name);path.write_bytes(package.read(entry));dynamic=tool('llvm-readelf','-d',path);(a.output/(lower+'-'+name+'-dynamic.txt')).write_text(dynamic)
            needed=re.findall(r'\(NEEDED\).*\[([^\]]+)\]',dynamic);assert not set(needed)-set(runtimes)-system_names,(variant,name,needed)
            materials[name]={'bytes':path.stat().st_size,'sha256':digest(path),'needed':needed}
        assert materials['libexreader_host.so']['needed'].count('libexreader.so')==1 and materials['libexreader_jni.so']['needed'].count('libexreader.so')==1
        for library,mapping_name in [('exreader_host','sdk-host-link.map'),('exreader_product','product-link.map')]:
            originals=[path for kind in kinds for path in (app/'build/intermediates/cxx'/kind).rglob('lib'+library+'.so')];maps=[path for kind in kinds for path in (app/'.cxx'/kind).rglob(mapping_name)];assert len(originals)==len(maps)==1
            symbols=tool('llvm-nm','--defined-only',originals[0]);mapping=maps[0].read_text();(a.output/(lower+'-'+mapping_name)).write_text(mapping)
            if library=='exreader_host':
                assert 'libreader_navigation.a' in mapping and 'reader_navigation_children' in symbols
                assert not any(name in mapping for name in sdk_archives) and not re.search(r'\b(?:sqlite3_|exr_document_|exr_library_|exr_pager_|exr_anchor_)\w*\s*$',symbols,re.M)
                assert ('Java_org_exreader_host_NativeNavigationProbe_live' in symbols)==(variant=='Debug')
            else:
                assert 'libreader_navigation.a' not in mapping and not re.search(r'\breader_navigation_\w*\s*$',symbols,re.M)
                assert len(re.findall(r'\bsqlite3_open_v2\s*$',symbols,re.M))==1
        if variant=='Release':
            for entry in package.infolist():
                data=entry.filename.encode()+package.read(entry);assert b'NativeNavigationProbe' not in data and b'NavigationUiTest' not in data,entry.filename
        checks.append({'variant':variant,'apk_bytes':apk.stat().st_size,'apk_sha256':digest(apk),'runtimes':materials})
result={**{key:os.environ[value] for key,value in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]},'accepted':True,'installed_navigation_sha256':digest(archive),'shared_sdk_single_provider':True,'no_navigation_or_sdk_in_product_dso':True,'checks':checks,
        'sdk_configuration':{'profile':'formal Android shared SDK, not desktop reading-core preset','options':options,'actual_cache_sha256':digest(cache),'installed_runtimes':installed,'jni_requires_audio_pdf':True}}
(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
