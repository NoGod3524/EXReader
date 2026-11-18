"""Rebuild the pre-WIP affine kernel and current candidate with shared PDF code.

Run from the repository root after configuring build/perf. Outputs go to
out/image-paint-reproduce/{A,B}; the working source is restored even on failure.
"""
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

source = Path('src/affine_image.c')
saved = source.read_bytes()
baseline = subprocess.check_output(['git', 'show', '809b3743d:src/affine_image.c'])
metadata = {'baseline_affine_ref': '809b3743d', 'shared_pdf_image_sha256': hashlib.sha256(Path('src/pdf_image.c').read_bytes()).hexdigest(), 'builds': {}}
try:
    for tag, code in [('A', baseline), ('B', saved)]:
        source.write_bytes(code)
        dll = Path('build/perf/libexreader.dll')
        dll.unlink(missing_ok=True)
        started = time.time()
        subprocess.run(['cmake', '--build', 'build/perf', '--target', 'exreader', '-j', '4'], check=True)
        assert dll.exists() and dll.stat().st_mtime >= started - 2
        destination = Path('out/image-paint-reproduce') / tag
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dll, destination / dll.name)
        metadata['builds'][tag] = {'source_sha256': hashlib.sha256(code).hexdigest(), 'dll_sha256': hashlib.sha256(dll.read_bytes()).hexdigest(), 'dll_mtime': dll.stat().st_mtime, 'bytes': dll.stat().st_size}
finally:
    source.write_bytes(saved)
Path('out/image-paint-reproduce/builds.json').write_text(json.dumps(metadata, indent=2) + '\n')
print(json.dumps(metadata, indent=2))
