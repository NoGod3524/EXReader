"""Read-only package/SDK archive inspection; no product code is executed."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import time
import zipfile

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('f07', 'C:/Users/Oscar/OneDrive/Desktop/deepseekHarness/.tmp/exr-baseline/tools/f07_authoritative_symbols_20261103.py')
f07 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f07)
BIN = ROOT / 'llvm-tools/llvm-tools-1.99.0-x86_64-pc-windows-msvc/llvm-tools-preview/lib/rustlib/x86_64-pc-windows-msvc/bin'
f07.NM_BIN, f07.RO_BIN = str(BIN / 'llvm-nm.exe'), str(BIN / 'llvm-readobj.exe')
f07.START = time.monotonic()
metadata = {a['id']: a for a in json.loads((ROOT / 'producer-all-artifacts-metadata.json').read_bytes())['artifacts']}
peers = json.loads((ROOT / 'local-peer-observations.json').read_text())
result = {'acceptance_assessed': False, 'builds': []}
for aid, target in [(13082734165, 'windows'), (13083942264, 'gtk'), (13083581922, 'macos'), (13083354773, 'iphone')]:
    blob = (ROOT / f'build-{aid}.zip').read_bytes()
    digest = f07.validate_artifact(metadata[aid], aid, blob)
    with zipfile.ZipFile(io.BytesIO(blob)) as outer:
        names = outer.namelist()
        entry = {'artifact_id': aid, 'target': target, 'archive_digest': digest, 'outer_members': names,
                 'provider_files': [n for n in names if n.lower().endswith(('.a', '.lib', '.o', '.obj', '.map', '.rsp'))],
                 'nested_packages': [], 'libraries': []}
        peer = next(p for p in peers['inputs'] if p['target'] == target)
        if 'program.bin' in names:
            entry['program_sha256'] = hashlib.sha256(outer.read('program.bin')).hexdigest()
            entry['program_matches_peer'] = entry['program_sha256'] == peer['program_sha256']
        for name in names:
            if name.endswith('.zip'):
                with zipfile.ZipFile(io.BytesIO(outer.read(name))) as nested:
                    nested_names = nested.namelist()
            elif name.endswith('.tar.gz'):
                with tarfile.open(fileobj=io.BytesIO(outer.read(name)), mode='r:gz') as nested:
                    nested_names = nested.getnames()
            else:
                continue
            entry['nested_packages'].append({'name': name, 'members': nested_names,
                'provider_files': [n for n in nested_names if n.lower().endswith(('.a', '.lib', '.o', '.obj', '.map', '.rsp'))]})
        if target in ('macos', 'iphone'):
            cache = {}
            for i, name in enumerate(n for n in names if n.endswith(('.a', '.dylib'))):
                binary = outer.read(name)
                sha = hashlib.sha256(binary).hexdigest()
                if sha not in cache:
                    path = ROOT / f'library-{target}-{i}.bin'
                    path.write_bytes(binary)
                    op = f07.run(['llvm-nm', '--format=posix', str(path)])
                    assert f07.operation_ok(op), (name, op)
                    symbols = f07.classify_nm(op['out'])
                    cache[sha] = {'sqlite': symbols, 'operation': op}
                    if name.endswith('.dylib'):
                        cache[sha]['needed_libraries_operation'] = f07.run(['llvm-readobj', '--needed-libs', str(path)])
                entry['libraries'].append({'name': name, 'sha256': sha, **cache[sha]})
    result['builds'].append(entry)
    print(target, 'provider_files=', len(entry['provider_files']),
          'nested_provider_files=', sum(len(p['provider_files']) for p in entry['nested_packages']),
          'sqlite_defining_libraries=', [(l['name'], len(l['sqlite']['defined'])) for l in entry['libraries'] if l['sqlite']['defined']], flush=True)
(ROOT / 'build-package-observations.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
