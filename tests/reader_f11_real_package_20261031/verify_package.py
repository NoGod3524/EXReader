#!/usr/bin/env python3
"""Read-only fixed historical simulator package audit. Executes no package code."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import stat
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip
spec = importlib.util.spec_from_file_location('f11_identity', ROOT / 'tools/reader_f11_mobile_identity_20261031/verify.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

def need(ok, reason):
    if not ok:
        raise ValueError(reason)
def sha(data):
    return hashlib.sha256(data).hexdigest()
def inventory(raw):
    bundle = zipfile.ZipFile(io.BytesIO(raw))
    entries = bundle.infolist()
    need(len(entries) <= 10000 and sum(e.file_size for e in entries) <= 256*1024*1024, 'archive-budget')
    names = [e.filename for e in entries]
    need(len(names) == len(set(names)), 'duplicate-archive-entry')
    normalized = set()
    for e in entries:
        p = PurePosixPath(e.filename)
        parts = e.filename.rstrip('/').split('/')
        need(parts and all(part not in ('', '.', '..') for part in parts), 'noncanonical-archive-path')
        name = str(p)
        need(name not in normalized, 'normalized-duplicate-archive-entry')
        normalized.add(name)
        need(not p.is_absolute() and '..' not in p.parts and '\\' not in e.filename, 'unsafe-archive-path')
        need(not stat.S_ISLNK(e.external_attr >> 16), 'archive-symlink')
        need(not e.flag_bits & 1, 'encrypted-archive-entry')
    return bundle

def main():
    need(os.environ.get('GITHUB_ACTIONS') == 'true', 'actions-only')
    lock = json.loads(Path(__file__).with_name('source_lock.json').read_text())
    need(os.environ['GITHUB_REPOSITORY'] == lock['repository'], 'repository')
    need(lock['gate_source'] == '9b5d0d6914671c99fc20b8cc7361f700b83ca778', 'gate-source-pin')
    out = ROOT / 'build/f11-real-package'
    out.mkdir(parents=True, exist_ok=True)
    report = {'accepted':False, 'scope':'historical simulator package identity only; no install/run/signing',
              'audit_source':os.environ['GITHUB_SHA'], 'audit_run':os.environ['GITHUB_RUN_ID'],
              'audit_attempt':os.environ['GITHUB_RUN_ATTEMPT'], 'producer_lock':lock}
    try:
        run = fetch('actions/runs/' + str(lock['producer_run']))
        need(run['head_sha'] == lock['producer_source'] and run['head_branch'] == lock['producer_branch'], 'producer-run-source')
        need(run['status'] == 'completed' and run['conclusion'] == 'success' and run['run_attempt'] == lock['producer_attempt'], 'producer-run-state')
        item = fetch('actions/artifacts/' + str(lock['artifact_id']))
        need(item['id'] == lock['artifact_id'] and item['name'] == lock['artifact_name'] and not item['expired'], 'artifact-identity')
        need(item['workflow_run']['id'] == lock['producer_run'] and item['workflow_run']['head_sha'] == lock['producer_source'], 'artifact-producer')
        need(item['size_in_bytes'] == lock['artifact_bytes'] and item['digest'] == 'sha256:' + lock['artifact_sha256'], 'artifact-metadata')
        raw = download_artifact_zip(lock['artifact_id'])
        need(len(raw) == lock['artifact_bytes'] and sha(raw) == lock['artifact_sha256'], 'artifact-actual-bytes')
        # Preserve only after API and actual outer-byte authentication.
        (out/'authenticated-original-artifact.zip').write_bytes(raw)
        (out/'source-lock.json').write_text(json.dumps(lock, indent=2)+'\n')
        (out/'authenticated-artifact-api.json').write_text(json.dumps(item, indent=2)+'\n')
        with inventory(raw) as archive:
            identity = json.loads(archive.read('identity.json'))
            build_raw = archive.read('host/build.json')
            build = json.loads(build_raw)
            (out/'original-build.json').write_bytes(build_raw)
            (out/'original-identity.json').write_bytes(archive.read('identity.json'))
            need((identity['source_sha'], str(identity['run_id']), str(identity['attempt']), identity['target']) ==
                 (lock['producer_source'], str(lock['producer_run']), str(lock['producer_attempt']), 'iphonesimulator'), 'inner-producer-identity')
            need(identity['sdk_content_candidate'] == lock['sdk_content_candidate'], 'sdk-content-pin')
            need(identity['sdk_content_paths'] == ['src','include','cmake','CMakeLists.txt','bindings'], 'sdk-content-paths')
            need(identity['product']['source_sha'] == lock['producer_source'] and identity['product']['sdk_version'] == lock['sdk_version'], 'product-identity')
            need(build['source_sha'] == lock['producer_source'] and build['sdk_version'] == lock['sdk_version'], 'build-identity')
            need(build['page_theme_enabled'] is True and identity['page_theme_enabled'] is True, 'original-feature-assertion')
            package = archive.read('EXReader.zip')
        need(sha(package) == identity['archive_sha256'], 'inner-archive-hash')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ignored = []
            with inventory(package) as app:
                for e in app.infolist():
                    if e.is_dir():
                        continue
                    # ditto resource forks are authenticated by inner ZIP hash, never interpreted as app code.
                    if e.filename.startswith('__MACOSX/'):
                        ignored.append(e.filename)
                        continue
                    need(e.filename.startswith('EXReader.app/'), 'unexpected-inner-file')
                    dest = root / e.filename
                    need(dest.resolve().is_relative_to(root), 'extract-boundary')
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(app.read(e))
            (root / 'build.json').write_bytes(build_raw) # authenticated original producer bytes, never rewritten
            need(sha((root/'EXReader.app/EXReader').read_bytes()) == identity['executable_sha256'], 'producer-executable-hash')
            info = plistlib.loads((root/'EXReader.app/Info.plist').read_bytes())
            need(info['EXRSourceSHA'] == lock['producer_source'] and info['CFBundleShortVersionString'] == lock['sdk_version'], 'plist-identity')
            need(info['EXRWave3Enabled'] is True and info['EXRRawSelectorEnabled'] is True, 'original-plist-flags')
            # Adapter inventory is explicitly derived, NOT a historical S20 manifest.
            files = {str(p.relative_to(root)):{'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size}
                     for p in root.rglob('*') if p.is_file()}
            manifest = {'target':'iphone','source_sha':lock['producer_source'],'sdk_version':lock['sdk_version'],'files':files}
            result = gate.verify(root, manifest, 'iphone', lock['producer_source'], lock['sdk_version'])
            report.update({'accepted':True,'gate':result,'derived_inventory_not_original_manifest':True,
                           'archive_sha256':sha(raw),'inner_archive_sha256':sha(package),
                           'original_build_sha256':sha(build_raw),'executable_sha256':identity['executable_sha256'],
                           'ignored_authenticated_resource_forks':ignored,
                           'file_count':len(files)})
    except Exception as error:
        report['failure'] = type(error).__name__ + ': ' + str(error)
    (out/'receipt.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report), flush=True)
    return 0 if report['accepted'] else 1
if __name__ == '__main__':
    raise SystemExit(main())
