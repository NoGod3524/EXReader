"""Reproduce observations locally from connector-downloaded, digest-bound ZIPs."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import time
import zipfile

ROOT = Path(__file__).resolve().parent
SOURCE = Path('C:/Users/Oscar/OneDrive/Desktop/deepseekHarness/.tmp/exr-baseline/tools/f07_authoritative_symbols_20261103.py')
spec = importlib.util.spec_from_file_location('f07_candidate', SOURCE)
f07 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f07)
BIN = ROOT / 'llvm-tools/llvm-tools-1.99.0-x86_64-pc-windows-msvc/llvm-tools-preview/lib/rustlib/x86_64-pc-windows-msvc/bin'
f07.NM_BIN, f07.RO_BIN = str(BIN / 'llvm-nm.exe'), str(BIN / 'llvm-readobj.exe')
f07.START = time.monotonic()
metadata = {a['id']: a for a in json.loads((ROOT / 'producer-peer-metadata.json').read_bytes())['artifacts']}
result = {'acceptance_assessed': False, 'a4_partial': True,
          'source_sha': f07.SOURCE_SHA, 'producer_run': f07.RUN_ID,
          'candidate_script_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
          'tools': {name: {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                           'version': f07.tool_version(str(path))}
                    for name, path in [('nm', BIN / 'llvm-nm.exe'), ('readobj', BIN / 'llvm-readobj.exe')]},
          'inputs': [], 'binaries': []}
for target, aid in f07.ARTIFACTS.items():
    blob = (ROOT / f'peer-{aid}.zip').read_bytes()
    digest = f07.validate_artifact(metadata[aid], aid, blob)
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        assert archive.namelist().count('program.bin') == 1
        payload = archive.read('program.bin')
        receipt = json.loads(archive.read('build-receipt.json'))
        assert receipt['source_sha'] == f07.SOURCE_SHA
        assert str(receipt['run_id']) == f07.RUN_ID and str(receipt['attempt']) == '1'
        identity = json.loads(archive.read('installed-identity.json')) if 'installed-identity.json' in archive.namelist() else None
        identity_hash = hashlib.sha256(archive.read('installed-identity.json')).hexdigest() if identity else None
        if receipt.get('installed_identity_sha256'):
            assert identity_hash == receipt['installed_identity_sha256']
        program_hash = hashlib.sha256(payload).hexdigest()
        matches = []
        if identity:
            for scope in ('sdk_files', 'raw_files'):
                matches.extend(scope + '/' + name for name, item in identity.get(scope, {}).items()
                               if isinstance(item, dict) and item.get('sha256') == program_hash)
        result['inputs'].append({'target': target, 'artifact_id': aid, 'archive_digest': digest,
            'archive_bytes': len(blob), 'program_sha256': program_hash, 'program_bytes': len(payload),
            'receipt': receipt, 'installed_identity_sha256': identity_hash,
            'installed_program_hash_matches': matches, 'members': archive.namelist()})
    if target == 'android':
        with zipfile.ZipFile(io.BytesIO(payload)) as apk:
            members = [n for n in apk.namelist() if n.startswith('lib/') and n.endswith('.so')]
            assert 0 < len(members) <= 64 and len(members) == len(set(members))
            binaries = [(n, apk.read(n), 'elf') for n in members]
    else:
        kind = {'windows': 'pe', 'gtk': 'elf', 'macos': 'macho', 'iphone': 'macho', 'ipad': 'macho'}[target]
        binaries = [('program.bin', payload, kind)]
    for i, (name, binary, kind) in enumerate(binaries):
        p = ROOT / f'{target}-{i}.bin'
        p.write_bytes(binary)
        entry = f07.analyse_payload(target, kind, str(p))
        entry['member'] = name
        entry['sha256'] = hashlib.sha256(binary).hexdigest()
        result['binaries'].append(entry)
        print(target, name, entry['sqlite_counts'], 'complete=', entry['operations_complete'], flush=True)
(ROOT / 'local-peer-observations.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
assert all(b['operations_complete'] for b in result['binaries'])
print('Six peer digests/receipts verified; local observations saved. Acceptance remains unassessed.')
