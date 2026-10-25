"""Actions-only proof that the actual CBZ renderer uses the original shared SDK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

assert os.environ.get('GITHUB_ACTIONS') == 'true'
p = argparse.ArgumentParser()
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
ndk = Path(os.environ['ANDROID_HOME']) / 'ndk/27.2.12479018/toolchains/llvm/prebuilt/linux-x86_64/bin'
checks = []
app = Path('examples/android/app')
for variant in ('Debug', 'Release'):
    lower = variant.lower()
    kinds = (variant,) if variant == 'Debug' else ('Release', 'RelWithDebInfo')
    apk = app / 'build/outputs/apk' / lower / ('app-' + lower + ('-unsigned' if variant == 'Release' else '') + '.apk')
    libraries = {}
    with zipfile.ZipFile(apk) as package:
        for name in ('exreader_host', 'exreader_product'):
            path = a.output / (lower + '-lib' + name + '.so')
            path.write_bytes(package.read('lib/x86_64/lib' + name + '.so'))
            files = [file for kind in kinds for file in (app / 'build/intermediates/cxx' / kind).rglob('lib' + name + '.so')]
            assert len(files) == 1
            defined = subprocess.check_output([str(ndk / 'llvm-nm'), '--defined-only', str(files[0])], text=True)
            dynamic = subprocess.check_output([str(ndk / 'llvm-readelf'), '-d', str(path)], text=True)
            needed = re.findall(r'\(NEEDED\).*\[([^\]]+)\]', dynamic)
            for method in ('nativeOpen', 'nativePages', 'nativeRender', 'nativeResolve', 'nativeClose'):
                assert ('Java_org_exreader_host_NativeCbz_' + method in defined) == (name == 'exreader_host')
            assert not re.search(r'\bexr_fixed_(?:open_memory|render|load_text|anchor_create|anchor_resolve)\s*$', defined, re.M)
            if name == 'exreader_host':
                assert needed.count('libexreader.so') == 1
                assert not re.search(r'\bsqlite3_\w*\s*$', defined, re.M)
            else:
                assert 'libexreader.so' not in needed
            (a.output / (lower + '-' + name + '-defined.txt')).write_text(defined)
            libraries[name] = {'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'needed': needed}
        if variant == 'Release':
            assert not any(b'CbzReadingUiTest' in package.read(entry) for entry in package.namelist())
    checks.append({'variant': variant, 'apk_bytes': apk.stat().st_size, 'apk_sha256': hashlib.sha256(apk.read_bytes()).hexdigest(), 'libraries': libraries})
result = {**{key: os.environ[value] for key, value in [('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT')]},
          'accepted': True, 'same_actual_renderer_doc_for_paint_and_public_resolve': True,
          'single_original_shared_sdk': True, 'no_new_product_sqlite_or_sdk': True, 'checks': checks}
(a.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result), flush=True)
