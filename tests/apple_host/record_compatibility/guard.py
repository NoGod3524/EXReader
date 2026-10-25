"""Pin both actual SDKs and every existing host/module except the reviewed owner."""
import os
import subprocess

BASE = 'eea3087c2ef27b9d45e00333ef0a16e586a0ac6e'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
ALLOWED = ('examples/apple/HostReadingRecords.swift', 'tests/apple_host/record_compatibility/',
           'examples/android/app/src/main/java/org/exreader/host/NativeReadingSdk.java',
           'examples/android/app/src/main/java/org/exreader/host/NativeCbz.java',
           'examples/android/app/src/main/java/org/exreader/host/ReadingParserPolicy.java',
           '.github/workflows/reader-apple-record-compatibility.yml',
           'docs/READER-APPLE-RECORD-COMPATIBILITY.md', 'docs/validation/reader-apple-record-compatibility.json')
assert os.environ.get('GITHUB_ACTIONS') == 'true'
subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'], check=True)
subprocess.run(['git', 'diff', '--exit-code', SDK, 'HEAD', '--', 'src', 'include', 'cmake', 'CMakeLists.txt',
                'bindings', 'tests/fixtures', '.github/workflows/native.yml', '.github/workflows/reliability.yml'], check=True)
for path in subprocess.check_output(['git', 'diff', '--name-only', BASE, 'HEAD'], text=True).splitlines():
    assert any(path.startswith(p) if p.endswith('/') else path == p for p in ALLOWED), path
print('Exact SDK trees and isolated Apple record owner scope verified')
from pathlib import Path
formatter = Path('examples/android/app/src/main/cpp/reading_sdk_jni.inc').read_text()
assert 'snprintf(parser,sizeof(parser),"exreader-sdk-%s",exr_version())' in formatter
assert 'context.parser_version=fields[1].c_str()' in Path('examples/android/app/src/main/cpp/reading_product_jni.inc').read_text()
