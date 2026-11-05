"""Actions-only source, manifest and original-ZIP contracts for the isolated candidate."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
import re
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / 'tests/reader_format_candidate'
WORK = ROOT / 'build/format'
BASE = 'e67d87cbeabb2457e0852f681ef0b27b2c0da4d8'
SDK = 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
F5 = '278d63691a4c73e7aa932d71a40a5938c5427514'
C04 = 'bfc6447798d533c4d5d5fe7ca02e9a54fc928999'
S13 = '313ebbb4f8e73ba42eb3bbe2b04b292f854886b4'
C05 = '1659f83491985baa26b609f287a02a01744bc6b2'
PATCHES = {
    'rtf': ('src/rtf.c', '2542b50eb2ae0d814b97670226ba704799fed44d347f60003d44982ef45a21fd',
            '14a1537048e7e8bd412976c513d35b693672ed9a05afc09436773076f90c32d6',
            'ea3fc050cc4ff2383fa97727e15568754cf9aa8ef12007e1e06311ed2ee56662'),
    'cbz': ('src/cbz.c', '8320206c0efafe398cab0e63d2d59869e83292a32a56a33c53a894e5fa3ab78a',
            '85f90ad69432a2a8d5979844694fa96715bdb2ef7186d276e374a684eb0d4d52',
            '49ef7cb5f7160ceaa471fbfdeb194638a5cbbcca5fb9d44d3199e857f565c49d')}
OWNED = ('candidates/reader-format-combination/', 'tests/reader_format_candidate/', 'docs/reader-format-combination/')
OWNED_FILES = {'.github/workflows/reader-format-combination.yml', 'HANDOFF-RESULT-FORMAT-COMBINATION.md'}


def actions():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Execution is reserved for Actions'


def identity():
    return {'source_sha': os.environ['GITHUB_SHA'], 'run_id': int(os.environ['GITHUB_RUN_ID']),
            'attempt': int(os.environ['GITHUB_RUN_ATTEMPT'])}


def git(*args, cwd=ROOT):
    return subprocess.check_output(['git', *map(str, args)], cwd=cwd)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            assert key not in result, 'duplicate JSON key'
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def original_manifest():
    raw = git('show', F5 + ':tests/reader_real_corpus/manifest.json')
    assert digest(raw) == 'be300d9a54329ab227ac7060bc39e0117de722ae3c60d6c0d998418eba994bf6'
    return raw, strict_json(raw)


def manifest_contract(candidate):
    _, original = original_manifest()
    wanted = deepcopy(original)
    wanted['dataset_id'] = 'reader-real-corpus-v2'
    rows = [row for row in wanted['files'] if row['id'] == 'rtf-crowley-policy']
    assert len(rows) == 1
    rows[0]['query'] = 'EH123 Rhetoric and Composition I'
    assert candidate == wanted, 'v2 differs outside the one query and dataset identity'
    assert len(candidate['files']) == 18 and not candidate['pending']
    return candidate


def owned_paths(paths):
    assert all(path.startswith(OWNED) or path in OWNED_FILES for path in paths), 'foreign changed path'


def verify_program(path, record):
    path = Path(path)
    assert path.is_file() and path.stat().st_size == record['bytes'] and file_hash(path) == record['sha256'], 'program bytes mismatch'


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def materialize():
    actions(); source_files = {}
    for label, source, prefix in (('f5', F5, 'tests/reader_real_corpus/'),
                                  ('rtf', C04, 'tests/reader_next_c04/'),
                                  ('cbz', S13, 'tests/reader_next_s13/')):
        paths = git('ls-tree', '-r', '--name-only', source, '--', prefix).decode().splitlines()
        assert paths
        for path in paths:
            relative = path[len(prefix):]
            target = WORK / 'vendor' / label / relative
            body = git('show', source + ':' + path)
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(body)
            source_files[label + '/' + relative] = {'source': source, 'git_path': path, 'sha256': digest(body), 'bytes': len(body)}
    for source, path in ((C05, 'candidates/reader-next-c05/probe.c'),
                         (C05, 'candidates/reader-next-c05/CMakeLists.txt'),
                         (S13, 'candidates/reader-next-s13/manifest.json'),
                         (S13, 'candidates/reader-next-s13/src/cbz.c')):
        body = git('show', source + ':' + path)
        target = WORK / 'source-records' / path
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(body)
        source_files[path] = {'source': source, 'sha256': digest(body), 'bytes': len(body)}
    assert file_hash(WORK / 'vendor/f5/consumer.c') == 'f2b5d06d1fb1450c74317b537164ca97b60d7826806175066b597335d342cf96'
    assert file_hash(WORK / 'vendor/f5/CMakeLists.txt') == '545147fa67c104ff6ccccb8a7419e17963c729639efdf759be777fbe11001288'
    return source_files


def guard():
    actions(); own = identity()
    assert git('rev-parse', 'HEAD').decode().strip() == own['source_sha']
    assert not git('diff', '--name-only', 'HEAD').strip(), 'tracked working source changed after checkout'
    assert os.environ['GITHUB_REF_NAME'] == 'codex/reader-format-combination'
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'], cwd=ROOT, check=True)
    changed = git('diff', '--name-only', BASE, 'HEAD').decode().splitlines()
    owned_paths(changed)
    assert not git('diff', '--name-only', SDK, 'HEAD', '--', 'src', 'include', 'cmake', 'CMakeLists.txt', 'bindings').strip()
    assert not git('diff', '--name-only', BASE, 'HEAD', '--', 'tests/fixtures', 'tests/reader_real_corpus', '.github/workflows/native.yml').strip()
    for name, (path, patch_hash, pre_hash, _) in PATCHES.items():
        patch = ROOT / 'candidates/reader-format-combination' / (name + '.patch')
        assert file_hash(patch) == patch_hash
        assert digest(git('show', SDK + ':' + path)) == pre_hash
        assert [line for line in patch.read_text(encoding='utf-8').splitlines() if line.startswith('+++ ')] == ['+++ b/' + path]
    candidate = manifest_contract(strict_json((HERE / 'manifest-v2.json').read_bytes()))
    material = materialize()
    f5 = load_module(WORK / 'vendor/f5/run_acceptance.py', 'original_f5_guard')
    f5.validate_manifest(original_manifest()[1], 'run')
    result = {**own, 'ok': True, 'base_sdk': SDK, 'f5': F5, 'c04': C04, 's13': S13, 'c05': C05,
              'changed_paths': changed, 'sources': material, 'manifest_v2_sha256': file_hash(HERE / 'manifest-v2.json'),
              'real_input_ids': [row['id'] for row in candidate['files']],
              'patches': {name: {'path': values[0], 'sha256': values[1], 'pre_sha256': values[2], 'post_sha256': values[3]} for name, values in PATCHES.items()}}
    write(WORK / 'guard/guard.json', result)
    return result


def combined_tree(order=None):
    actions()
    with tempfile.TemporaryDirectory(prefix='format-index-') as directory:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(directory) / 'index'))
        subprocess.run(['git', 'read-tree', SDK], cwd=ROOT, env=env, check=True)
        for name in (list(PATCHES) if order is None else order):
            subprocess.run(['git', 'apply', '--cached', str(ROOT / 'candidates/reader-format-combination' / (name + '.patch'))], cwd=ROOT, env=env, check=True)
        tree = subprocess.check_output(['git', 'write-tree'], cwd=ROOT, env=env).decode().strip()
    for path, _, _, post_hash in PATCHES.values():
        assert digest(git('show', tree + ':' + path)) == post_hash
    return {'base_sdk_tree': git('rev-parse', SDK + '^{tree}').decode().strip(), 'candidate_sdk_tree': tree,
            'base_src_tree': git('rev-parse', SDK + ':src').decode().strip(),
            'candidate_src_tree': git('rev-parse', tree + ':src').decode().strip()}


def safe_members(archive, max_bytes=1024 ** 3):
    infos = archive.infolist()
    assert len(infos) <= 20000 and len({row.orig_filename for row in infos}) == len(infos), 'duplicate or excessive ZIP entries'
    assert sum(row.file_size for row in infos) <= max_bytes, 'expanded ZIP limit'
    for row in infos:
        name = row.orig_filename
        assert name and not any(char in name for char in ('\\', ':', '\x00')) and not name.startswith('/'), 'unsafe original ZIP name'
        path = PurePosixPath(name)
        assert '..' not in path.parts and str(path) == name.rstrip('/'), 'noncanonical ZIP name'
        assert (row.external_attr >> 16) & 0o170000 in (0, 0o100000, 0o040000), 'nonregular ZIP member'


def api_helpers():
    sys.path.insert(0, str(ROOT / 'tools'))
    from check_parallel_integration import fetch, download_artifact_zip
    return fetch, download_artifact_zip


def artifact_metadata(row, full_name, own):
    assert row['name'] == full_name and row['workflow_run']['id'] == own['run_id'] and row['workflow_run']['head_sha'] == own['source_sha'], 'artifact source/run/attempt identity'
    assert row['expired'] is False and type(row['size_in_bytes']) is int and row['size_in_bytes'] > 0, 'expired/empty artifact'
    assert re.fullmatch(r'sha256:[0-9a-f]{64}', row['digest']), 'artifact digest syntax'
    assert datetime.fromisoformat(row['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc), 'artifact expiry'


def artifact_body(row, raw):
    assert len(raw) == row['size_in_bytes'] and 'sha256:' + digest(raw) == row['digest'], 'actual ZIP byte count/digest'


def artifact(name, destination):
    actions(); fetch, download = api_helpers(); own = identity()
    full = f"{name}-{own['run_id']}-{own['attempt']}"
    rows = fetch(f"actions/runs/{own['run_id']}/artifacts?per_page=100")['artifacts']
    found = [row for row in rows if row['name'] == full]; assert len(found) == 1, full
    row = found[0]
    artifact_metadata(row, full, own)
    raw = download(row['id'])
    artifact_body(row, raw)
    destination = Path(destination); destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as zipped:
        safe_members(zipped)
        zipped.extractall(destination)
    return {key: row[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')}
