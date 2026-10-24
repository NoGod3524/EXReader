#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only package size, dependency, license and Release boundary evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from fixture import require_actions


def main():
    require_actions();p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    sdk=Path(os.environ['ANDROID_HOME']);ndk=sdk/'ndk/27.2.12479018/toolchains/llvm/prebuilt/linux-x86_64/bin'
    aapt=sdk/'build-tools/35.0.0/aapt2';files={
      'baseline_apk':Path('tests/webdav_android/android/baseline/build/outputs/apk/release/baseline-release-unsigned.apk'),
      'backend_apk':Path('tests/webdav_android/android/backend/build/outputs/apk/release/backend-release-unsigned.apk'),
      'support_aar':Path('extras/webdav/android/webdav/build/outputs/aar/webdav-release.aar'),
      'static_archive':Path('build/webdav-android/stage-release/lib/libexr_webdav.a')}
    # The module's Gradle name is :support when consumed by the standalone probe.
    if not files['support_aar'].is_file():files['support_aar']=Path('extras/webdav/android/webdav/build/outputs/aar/support-release.aar')
    rows={}
    forbidden=(b'fixture_ca',b'EXReader Android test-only CA',b'fixture_network_security',b'exr_webdav_android_test_stats',b'ProcessProbe',b'ExitActivity')
    for name,path in files.items():
        data=path.read_bytes();row={'path':str(path),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as package:
                methods=0
                for entry in package.infolist():
                    payload=package.read(entry)
                    assert not any(token in entry.filename.encode()+payload for token in forbidden),(name,entry.filename)
                    if entry.filename.endswith('.dex'):
                        assert payload[:4]==b'dex\n';methods+=struct.unpack_from('<I',payload,0x58)[0]
                row['dex_method_references']=methods
        else:assert not any(token in data for token in forbidden)
        rows[name]=row
    manifest=subprocess.check_output([str(aapt),'dump','xmltree',str(files['backend_apk']),'--file','AndroidManifest.xml'],text=True)
    assert 'networkSecurityConfig' not in manifest and 'debuggable' not in manifest
    (a.output/'release-manifest.txt').write_text(manifest)
    symbols=subprocess.check_output([str(ndk/'llvm-nm'),'--defined-only',str(files['static_archive'])],text=True)
    assert 'exr_webdav_android_initialize' in symbols and 'exr_webdav_android_test_stats' not in symbols
    (a.output/'release-static-symbols.txt').write_text(symbols)
    with zipfile.ZipFile(files['backend_apk']) as package:
        library=package.read('lib/x86_64/libwebdav-consumer.so');local=a.output/'release-consumer.so';local.write_bytes(library)
    deps=subprocess.check_output([str(ndk/'llvm-readelf'),'-d',str(local)],text=True)
    assert not any(name in deps.lower() for name in ('libcurl','libxml','libssl','libcrypto','webview','chromium'))
    (a.output/'release-native-dependencies.txt').write_text(deps)
    runtime=json.loads(Path('extras/webdav/android/webdav/build/reports/runtime.json').read_text());licenses=[]
    namespaces={'m':'http://maven.apache.org/POM/4.0.0'}
    for item in runtime:
        group,artifact,version=item['module'].split(':');url=f'https://repo.maven.apache.org/maven2/{group.replace(".","/")}/{artifact}/{version}/{artifact}-{version}.pom'
        pom=urllib.request.urlopen(url,timeout=30).read();parsed=ET.fromstring(pom)
        declared=[{'name':node.findtext('m:name',default='',namespaces=namespaces),'url':node.findtext('m:url',default='',namespaces=namespaces)} for node in parsed.findall('m:licenses/m:license',namespaces)]
        assert declared,(item['module'],'license metadata missing')
        licenses.append({**item,'pom_url':url,'pom_sha256':hashlib.sha256(pom).hexdigest(),'licenses':declared})
    assert any(item['module']=='com.squareup.okhttp3:okhttp:4.12.0' for item in runtime)
    rows['runtime']=licenses;rows['apk_bytes_delta']=rows['backend_apk']['bytes']-rows['baseline_apk']['bytes']
    rows['dex_method_references_delta']=rows['backend_apk']['dex_method_references']-rows['baseline_apk']['dex_method_references']
    rows.update(source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],release_boundaries_verified=True)
    (a.output/'packages.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(rows),flush=True)


if __name__=='__main__':main()
