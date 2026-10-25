"""Actions-only approved host scope and exact sealed family/source constraints."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
assert os.environ.get('GITHUB_ACTIONS')=='true'
BASE='3c8c9eabbd9e8a5001db10b7a1a92cf69be1c223'
FAMILY='0793b26256e1397ba0f60d27de7d090fad61af81'
MERGE='09377761748cd5549bc864e932e5edd38019142b'
SDK='edddc463c06ed5731195cdb8f06b2df6dff7699e'
def git(*args):return subprocess.check_output(['git',*args],text=True,encoding='utf-8').strip()
def same(ref,*paths):subprocess.run(['git','diff','--exit-code',ref,'HEAD','--',*paths],check=True)
assert git('rev-parse','HEAD')==os.environ['GITHUB_SHA']
for source in (BASE,FAMILY,MERGE):subprocess.run(['git','merge-base','--is-ancestor',source,'HEAD'],check=True)
modules=['revisions','reading-state','reading-commands','annotation-view','commands','sync','session']
same(FAMILY,*['apps/reader/'+m for m in modules])
same(SDK,'src','include','cmake','CMakeLists.txt')
same(BASE,'bindings','extras','apps/reader/store','tests/fixtures',
     'examples/android/app/src/main/cpp/reading_sdk_jni.inc',
     'examples/android/app/src/main/java/org/exreader/host/NativeReadingSdk.java',
     'examples/android/app/src/main/java/org/exreader/host/ReadingParserPolicy.java',
     'examples/android/app/src/main/java/org/exreader/host/NativeCbz.java',
     'tests/apple_host/record_compatibility','tests/apple_host/reading',
     'tests/reader_android_page_theme','tests/reader_android_host_import','tests/reader_android_fixed_pan',
     'tests/reader_android_cbz_reading','tests/reader_android_reading','tests/reader_android_preferences',
     'tests/reader_android_navigation','tests/reader_android_search','tests/reader_host_session_android')
same(FAMILY,'tests/reader_android_record_interop','tests/reader_selector_bytes','tests/reader_raw_store_companions')
allowed={'examples/android/app/build.gradle',*[ 'examples/android/app/src/main/cpp/'+s for s in
    ['CMakeLists.txt','catalog_jni.cpp','reading_product_jni.inc','sync_jni.cpp']],
    *['examples/android/app/src/main/java/org/exreader/host/'+s+'.java' for s in
      ['NativeReadingProduct','ReadingRequests','ReadingVersion','MainActivity']],
    '.github/workflows/reader-android-raw3.yml','docs/READER-ANDROID-RAW3.md','docs/validation/reader-android-raw3.json'}
changed=git('diff','--name-only',MERGE,'HEAD').splitlines()
assert all(p in allowed or p.startswith('tests/reader_android_raw3/') for p in changed),changed
pdf=Path('tests/fixtures/pdf-public-text.pdf').read_bytes()
assert len(pdf)==8845 and hashlib.sha256(pdf).hexdigest()=='5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc'
out=Path('build/android-raw3');out.mkdir(parents=True,exist_ok=True)
(out/'guard.json').write_text(json.dumps({'accepted':True,'base':BASE,'family':FAMILY,'merge':MERGE,'source_sha':os.environ['GITHUB_SHA'],
    'changed':changed,'sdk_boundaries_unchanged':True,'legacy_suites_unchanged':True,'seven_modules_unchanged':True},indent=2)+'\n')
