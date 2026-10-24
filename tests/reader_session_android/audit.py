#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only actual two-owner symbols, link maps and Release boundary audit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import zipfile


def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    ndk=Path(os.environ['ANDROID_HOME'])/'ndk/27.2.12479018/toolchains/llvm/prebuilt/linux-x86_64/bin'
    def tool(name,*args):return subprocess.check_output([str(ndk/name),*map(str,args)],text=True)
    checks=[]
    for module,product,sdk,map_name in (
        ('tests/reader_session_android/android/session','session-product-owner','session-sdk-owner','product-owner.map'),
        ('examples/android/app','exreader_product','exreader_host','product-link.map')):
        app=Path(module)
        for variant in ('Debug','Release'):
            prefix=product+'-'+variant.lower();apk=app/'build/outputs/apk'/variant.lower()/(('session' if 'session' in module else 'app')+'-'+variant.lower()+('-unsigned' if variant=='Release' else '')+'.apk')
            with zipfile.ZipFile(apk) as archive:
                native=a.output/(prefix+'.so');native.write_bytes(archive.read('lib/x86_64/lib'+product+'.so'))
                sdk_native=a.output/(sdk+'-'+variant.lower()+'.so');sdk_native.write_bytes(archive.read('lib/x86_64/lib'+sdk+'.so'))
                if variant=='Release' and 'session' in module:
                    forbidden=(b'fixture_ca',b'fixture_network_security',b'ControlReceiver',b'ControlActivity',b'SessionController',b'EXReader Android test-only CA',b'exr_webdav_android_test_stats')
                    for entry in archive.infolist():
                        assert not any(token in entry.filename.encode()+archive.read(entry) for token in forbidden),entry.filename
            # Packaged libraries are stripped; keep actual unstripped symbols
            # from the matching build and retain both identities.
            kinds=(variant,) if variant=='Debug' else ('Release','RelWithDebInfo')
            originals=[f for kind in kinds for f in (app/'build/intermediates/cxx'/kind).rglob('lib'+product+'.so')]
            maps=[f for kind in kinds for f in (app/'.cxx'/kind).rglob(map_name)]
            assert len(originals)==len(maps)==1,(module,variant,originals,maps)
            original=originals[0];mapping=maps[0].read_text();shutil.copyfile(maps[0],a.output/(prefix+'.map'))
            build_id=re.search(r'Build ID:\s*(\w+)',tool('llvm-readelf','-n',original));packaged_id=re.search(r'Build ID:\s*(\w+)',tool('llvm-readelf','-n',native))
            assert build_id and packaged_id and build_id[1]==packaged_id[1]
            symbols=tool('llvm-nm','--defined-only',original);dynamic=tool('llvm-readelf','-d',original);exports=tool('llvm-nm','-D','--defined-only',original)
            for label,value in (('symbols',symbols),('dynamic',dynamic),('exports',exports)):(a.output/(prefix+'-'+label+'.txt')).write_text(value)
            assert len(re.findall(r'\bsqlite3_open_v2\s*$',symbols,re.M))==1
            assert 'libreader_catalog_sqlite.a' in mapping and 'sqlite3_open_v2' in mapping
            assert 'exr_vendor_exr_sqlite' not in mapping and not re.search(r'\bexr_library_',symbols)
            assert not re.search(r'NEEDED.*(?:sqlite|exreader|curl|xml|ssl|crypto)',dynamic,re.I)
            assert not re.search(r'\bsqlite3_open_v2\s*$',exports,re.M)
            assert ('exr_webdav_android_test_stats' in symbols)==(variant=='Debug' and 'session' in module)
            if 'session' in module:
                sdk_originals=[f for kind in kinds for f in (app/'build/intermediates/cxx'/kind).rglob('lib'+sdk+'.so')];assert len(sdk_originals)==1
                sdk_symbols=tool('llvm-nm','--defined-only',sdk_originals[0]);(a.output/(sdk+'-'+variant.lower()+'-symbols.txt')).write_text(sdk_symbols)
                assert len(re.findall(r'\bsqlite3_open_v2\s*$',sdk_symbols,re.M))==1 and not re.search(r'\breader_(?:catalog|session|revision)',sdk_symbols)
                sdk_maps=[f for kind in kinds for f in (app/'.cxx'/kind).rglob('sdk-owner.map')];assert len(sdk_maps)==1
                sdk_mapping=sdk_maps[0].read_text();assert 'exr_vendor_exr_sqlite' in sdk_mapping and 'reader_catalog_sqlite' not in sdk_mapping
                shutil.copyfile(sdk_maps[0],a.output/(sdk+'-'+variant.lower()+'.map'))
            checks.append({'module':module,'variant':variant,'build_id':build_id[1],'packaged_sha256':hashlib.sha256(native.read_bytes()).hexdigest(),'installed_private_provider_unique':True})
    aapt=Path(os.environ['ANDROID_HOME'])/'build-tools/35.0.0/aapt2'
    manifest=subprocess.check_output([str(aapt),'dump','xmltree','tests/reader_session_android/android/session/build/outputs/apk/release/session-release-unsigned.apk','--file','AndroidManifest.xml'],text=True)
    assert 'networkSecurityConfig' not in manifest and 'debuggable' not in manifest and 'ControlReceiver' not in manifest
    (a.output/'release-manifest.txt').write_text(manifest)
    result={**{key:os.environ[value] for key,value in [('source_sha','GITHUB_SHA'),('run_id','GITHUB_RUN_ID'),('attempt','GITHUB_RUN_ATTEMPT')]},'checks':checks,'accepted':True}
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)


if __name__=='__main__':main()
